// WASKITA - firmware kotak sensor energi (ESP32 + SCT-013 + ZMPT101B).
//
// Alur:
//   measurementTask (core 1, prioritas 2)
//     - tiap 500 ms menangkap 12 siklus V & I pada 4 kHz (sampel V lalu I),
//     - computeWindow(): Vrms, Irms, P, Q, PF, frekuensi (10 siklus bulat),
//     - setiap 2 jendela -> 1 TelemetrySample (agregat 1 detik) -> queue.
//   loop() (core 1, prioritas 1)
//     - portal WiFiManager non-blocking, tombol reset, perintah serial,
//     - queue -> ring buffer RAM (-> spool LittleFS bila RAM penuh),
//     - kirim ke backend: /ingest (1 sampel) atau /ingest-batch (backlog),
//     - NTP, reconnect WiFi, OTA, LED status, watchdog.
//
// Kontrak API: backend/docs/CONTRACTS.md bagian 7.

#include <Arduino.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <esp_idf_version.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <math.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include <vector>

#include "config.h"
#include "power_calc.h"
#include "sample_ring.h"
#include "telemetry_format.h"

using waskita::Aggregator;
using waskita::Calibration;
using waskita::SampleRing;
using waskita::TelemetrySample;
using waskita::WindowConfig;
using waskita::WindowResult;

// ===========================================================================
// Status global
// ===========================================================================

static Preferences g_prefs;
static const char* kPrefsNs = "waskita";

// Konfigurasi runtime (dari NVS, diisi lewat portal).
static char g_apiBase[129] = "";
static char g_deviceId[65] = "";
static char g_deviceKey[129] = "";
static char g_hostname[32] = "";
static char g_apName[32] = "";

// Kalibrasi dibaca measurementTask, ditulis loop() -> dilindungi spinlock.
static portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
static Calibration g_cal = {V_CAL_DEFAULT, I_CAL_DEFAULT, PHASE_CAL_DEFAULT};

// Tampilan "live" (rata-rata eksponensial beberapa jendela) untuk perintah
// serial status/kalibrasi. Ditulis measurementTask di bawah g_mux.
struct LiveView {
  float v_rms, i_rms, p_active, q_reactive, power_factor, frequency_hz;
  float phase_deg, sample_rate_hz;
  bool freq_valid;
  uint32_t windows;
};
static LiveView g_live = {};

static QueueHandle_t g_sampleQueue = nullptr;
static TaskHandle_t g_measTask = nullptr;
static volatile uint32_t g_droppedQueue = 0;
static volatile uint32_t g_slowSamplingWindows = 0;

// Buffer tangkapan ADC (hanya dipakai measurementTask).
static uint16_t g_rawV[CAPTURE_SAMPLES];
static uint16_t g_rawI[CAPTURE_SAMPLES];

// Ring buffer + buffer kerja (dialokasikan di heap saat boot).
static SampleRing g_ring;
static TelemetrySample* g_scratch = nullptr;  // BATCH_MAX sampel
static char* g_json = nullptr;
static size_t g_jsonCap = 0;
static size_t g_batchLimit = BATCH_MAX;
static uint32_t g_droppedRing = 0;

// Spool LittleFS.
static bool g_spoolOk = false;
static uint32_t g_spoolBytes = 0;
static uint32_t g_spoolReadOffset = 0;

// Waktu.
static bool g_timeSynced = false;
static int64_t g_epochOffsetMs = 0;  // epoch_ms = uptime_ms + offset
static uint32_t g_lastTimeCheckMs = 0;

// Jaringan.
static WiFiManager g_wm;
static WiFiManagerParameter g_paramApi("api_base", "URL server WASKITA (mis. http://192.168.1.10:8000)", "", 128);
static WiFiManagerParameter g_paramDevId("device_id", "ID perangkat (sama dengan registrasi di backend)", "", 64);
static WiFiManagerParameter g_paramDevKey("device_key", "Device key (kosongkan bila tidak diubah)", "", 128,
                                          "type=\"password\" autocomplete=\"off\"");
static WiFiClient g_plainClient;
static WiFiClientSecure g_secureClient;
static bool g_netStarted = false;
static bool g_otaStarted = false;
static volatile bool g_otaInProgress = false;
static uint32_t g_lastReconnectMs = 0;
static uint32_t g_portalClosedMs = 0;
static bool g_portalWasActive = false;

// Uplink.
static uint32_t g_nextAttemptMs = 0;
static uint32_t g_backoffMs = 0;
static bool g_authError = false;
static bool g_lastSendFailed = false;
static uint32_t g_sentSamples = 0;
static uint32_t g_failedPosts = 0;
static uint32_t g_droppedRejected = 0;

// Arah daya.
static uint32_t g_reverseStreak = 0;
static uint32_t g_reverseTotal = 0;
static uint32_t g_lastReverseWarnMs = 0;

// Tombol & LED.
static bool g_btnDown = false;
static uint32_t g_btnSinceMs = 0;

enum class LedState : uint8_t {
  Boot,
  Portal,
  Connecting,
  Online,
  Buffering,
  ConfigError,
  ResetPending,
};
static LedState g_ledState = LedState::Boot;

// ===========================================================================
// Utilitas
// ===========================================================================

static inline bool timeReached(uint32_t now, uint32_t deadline) {
  return (int32_t)(now - deadline) >= 0;
}

static inline int64_t uptimeMs() { return esp_timer_get_time() / 1000; }

static bool configComplete() {
  return g_apiBase[0] != '\0' && g_deviceId[0] != '\0' && g_deviceKey[0] != '\0';
}

static void copyStr(char* dst, size_t cap, const char* src) {
  if (!dst || cap == 0) return;
  if (!src) src = "";
  strncpy(dst, src, cap - 1);
  dst[cap - 1] = '\0';
}

static void trimInPlace(char* s) {
  if (!s) return;
  char* p = s;
  while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') ++p;
  if (p != s) memmove(s, p, strlen(p) + 1);
  size_t len = strlen(s);
  while (len > 0 && (s[len - 1] == ' ' || s[len - 1] == '\t' || s[len - 1] == '\r' ||
                     s[len - 1] == '\n')) {
    s[--len] = '\0';
  }
}

// ===========================================================================
// Watchdog (API berbeda antara ESP-IDF 4.x dan 5.x)
// ===========================================================================

static void setupWatchdog() {
#if ESP_IDF_VERSION_MAJOR >= 5
  esp_task_wdt_config_t wdt;
  wdt.timeout_ms = (uint32_t)WDT_TIMEOUT_S * 1000UL;
  wdt.idle_core_mask = 0;
  wdt.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&wdt) != ESP_OK) {
    esp_task_wdt_init(&wdt);
  }
#else
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
#endif
  esp_task_wdt_add(nullptr);  // task loop()
}

// ===========================================================================
// Preferences (NVS)
// ===========================================================================

// MAC dasar dari eFuse (sama dengan MAC STA), tersedia sebelum WiFi aktif.
static void readMac(uint8_t mac[6]) {
  const uint64_t efuse = ESP.getEfuseMac();
  for (int k = 0; k < 6; ++k) mac[k] = (uint8_t)((efuse >> (8 * k)) & 0xFF);
}

static void defaultDeviceId(char* out, size_t cap) {
  uint8_t mac[6] = {0};
  readMac(mac);
  snprintf(out, cap, "%s%02X%02X%02X", DEVICE_ID_PREFIX, mac[3], mac[4], mac[5]);
}

static void loadConfig() {
  g_prefs.begin(kPrefsNs, true);
  String api = g_prefs.getString("api_base", DEFAULT_API_BASE);
  String id = g_prefs.getString("dev_id", "");
  String key = g_prefs.getString("dev_key", "");
  g_cal.v_cal = g_prefs.getFloat("v_cal", V_CAL_DEFAULT);
  g_cal.i_cal = g_prefs.getFloat("i_cal", I_CAL_DEFAULT);
  g_cal.phase_cal = g_prefs.getFloat("ph_cal", PHASE_CAL_DEFAULT);
  g_spoolReadOffset = g_prefs.getUInt("spool_off", 0);
  g_prefs.end();

  char norm[sizeof(g_apiBase)];
  if (api.length() > 0 && waskita::normalizeApiBase(api.c_str(), norm, sizeof(norm))) {
    copyStr(g_apiBase, sizeof(g_apiBase), norm);
  } else {
    g_apiBase[0] = '\0';
  }
  copyStr(g_deviceId, sizeof(g_deviceId), id.c_str());
  if (!waskita::isValidDeviceId(g_deviceId)) defaultDeviceId(g_deviceId, sizeof(g_deviceId));
  copyStr(g_deviceKey, sizeof(g_deviceKey), key.c_str());

  if (!(g_cal.v_cal > 0.0f) || !(g_cal.i_cal > 0.0f) || !isfinite(g_cal.phase_cal)) {
    g_cal.v_cal = V_CAL_DEFAULT;
    g_cal.i_cal = I_CAL_DEFAULT;
    g_cal.phase_cal = PHASE_CAL_DEFAULT;
  }
}

static void saveCalibration(const Calibration& c) {
  portENTER_CRITICAL(&g_mux);
  g_cal = c;
  portEXIT_CRITICAL(&g_mux);
  g_prefs.begin(kPrefsNs, false);
  g_prefs.putFloat("v_cal", c.v_cal);
  g_prefs.putFloat("i_cal", c.i_cal);
  g_prefs.putFloat("ph_cal", c.phase_cal);
  g_prefs.end();
}

static Calibration currentCalibration() {
  portENTER_CRITICAL(&g_mux);
  Calibration c = g_cal;
  portEXIT_CRITICAL(&g_mux);
  return c;
}

static LiveView currentLive() {
  portENTER_CRITICAL(&g_mux);
  LiveView v = g_live;
  portEXIT_CRITICAL(&g_mux);
  return v;
}

static void saveSpoolOffset() {
  g_prefs.begin(kPrefsNs, false);
  g_prefs.putUInt("spool_off", g_spoolReadOffset);
  g_prefs.end();
}

// Dipanggil WiFiManager setelah form portal disimpan.
static void onPortalParamsSaved() {
  char buf[129];
  bool changed = false;

  copyStr(buf, sizeof(buf), g_paramApi.getValue());
  trimInPlace(buf);
  char norm[129];
  g_prefs.begin(kPrefsNs, false);
  if (buf[0] != '\0') {
    if (waskita::normalizeApiBase(buf, norm, sizeof(norm))) {
      g_prefs.putString("api_base", norm);
      changed = true;
    } else {
      Serial.println(F("[portal] URL server tidak valid (harus diawali http:// atau https://) - diabaikan"));
    }
  }

  copyStr(buf, sizeof(buf), g_paramDevId.getValue());
  trimInPlace(buf);
  if (buf[0] != '\0') {
    if (waskita::isValidDeviceId(buf)) {
      g_prefs.putString("dev_id", buf);
      changed = true;
    } else {
      Serial.println(F("[portal] ID perangkat tidak valid (1-64 karakter A-Z a-z 0-9 . _ -) - diabaikan"));
    }
  }

  copyStr(buf, sizeof(buf), g_paramDevKey.getValue());
  trimInPlace(buf);
  if (buf[0] != '\0') {
    g_prefs.putString("dev_key", buf);
    changed = true;
  }
  g_prefs.end();

  if (changed) {
    loadConfig();
    g_authError = false;
    g_backoffMs = 0;
    g_nextAttemptMs = millis();
    Serial.printf("[portal] konfigurasi tersimpan: server=%s id=%s key=%s\n", g_apiBase,
                  g_deviceId, g_deviceKey[0] ? "(terisi)" : "(KOSONG)");
  }
}

// ===========================================================================
// Pengukuran (measurementTask)
// ===========================================================================

static void setupAdc() {
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_ADC_VOLTAGE, ADC_11db);
  analogSetPinAttenuation(PIN_ADC_CURRENT, ADC_11db);
  pinMode(PIN_ADC_VOLTAGE, INPUT);
  pinMode(PIN_ADC_CURRENT, INPUT);
  // Baca sekali agar driver ADC terinisialisasi sebelum loop berwaktu.
  (void)analogRead(PIN_ADC_VOLTAGE);
  (void)analogRead(PIN_ADC_CURRENT);
}

// Tangkap CAPTURE_SAMPLES pasangan sampel dengan jadwal tetap (busy-wait
// pada esp_timer). V dibaca lalu I segera sesudahnya; selisih waktu kecil
// itu dikompensasi PHASE_CAL. Return laju sampel aktual (Hz).
static float captureWindow() {
  const int64_t period_us = 1000000LL / SAMPLE_RATE_HZ;
  int64_t next = esp_timer_get_time();
  int64_t t_first = next;
  int64_t t_last = next;
  uint32_t late = 0;
  for (size_t k = 0; k < (size_t)CAPTURE_SAMPLES; ++k) {
    int64_t t;
    while ((t = esp_timer_get_time()) < next) {
      // busy-wait: presisi waktu sampel lebih penting daripada yield
    }
    if (t - next > period_us / 2) ++late;
    if (k == 0) t_first = t;
    t_last = t;
    g_rawV[k] = (uint16_t)analogRead(PIN_ADC_VOLTAGE);
    g_rawI[k] = (uint16_t)analogRead(PIN_ADC_CURRENT);
    next += period_us;
  }
  if (late > (uint32_t)CAPTURE_SAMPLES / 10) g_slowSamplingWindows = g_slowSamplingWindows + 1;
  const int64_t span = t_last - t_first;
  if (span <= 0) return (float)SAMPLE_RATE_HZ;
  return (float)(CAPTURE_SAMPLES - 1) * 1.0e6f / (float)span;
}

static void updateLive(const WindowResult& r, float fs) {
  const float a = 0.2f;  // EMA ~5 jendela (~2,5 detik)
  portENTER_CRITICAL(&g_mux);
  if (g_live.windows == 0) {
    g_live.v_rms = r.v_rms;
    g_live.i_rms = r.i_rms;
    g_live.p_active = r.p_active;
    g_live.q_reactive = r.q_reactive;
    g_live.power_factor = r.power_factor;
    g_live.frequency_hz = r.frequency_hz;
    g_live.phase_deg = r.phase_deg;
  } else {
    g_live.v_rms += a * (r.v_rms - g_live.v_rms);
    g_live.i_rms += a * (r.i_rms - g_live.i_rms);
    g_live.p_active += a * (r.p_active - g_live.p_active);
    g_live.q_reactive += a * (r.q_reactive - g_live.q_reactive);
    g_live.power_factor += a * (r.power_factor - g_live.power_factor);
    g_live.frequency_hz += a * (r.frequency_hz - g_live.frequency_hz);
    g_live.phase_deg += a * (r.phase_deg - g_live.phase_deg);
  }
  g_live.sample_rate_hz = fs;
  g_live.freq_valid = r.freq_valid;
  g_live.windows++;
  portEXIT_CRITICAL(&g_mux);
}

static void measurementTask(void*) {
  esp_task_wdt_add(nullptr);
  WindowConfig wc;
  wc.sample_rate_hz = (float)SAMPLE_RATE_HZ;
  wc.nominal_freq_hz = MAINS_NOMINAL_HZ;
  wc.target_cycles = WINDOW_CYCLES;
  wc.volts_per_count = ADC_VOLTS_PER_COUNT;
  wc.i_noise_floor_a = I_NOISE_FLOOR_A;
  wc.v_min_for_freq_v = V_MIN_FOR_FREQ_V;
  wc.min_hysteresis_counts = MIN_HYSTERESIS_COUNTS;
  wc.invert_current = (CT_INVERT != 0);

  Aggregator agg;
  TickType_t lastWake = xTaskGetTickCount();
  for (;;) {
    const float fs = captureWindow();
    const Calibration cal = currentCalibration();
    wc.sample_rate_hz = fs;
    WindowResult r;
    if (waskita::computeWindow(g_rawV, g_rawI, CAPTURE_SAMPLES, wc, cal, &r)) {
      updateLive(r, fs);
      agg.add(r);
    }
    if (agg.count() >= WINDOWS_PER_SAMPLE) {
      TelemetrySample s;
      if (agg.finish(uptimeMs(), MAINS_NOMINAL_HZ, &s)) {
        waskita::sanitizeForBackend(&s, waskita::defaultBackendLimits());
        if (xQueueSend(g_sampleQueue, &s, 0) != pdTRUE) g_droppedQueue = g_droppedQueue + 1;
      }
      agg.reset();
    }
    esp_task_wdt_reset();
    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(WINDOW_PERIOD_MS));
  }
}

// ===========================================================================
// Waktu (NTP)
// ===========================================================================

static void maintainTime() {
  const uint32_t now = millis();
  const uint32_t interval = g_timeSynced ? 60000UL : 1000UL;
  if (now - g_lastTimeCheckMs < interval) return;
  g_lastTimeCheckMs = now;
  struct timeval tv;
  if (gettimeofday(&tv, nullptr) != 0) return;
  if ((long)tv.tv_sec < MIN_VALID_EPOCH) return;
  const int64_t epoch_ms = (int64_t)tv.tv_sec * 1000 + (int64_t)(tv.tv_usec / 1000);
  g_epochOffsetMs = epoch_ms - uptimeMs();
  if (!g_timeSynced) {
    g_timeSynced = true;
    char iso[40];
    waskita::formatIso8601(epoch_ms, TZ_OFFSET_SECONDS, iso, sizeof(iso));
    Serial.printf("[ntp] jam tersinkron: %s\n", iso);
  }
}

static inline int64_t uptimeToEpochMs(int64_t up_ms) { return up_ms + g_epochOffsetMs; }

// ===========================================================================
// Spool LittleFS
// ===========================================================================

static void setupSpool() {
#if ENABLE_LITTLEFS_SPOOL
  if (!LittleFS.begin(true)) {
    Serial.println(F("[spool] LittleFS gagal di-mount - spool nonaktif (hanya RAM)"));
    g_spoolOk = false;
    return;
  }
  g_spoolOk = true;
  g_spoolBytes = 0;
  if (LittleFS.exists(SPOOL_PATH)) {
    File f = LittleFS.open(SPOOL_PATH, "r");
    if (f) {
      g_spoolBytes = (uint32_t)f.size();
      f.close();
    }
  }
  // Abaikan rekaman terakhir yang terpotong (mati listrik saat menulis).
  g_spoolBytes -= g_spoolBytes % sizeof(TelemetrySample);
  if (g_spoolReadOffset > g_spoolBytes || g_spoolReadOffset % sizeof(TelemetrySample) != 0) {
    g_spoolReadOffset = 0;
  }
  if (g_spoolBytes > 0) {
    Serial.printf("[spool] %u sampel tertunda di flash\n",
                  (unsigned)((g_spoolBytes - g_spoolReadOffset) / sizeof(TelemetrySample)));
  }
#endif
}

static bool spoolHasData() { return g_spoolOk && g_spoolReadOffset < g_spoolBytes; }

static void spoolClear() {
#if ENABLE_LITTLEFS_SPOOL
  if (g_spoolOk) LittleFS.remove(SPOOL_PATH);
#endif
  g_spoolBytes = 0;
  g_spoolReadOffset = 0;
  saveSpoolOffset();
}

// Pindahkan n sampel tertua dari RAM ke flash (butuh jam tersinkron karena
// spool menyimpan epoch, agar tetap benar setelah reboot).
static size_t spillOldestToSpool(size_t n) {
#if ENABLE_LITTLEFS_SPOOL
  if (!g_spoolOk || !g_timeSynced || n == 0) return 0;
  if (n > g_ring.size()) n = g_ring.size();
  const size_t rec = sizeof(TelemetrySample);
  if ((size_t)g_spoolBytes + n * rec > (size_t)SPOOL_MAX_BYTES) return 0;
  File f = LittleFS.open(SPOOL_PATH, FILE_APPEND);
  if (!f) return 0;
  size_t written = 0;
  for (size_t k = 0; k < n; ++k) {
    TelemetrySample s = g_ring.at(k);
    s.time_ms = uptimeToEpochMs(s.time_ms);
    if (f.write((const uint8_t*)&s, rec) != rec) break;
    ++written;
  }
  f.close();
  g_spoolBytes += (uint32_t)(written * rec);
  g_ring.popFront(written);
  return written;
#else
  (void)n;
  return 0;
#endif
}

// ===========================================================================
// Queue -> ring buffer
// ===========================================================================

static void noteDirection(const TelemetrySample& s) {
  if (s.flags & waskita::FLAG_REVERSE_POWER) {
    ++g_reverseStreak;
    ++g_reverseTotal;
    const uint32_t now = millis();
    if (g_reverseStreak >= 10 && now - g_lastReverseWarnMs > 60000UL) {
      g_lastReverseWarnMs = now;
      Serial.printf(
          "[arah] P negatif selama %u detik berturut-turut (dikirim sebagai 0 W). "
          "Kemungkinan CT terpasang terbalik (balik arah klem atau set CT_INVERT=1) "
          "atau ada ekspor daya PLTS.\n",
          (unsigned)g_reverseStreak);
    }
  } else {
    g_reverseStreak = 0;
  }
}

static void drainQueueToRing() {
  TelemetrySample s;
  while (xQueueReceive(g_sampleQueue, &s, 0) == pdTRUE) {
    noteDirection(s);
    if (g_ring.full()) {
      size_t chunk = SPOOL_CHUNK;
      if (chunk > g_ring.size()) chunk = g_ring.size();
      spillOldestToSpool(chunk);
    }
    if (g_ring.push(s, nullptr)) ++g_droppedRing;  // sampel tertua tertimpa
  }
}

// ===========================================================================
// HTTP
// ===========================================================================

enum class SendResult : uint8_t { Ok, Retry, Drop, AuthError, TooLarge };

static SendResult classifyHttp(int code) {
  if (code >= 200 && code < 300) return SendResult::Ok;
  if (code == 401 || code == 403) return SendResult::AuthError;
  if (code == 413) return SendResult::TooLarge;
  if (code == 400 || code == 422) return SendResult::Drop;  // data ditolak permanen
  return SendResult::Retry;  // <0 (koneksi), 404, 408, 429, 5xx
}

static int httpPostJson(const char* path, const char* body, size_t len) {
  String url(g_apiBase);
  url += path;
  HTTPClient http;
  bool ok;
  if (strncmp(g_apiBase, "https://", 8) == 0) {
    ok = http.begin(g_secureClient, url);
  } else {
    ok = http.begin(g_plainClient, url);
  }
  if (!ok) return -1;
  http.setReuse(true);
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", g_deviceKey);
  http.addHeader("User-Agent", "WASKITA-sensor/" WASKITA_FW_VERSION);
  const int code = http.POST((uint8_t*)body, len);
  if (code >= 400) {
    String resp = http.getString();
    if (resp.length() > 200) resp = resp.substring(0, 200);
    Serial.printf("[http] %s -> %d %s\n", path, code, resp.c_str());
  } else if (code < 0) {
    Serial.printf("[http] %s -> gagal: %s\n", path, HTTPClient::errorToString(code).c_str());
  }
  http.end();
  return code;
}

// Bangun body /ingest-batch dari g_scratch[0..m) (time_ms = epoch ms).
static size_t buildBatchJson(size_t m) {
  int w = snprintf(g_json, g_jsonCap, "{\"device_id\":\"%s\",\"samples\":[", g_deviceId);
  if (w < 0 || (size_t)w >= g_jsonCap) return 0;
  size_t pos = (size_t)w;
  for (size_t k = 0; k < m; ++k) {
    char iso[40];
    if (!waskita::formatIso8601(g_scratch[k].time_ms, TZ_OFFSET_SECONDS, iso, sizeof(iso))) return 0;
    if (k > 0) {
      if (pos + 1 >= g_jsonCap) return 0;
      g_json[pos++] = ',';
    }
    const size_t n = waskita::formatSampleJson(g_json + pos, g_jsonCap - pos, nullptr, iso, g_scratch[k]);
    if (n == 0) return 0;
    pos += n;
  }
  if (pos + 3 > g_jsonCap) return 0;
  g_json[pos++] = ']';
  g_json[pos++] = '}';
  g_json[pos] = '\0';
  return pos;
}

static SendResult postBatch(size_t m) {
  const size_t len = buildBatchJson(m);
  if (len == 0) return SendResult::TooLarge;
  return classifyHttp(httpPostJson(API_PATH_INGEST_BATCH, g_json, len));
}

static SendResult postSingle(const TelemetrySample& s) {
  char iso[40];
  if (!waskita::formatIso8601(uptimeToEpochMs(s.time_ms), TZ_OFFSET_SECONDS, iso, sizeof(iso))) {
    return SendResult::Drop;
  }
  const size_t len = waskita::formatSampleJson(g_json, g_jsonCap, g_deviceId, iso, s);
  if (len == 0) return SendResult::Drop;
  return classifyHttp(httpPostJson(API_PATH_INGEST, g_json, len));
}

// Kirim satu potong spool (sampel paling tua). Return hasil + jumlah sampel.
static SendResult sendSpoolChunk(size_t* consumed) {
  *consumed = 0;
#if ENABLE_LITTLEFS_SPOOL
  const size_t rec = sizeof(TelemetrySample);
  size_t want = (g_spoolBytes - g_spoolReadOffset) / rec;
  if (want > g_batchLimit) want = g_batchLimit;
  File f = LittleFS.open(SPOOL_PATH, "r");
  if (!f || !f.seek(g_spoolReadOffset)) {
    if (f) f.close();
    Serial.println(F("[spool] file tidak terbaca - spool dihapus"));
    spoolClear();
    return SendResult::Drop;
  }
  const size_t got = f.read((uint8_t*)g_scratch, want * rec) / rec;
  f.close();
  if (got == 0) {
    spoolClear();
    return SendResult::Drop;
  }
  *consumed = got;
  return postBatch(got);
#else
  return SendResult::Retry;
#endif
}

static void consumeSpool(size_t n) {
  g_spoolReadOffset += (uint32_t)(n * sizeof(TelemetrySample));
  if (g_spoolReadOffset >= g_spoolBytes) {
    spoolClear();
  } else {
    saveSpoolOffset();
  }
}

static void scheduleRetry() {
  g_backoffMs = g_backoffMs == 0 ? BACKOFF_MIN_MS : g_backoffMs * 2;
  if (g_backoffMs > BACKOFF_MAX_MS) g_backoffMs = BACKOFF_MAX_MS;
  g_nextAttemptMs = millis() + g_backoffMs;
}

static void uplinkStep() {
  if (g_otaInProgress || !configComplete() || g_wm.getConfigPortalActive()) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if (!timeReached(millis(), g_nextAttemptMs)) return;

  SendResult res;
  size_t n = 0;
  bool fromSpool = false;

  if (spoolHasData()) {
    // Spool berisi data paling tua (dan sudah ber-epoch) -> kirim dulu.
    fromSpool = true;
    res = sendSpoolChunk(&n);
  } else {
    if (!g_timeSynced || g_ring.empty()) return;
    const size_t backlog = g_ring.size();
    if (backlog == 1) {
      n = 1;
      res = postSingle(g_ring.at(0));
    } else {
      n = backlog < g_batchLimit ? backlog : g_batchLimit;
      for (size_t k = 0; k < n; ++k) {
        g_scratch[k] = g_ring.at(k);
        g_scratch[k].time_ms = uptimeToEpochMs(g_scratch[k].time_ms);
      }
      res = postBatch(n);
    }
  }

  switch (res) {
    case SendResult::Ok:
      if (fromSpool) consumeSpool(n); else g_ring.popFront(n);
      g_sentSamples += (uint32_t)n;
      g_backoffMs = 0;
      g_nextAttemptMs = millis();
      g_authError = false;
      g_lastSendFailed = false;
      break;
    case SendResult::Drop:
      Serial.printf("[uplink] %u sampel ditolak server (400/422) dan dibuang\n", (unsigned)n);
      if (fromSpool) consumeSpool(n); else g_ring.popFront(n);
      g_droppedRejected += (uint32_t)n;
      g_lastSendFailed = true;
      break;
    case SendResult::TooLarge:
      if (g_batchLimit > 1) {
        g_batchLimit /= 2;
        Serial.printf("[uplink] batch terlalu besar - diturunkan ke %u\n", (unsigned)g_batchLimit);
      } else {
        if (fromSpool) consumeSpool(n); else g_ring.popFront(n);
        ++g_droppedRejected;
      }
      g_lastSendFailed = true;
      break;
    case SendResult::AuthError:
      if (!g_authError) {
        Serial.println(F("[uplink] 401/403: device key salah atau perangkat belum diregistrasi. "
                         "Data tetap disimpan. Tahan tombol 5 detik untuk membuka portal lagi."));
      }
      g_authError = true;
      g_lastSendFailed = true;
      ++g_failedPosts;
      g_backoffMs = BACKOFF_MAX_MS;
      g_nextAttemptMs = millis() + g_backoffMs;
      break;
    case SendResult::Retry:
    default:
      g_lastSendFailed = true;
      ++g_failedPosts;
      scheduleRetry();
      break;
  }
}

// ===========================================================================
// WiFi, portal, OTA
// ===========================================================================

static void startOta() {
#if ENABLE_OTA
  if (g_otaStarted) return;
  if (strlen(OTA_PASSWORD) < 8) {
    Serial.println(F("[ota] OTA_PASSWORD kosong/< 8 karakter - OTA nonaktif"));
    g_otaStarted = true;  // jangan dicoba lagi
    return;
  }
  ArduinoOTA.setHostname(g_hostname);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() {
    g_otaInProgress = true;
    Serial.println(F("[ota] mulai - memindahkan buffer RAM ke flash"));
    while (!g_ring.empty() && spillOldestToSpool(SPOOL_CHUNK) > 0) {
    }
  });
  ArduinoOTA.onProgress([](unsigned int, unsigned int) { esp_task_wdt_reset(); });
  ArduinoOTA.onEnd([]() { Serial.println(F("[ota] selesai, reboot")); });
  ArduinoOTA.onError([](ota_error_t e) {
    g_otaInProgress = false;
    Serial.printf("[ota] gagal (%u)\n", (unsigned)e);
  });
  ArduinoOTA.begin();
  g_otaStarted = true;
  Serial.printf("[ota] siap: %s.local\n", g_hostname);
#endif
}

static void onNetworkUp() {
  if (g_netStarted) return;
  g_netStarted = true;
  configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2, NTP_SERVER_3);  // UTC; offset WIB saat format
  if (strlen(WASKITA_ROOT_CA) > 0) {
    g_secureClient.setCACert(WASKITA_ROOT_CA);
  } else {
    g_secureClient.setInsecure();
  }
  startOta();
}

static void startPortal() {
  if (g_wm.getConfigPortalActive()) return;
  Serial.printf("[portal] membuka AP \"%s\" - sambungkan HP lalu buka http://192.168.4.1\n", g_apName);
  const char* pass = strlen(PORTAL_AP_PASSWORD) >= 8 ? PORTAL_AP_PASSWORD : nullptr;
  g_wm.startConfigPortal(g_apName, pass);
}

static void maintainWiFi() {
  const bool portal = g_wm.getConfigPortalActive();
  if (g_portalWasActive && !portal) g_portalClosedMs = millis();
  g_portalWasActive = portal;
  if (portal) return;

  const uint32_t now = millis();
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected) onNetworkUp();
  // Konfigurasi belum lengkap (mis. device key kosong) / WiFi belum pernah
  // disimpan -> buka portal lagi (jeda 10 detik setelah portal tertutup).
  if ((!configComplete() || (!connected && !g_wm.getWiFiIsSaved())) &&
      now - g_portalClosedMs > 10000UL) {
    startPortal();
    return;
  }
  if (connected) return;
  if (now - g_lastReconnectMs >= WIFI_RECONNECT_INTERVAL_MS) {
    g_lastReconnectMs = now;
    Serial.println(F("[wifi] terputus - mencoba sambung ulang"));
    WiFi.reconnect();
  }
}

static void setupWiFi() {
  uint8_t mac[6] = {0};
  readMac(mac);
  snprintf(g_apName, sizeof(g_apName), "%s%02X%02X", PORTAL_AP_PREFIX, mac[4], mac[5]);
  snprintf(g_hostname, sizeof(g_hostname), "waskita-%02x%02x%02x", mac[3], mac[4], mac[5]);
  WiFi.setHostname(g_hostname);  // harus sebelum WiFi.mode() di core 2.x
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
}

static void setupPortal() {
  g_paramApi.setValue(g_apiBase, 128);
  g_paramDevId.setValue(g_deviceId, 64);
  g_paramDevKey.setValue("", 128);  // key lama tidak pernah ditampilkan
  g_wm.addParameter(&g_paramApi);
  g_wm.addParameter(&g_paramDevId);
  g_wm.addParameter(&g_paramDevKey);
  g_wm.setSaveParamsCallback(onPortalParamsSaved);
  g_wm.setConfigPortalBlocking(false);
  g_wm.setConfigPortalTimeout(PORTAL_TIMEOUT_S);
  g_wm.setConnectTimeout(WIFI_CONNECT_TIMEOUT_S);
  g_wm.setTitle("WASKITA");
  g_wm.setHostname(g_hostname);
  // Tanpa menu "update": unggah firmware lewat portal tidak berpassword.
  std::vector<const char*> menu = {"wifi", "info", "exit"};
  g_wm.setMenu(menu);

  const char* pass = strlen(PORTAL_AP_PASSWORD) >= 8 ? PORTAL_AP_PASSWORD : nullptr;
  if (!pass) Serial.println(F("[portal] PERINGATAN: AP portal tanpa password"));
  if (configComplete()) {
    if (g_wm.autoConnect(g_apName, pass)) {
      Serial.printf("[wifi] tersambung ke \"%s\" IP %s\n", WiFi.SSID().c_str(),
                    WiFi.localIP().toString().c_str());
    }
  } else {
    Serial.println(F("[portal] konfigurasi belum lengkap (URL server / device key)"));
    startPortal();
  }
}

// ===========================================================================
// Tombol reset konfigurasi
// ===========================================================================

static void factoryResetConfig() {
  Serial.println(F("[reset] menghapus WiFi, URL server, device key, dan spool. Kalibrasi DIPERTAHANKAN."));
  digitalWrite(PIN_STATUS_LED, STATUS_LED_ACTIVE_HIGH ? HIGH : LOW);
  g_prefs.begin(kPrefsNs, false);
  g_prefs.remove("api_base");
  g_prefs.remove("dev_id");
  g_prefs.remove("dev_key");
  g_prefs.end();
  spoolClear();
  g_wm.resetSettings();
  delay(500);
  ESP.restart();
}

static void handleButton() {
  const bool pressed = digitalRead(PIN_CONFIG_BUTTON) == LOW;
  const uint32_t now = millis();
  if (!pressed) {
    g_btnDown = false;
    return;
  }
  if (!g_btnDown) {
    g_btnDown = true;
    g_btnSinceMs = now;
    return;
  }
  if (now - g_btnSinceMs >= CONFIG_BUTTON_HOLD_MS) factoryResetConfig();
}

// ===========================================================================
// LED status
// ===========================================================================

static void updateLedState() {
  if (g_btnDown && millis() - g_btnSinceMs > 1000UL) {
    g_ledState = LedState::ResetPending;
  } else if (g_wm.getConfigPortalActive()) {
    g_ledState = LedState::Portal;
  } else if (!configComplete() || g_authError) {
    g_ledState = LedState::ConfigError;
  } else if (WiFi.status() != WL_CONNECTED || !g_timeSynced) {
    g_ledState = LedState::Connecting;
  } else if (g_lastSendFailed || g_ring.size() > 5 || spoolHasData()) {
    g_ledState = LedState::Buffering;
  } else {
    g_ledState = LedState::Online;
  }
}

static void updateLed() {
  // Pola: durasi bergantian nyala, mati, nyala, mati, ... (ms).
  static const uint16_t kPortal[] = {100, 100};
  static const uint16_t kConnecting[] = {500, 500};
  static const uint16_t kOnline[] = {60, 1940};
  static const uint16_t kBuffering[] = {150, 150, 150, 1550};
  static const uint16_t kConfigError[] = {150, 150, 150, 150, 150, 1250};
  const uint16_t* steps = nullptr;
  size_t n = 0;
  bool on = false;
  switch (g_ledState) {
    case LedState::Boot:
    case LedState::ResetPending:
      on = true;
      break;
    case LedState::Portal: steps = kPortal; n = 2; break;
    case LedState::Connecting: steps = kConnecting; n = 2; break;
    case LedState::Online: steps = kOnline; n = 2; break;
    case LedState::Buffering: steps = kBuffering; n = 4; break;
    case LedState::ConfigError: steps = kConfigError; n = 6; break;
  }
  if (steps) {
    uint32_t total = 0;
    for (size_t k = 0; k < n; ++k) total += steps[k];
    uint32_t t = millis() % total;
    for (size_t k = 0; k < n; ++k) {
      if (t < steps[k]) {
        on = (k % 2) == 0;
        break;
      }
      t -= steps[k];
    }
  }
  const bool level = STATUS_LED_ACTIVE_HIGH ? on : !on;
  digitalWrite(PIN_STATUS_LED, level ? HIGH : LOW);
}

// ===========================================================================
// Perintah serial (kalibrasi & diagnosa) - 115200 baud, akhiri dengan Enter
// ===========================================================================

static void printHelp() {
  Serial.println(F(
      "Perintah:\n"
      "  status            ringkasan pengukuran & antrean\n"
      "  cal show          tampilkan konstanta kalibrasi\n"
      "  cal v <volt>      kalibrasi tegangan dengan pembacaan multimeter (mis. cal v 228.4)\n"
      "  cal i <ampere>    kalibrasi arus dengan tang ampere (beban >= 2 A, mis. cal i 4.35)\n"
      "  cal phase         kalibrasi fase otomatis (HANYA saat beban resistif murni >= 2 A menyala)\n"
      "  cal phase <nilai> set PHASE_CAL manual\n"
      "  cal reset         kembalikan kalibrasi default dari config.h\n"
      "  config            tampilkan URL server & ID perangkat\n"
      "  portal            buka portal konfigurasi WiFi\n"
      "  reboot            simpan buffer ke flash lalu restart"));
}

static void printStatus() {
  const LiveView lv = currentLive();
  Serial.printf("V=%.1f V  I=%.3f A  P=%.1f W  Q=%.1f VAR  PF=%.3f  f=%.3f Hz%s  fasa=%.2f deg\n",
                lv.v_rms, lv.i_rms, lv.p_active, lv.q_reactive, lv.power_factor, lv.frequency_hz,
                lv.freq_valid ? "" : " (nominal)", lv.phase_deg);
  Serial.printf("fs=%.0f Hz  jendela=%u  jendela_lambat=%u\n", lv.sample_rate_hz,
                (unsigned)lv.windows, (unsigned)g_slowSamplingWindows);
  Serial.printf("WiFi=%s  NTP=%s  server=%s  auth=%s\n",
                WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "putus",
                g_timeSynced ? "ok" : "belum", g_apiBase[0] ? g_apiBase : "(kosong)",
                g_authError ? "DITOLAK" : "ok");
  Serial.printf("antrean RAM=%u/%u  spool=%u  terkirim=%u  gagal_post=%u  dibuang(penuh)=%u  "
                "ditolak=%u  queue_drop=%u  detik_P_negatif=%u\n",
                (unsigned)g_ring.size(), (unsigned)g_ring.capacity(),
                (unsigned)(g_spoolOk ? (g_spoolBytes - g_spoolReadOffset) / sizeof(TelemetrySample) : 0),
                (unsigned)g_sentSamples, (unsigned)g_failedPosts, (unsigned)g_droppedRing,
                (unsigned)g_droppedRejected, (unsigned)g_droppedQueue, (unsigned)g_reverseTotal);
  Serial.printf("heap bebas=%u  firmware=%s\n", (unsigned)ESP.getFreeHeap(), WASKITA_FW_VERSION);
}

static void printCal() {
  const Calibration c = currentCalibration();
  Serial.printf("V_CAL=%.3f  I_CAL=%.3f  PHASE_CAL=%.4f  (CT_TYPE=%d, CT_INVERT=%d)\n", c.v_cal,
                c.i_cal, c.phase_cal, (int)CT_TYPE, (int)CT_INVERT);
}

static void handleCommand(char* line) {
  trimInPlace(line);
  if (line[0] == '\0') return;
  char* save = nullptr;
  char* cmd = strtok_r(line, " ", &save);
  char* a1 = strtok_r(nullptr, " ", &save);
  char* a2 = strtok_r(nullptr, " ", &save);

  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "?") == 0) {
    printHelp();
  } else if (strcmp(cmd, "status") == 0) {
    printStatus();
  } else if (strcmp(cmd, "config") == 0) {
    Serial.printf("server=%s  device_id=%s  device_key=%s  AP=%s  host=%s\n",
                  g_apiBase[0] ? g_apiBase : "(kosong)", g_deviceId,
                  g_deviceKey[0] ? "(terisi)" : "(KOSONG)", g_apName, g_hostname);
  } else if (strcmp(cmd, "portal") == 0) {
    startPortal();
  } else if (strcmp(cmd, "reboot") == 0) {
    Serial.println(F("[reboot] memindahkan buffer RAM ke flash..."));
    while (!g_ring.empty() && spillOldestToSpool(SPOOL_CHUNK) > 0) {
    }
    delay(200);
    ESP.restart();
  } else if (strcmp(cmd, "cal") == 0 && a1) {
    Calibration c = currentCalibration();
    const LiveView lv = currentLive();
    if (strcmp(a1, "show") == 0) {
      printCal();
    } else if (strcmp(a1, "reset") == 0) {
      c.v_cal = V_CAL_DEFAULT;
      c.i_cal = I_CAL_DEFAULT;
      c.phase_cal = PHASE_CAL_DEFAULT;
      saveCalibration(c);
      printCal();
    } else if (strcmp(a1, "v") == 0 && a2) {
      const float ref = (float)strtod(a2, nullptr);
      if (!(ref > 50.0f) || !(lv.v_rms > 10.0f)) {
        Serial.println(F("[cal] gagal: tegangan referensi atau terukur terlalu kecil"));
      } else {
        c.v_cal *= ref / lv.v_rms;
        saveCalibration(c);
        Serial.printf("[cal] V_CAL baru = %.3f (terukur %.2f V -> %.2f V)\n", c.v_cal, lv.v_rms, ref);
      }
    } else if (strcmp(a1, "i") == 0 && a2) {
      const float ref = (float)strtod(a2, nullptr);
      if (!(ref >= 0.5f) || !(lv.i_rms > 0.2f)) {
        Serial.println(F("[cal] gagal: pakai beban >= 2 A agar derau tidak dominan"));
      } else {
        c.i_cal *= ref / lv.i_rms;
        saveCalibration(c);
        Serial.printf("[cal] I_CAL baru = %.3f (terukur %.3f A -> %.3f A)\n", c.i_cal, lv.i_rms, ref);
      }
    } else if (strcmp(a1, "phase") == 0) {
      if (a2) {
        const float v = (float)strtod(a2, nullptr);
        if (isfinite(v) && v > -5.0f && v < 5.0f) {
          c.phase_cal = v;
          saveCalibration(c);
          printCal();
        } else {
          Serial.println(F("[cal] PHASE_CAL di luar rentang wajar (-5..5)"));
        }
      } else if (!(lv.i_rms >= 1.0f) || !lv.freq_valid) {
        Serial.println(F("[cal] gagal: butuh beban resistif >= 1 A dan tegangan terukur"));
      } else {
        c.phase_cal = waskita::phaseCalFromResistiveLoad(lv.phase_deg, lv.frequency_hz,
                                                         lv.sample_rate_hz, c.phase_cal);
        saveCalibration(c);
        Serial.printf("[cal] fasa terukur %.2f deg -> PHASE_CAL baru = %.4f. "
                      "Tunggu 5 detik lalu cek 'status': PF harus ~1.00.\n",
                      lv.phase_deg, c.phase_cal);
      }
    } else {
      printHelp();
    }
  } else {
    printHelp();
  }
}

static void handleSerial() {
  static char buf[96];
  static size_t len = 0;
  while (Serial.available() > 0) {
    const int ch = Serial.read();
    if (ch < 0) break;
    if (ch == '\n' || ch == '\r') {
      if (len > 0) {
        buf[len] = '\0';
        handleCommand(buf);
        len = 0;
      }
    } else if (len + 1 < sizeof(buf)) {
      buf[len++] = (char)ch;
    }
  }
}

// ===========================================================================
// Alokasi buffer
// ===========================================================================

static void allocateBuffers() {
  size_t cap = RING_CAPACITY;
  TelemetrySample* storage = nullptr;
  while (cap >= RING_CAPACITY_MIN) {
    storage = (TelemetrySample*)malloc(cap * sizeof(TelemetrySample));
    if (storage) break;
    cap /= 2;
  }
  g_ring.attach(storage, storage ? cap : 0);
  g_scratch = (TelemetrySample*)malloc(BATCH_MAX * sizeof(TelemetrySample));
  g_jsonCap = (size_t)BATCH_MAX * JSON_BYTES_PER_SAMPLE + 256;
  g_json = (char*)malloc(g_jsonCap);
  if (!g_scratch || !g_json) {
    Serial.println(F("[fatal] heap tidak cukup untuk buffer kirim - restart"));
    delay(2000);
    ESP.restart();
  }
  Serial.printf("[buffer] ring RAM %u sampel (%u menit)\n", (unsigned)g_ring.capacity(),
                (unsigned)(g_ring.capacity() * SAMPLE_PERIOD_MS / 60000UL));
}

// ===========================================================================
// setup() / loop()
// ===========================================================================

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n=== WASKITA kotak sensor v%s ===\n", WASKITA_FW_VERSION);

  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_CONFIG_BUTTON, INPUT_PULLUP);
  g_ledState = LedState::Boot;
  updateLed();

  setupWatchdog();
  allocateBuffers();

  setupWiFi();  // perlu MAC untuk ID default
  loadConfig();
  printCal();
  setupSpool();

  setupAdc();
  g_sampleQueue = xQueueCreate(SAMPLE_QUEUE_DEPTH, sizeof(TelemetrySample));
  if (!g_sampleQueue) {
    Serial.println(F("[fatal] queue gagal dibuat - restart"));
    delay(2000);
    ESP.restart();
  }
  // Pengukuran jalan terus, terlepas dari status jaringan.
  xTaskCreatePinnedToCore(measurementTask, "waskita_meas", 6144, nullptr, 2, &g_measTask, 1);

  setupPortal();
  Serial.printf("device_id=%s  ketik 'help' untuk perintah serial\n", g_deviceId);
}

void loop() {
  esp_task_wdt_reset();
  g_wm.process();
  handleButton();
  handleSerial();
  drainQueueToRing();
  maintainWiFi();
  maintainTime();
#if ENABLE_OTA
  if (g_otaStarted) ArduinoOTA.handle();
#endif
  uplinkStep();
  updateLedState();
  updateLed();
  delay(10);
}
