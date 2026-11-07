// WASKITA - konfigurasi build firmware kotak sensor.
//
// File ini berisi konstanta yang AMAN di-commit (tanpa rahasia). Rahasia
// build ada di include/secrets.h (salin dari secrets.example.h).
// SSID/password WiFi, URL server, ID dan key perangkat diisi lewat portal
// WiFiManager, bukan di sini.
#pragma once

#if defined(__has_include)
#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "include/secrets.h tidak ada - memakai secrets.example.h (password portal default!)"
#include "secrets.example.h"
#endif
#else
#include "secrets.h"
#endif

#ifndef WASKITA_FW_VERSION
#define WASKITA_FW_VERSION "0.1.0"
#endif

// ===========================================================================
// Pin (ESP32 DevKit / board esp32dev)
// ===========================================================================
// WAJIB ADC1 (GPIO32..39): ADC2 tidak bisa dipakai saat WiFi aktif.
// GPIO34/35 adalah input-only, cocok untuk ADC.
#define PIN_ADC_CURRENT 34   // SCT-013 (lewat rangkaian bias 1.65 V) -> ADC1_CH6
#define PIN_ADC_VOLTAGE 35   // ZMPT101B OUT -> ADC1_CH7
#define PIN_STATUS_LED 2     // LED biru onboard DevKit
#define STATUS_LED_ACTIVE_HIGH 1
#define PIN_CONFIG_BUTTON 0  // tombol BOOT onboard (aktif LOW)
#define CONFIG_BUTTON_HOLD_MS 5000UL

// ===========================================================================
// Sensor arus SCT-013
// ===========================================================================
#define CT_TYPE_CURRENT_OUTPUT 1  // SCT-013-000 100 A : 50 mA, perlu resistor burden
#define CT_TYPE_VOLTAGE_OUTPUT 2  // SCT-013-030 30 A / 1 V (burden internal)

#ifndef CT_TYPE
#define CT_TYPE CT_TYPE_CURRENT_OUTPUT
#endif

// Untuk CT_TYPE_CURRENT_OUTPUT. Burden 33 ohm -> 35 A RMS = +/-0.82 V puncak
// di sekitar bias 1.65 V (masih di daerah linear ADC ESP32 pada atenuasi
// 11 dB, kira-kira 0.15..2.45 V). Untuk sambungan > 7700 VA pakai burden
// lebih kecil (mis. 22 ohm -> ~52 A).
#define CT_TURNS_RATIO 2000.0f
#define CT_BURDEN_OHMS 33.0f
// Untuk CT_TYPE_VOLTAGE_OUTPUT: ampere per volt keluaran (30 A / 1 V = 30).
// Catatan: 1 V RMS = 1.41 V puncak, melewati daerah linear ADC; versi 30 A/1V
// praktis akurat sampai ~17 A RMS saja.
#define CT_RATED_AMPS_PER_VOLT 30.0f

#if CT_TYPE == CT_TYPE_CURRENT_OUTPUT
#define I_CAL_DEFAULT (CT_TURNS_RATIO / CT_BURDEN_OHMS)
#elif CT_TYPE == CT_TYPE_VOLTAGE_OUTPUT
#define I_CAL_DEFAULT (CT_RATED_AMPS_PER_VOLT)
#else
#error "CT_TYPE tidak dikenal"
#endif

// 1 = balik tanda arus (bila CT terpasang terbalik dan tidak mau dibuka lagi).
#define CT_INVERT 0

// ===========================================================================
// Sensor tegangan ZMPT101B + kalibrasi
// ===========================================================================
// Nilai awal saja. V_CAL bergantung posisi trimpot modul ZMPT101B, jadi
// WAJIB dikalibrasi (perintah serial "cal v <volt>"). Hasil kalibrasi
// disimpan di NVS dan menimpa nilai di bawah.
#define V_CAL_DEFAULT 500.0f
#define PHASE_CAL_DEFAULT 1.0f

// ===========================================================================
// ADC & sampling
// ===========================================================================
#define ADC_VREF_VOLTS 3.3f
#define ADC_MAX_COUNTS 4095.0f
#define ADC_VOLTS_PER_COUNT (ADC_VREF_VOLTS / ADC_MAX_COUNTS)
// Titik tengah bias (pembagi 2 x 10k dari 3V3). Hanya informasi: offset DC
// dihapus numerik di perangkat lunak.
#define ADC_BIAS_VOLTS 1.65f

#define MAINS_NOMINAL_HZ 50.0f
// Laju pasangan sampel (V lalu I) per detik. >= 2 kHz; 4 kHz = 80 sampel per
// siklus 50 Hz.
#define SAMPLE_RATE_HZ 4000
// Jumlah siklus penuh yang dihitung per jendela (10 siklus = 200 ms).
#define WINDOW_CYCLES 10
// Jendela per sampel telemetri (1 sampel/detik).
#define WINDOWS_PER_SAMPLE 2
#define SAMPLE_PERIOD_MS 1000
#define WINDOW_PERIOD_MS (SAMPLE_PERIOD_MS / WINDOWS_PER_SAMPLE)
// Buffer menangkap 2 siklus ekstra untuk mencari zero-crossing dan ruang
// pergeseran fasa.
#define CAPTURE_SAMPLES ((WINDOW_CYCLES + 2) * (SAMPLE_RATE_HZ / 50))

// Irms di bawah ini dianggap 0 (derau ADC 12-bit ESP32 + CT 100 A).
#define I_NOISE_FLOOR_A 0.08f
// Vrms minimum agar frekuensi dianggap terukur.
#define V_MIN_FOR_FREQ_V 100.0f
#define MIN_HYSTERESIS_COUNTS 4.0f

// ===========================================================================
// Pengiriman ke backend
// ===========================================================================
// Default URL di portal (boleh kosong). Contoh: "http://192.168.1.10:8000"
#define DEFAULT_API_BASE ""
#define API_PATH_INGEST "/api/v1/telemetry/ingest"
#define API_PATH_INGEST_BATCH "/api/v1/telemetry/ingest-batch"
// Prefiks device_id default (ditambah 6 digit hex MAC). Harus sama dengan
// device_id yang diregistrasi di backend.
#define DEVICE_ID_PREFIX "WSK-"

#define HTTP_CONNECT_TIMEOUT_MS 3000
#define HTTP_TIMEOUT_MS 5000
// Kontrak backend: maks. 500 sampel per batch. Dipakai lebih kecil agar
// buffer JSON (~190 byte/sampel) tetap muat di heap.
#define BATCH_MAX 120
#define BATCH_HARD_LIMIT 500
#define JSON_BYTES_PER_SAMPLE 192
#define BACKOFF_MIN_MS 2000UL
#define BACKOFF_MAX_MS 60000UL

// Ring buffer RAM (32 byte/sampel). 1800 = 30 menit offline.
#define RING_CAPACITY 1800
#define RING_CAPACITY_MIN 120
#define SAMPLE_QUEUE_DEPTH 64

// Spool LittleFS (opsional) bila RAM penuh saat offline lama.
#define ENABLE_LITTLEFS_SPOOL 1
#define SPOOL_PATH "/spool.bin"
#define SPOOL_MAX_BYTES (512UL * 1024UL)   // ~16 ribu sampel = ~4,5 jam
#define SPOOL_CHUNK 300                     // dipindah dari RAM per tulis

// ===========================================================================
// Waktu (NTP)
// ===========================================================================
#define NTP_SERVER_1 "id.pool.ntp.org"
#define NTP_SERVER_2 "pool.ntp.org"
#define NTP_SERVER_3 "time.google.com"
// WIB = UTC+7. Timestamp dikirim sebagai ISO 8601 "+07:00".
#define TZ_OFFSET_SECONDS (7 * 3600)
// Epoch minimum yang dianggap "jam sudah sinkron" (2024-01-01).
#define MIN_VALID_EPOCH 1704067200L

// ===========================================================================
// WiFi, portal, OTA, watchdog
// ===========================================================================
#define PORTAL_AP_PREFIX "WASKITA-"
#define PORTAL_TIMEOUT_S 300
#define WIFI_CONNECT_TIMEOUT_S 20
#define WIFI_RECONNECT_INTERVAL_MS 30000UL
#define ENABLE_OTA 1
// > waktu blok terlama loop(): autoConnect saat boot (~20 s) / HTTP (~8 s).
#define WDT_TIMEOUT_S 60

// ===========================================================================
// Pemeriksaan saat kompilasi
// ===========================================================================
static_assert(SAMPLE_RATE_HZ >= 2000, "SAMPLE_RATE_HZ minimal 2 kHz");
static_assert(SAMPLE_RATE_HZ % 50 == 0, "SAMPLE_RATE_HZ harus kelipatan 50");
static_assert(WINDOW_CYCLES >= 2 && WINDOW_CYCLES <= 50, "WINDOW_CYCLES 2..50");
static_assert(BATCH_MAX >= 1 && BATCH_MAX <= BATCH_HARD_LIMIT,
              "BATCH_MAX harus 1..500 (kontrak backend)");
static_assert((WINDOW_CYCLES + 2) * 20 * WINDOWS_PER_SAMPLE <= 700,
              "Waktu sampling per detik terlalu lama; loop() butuh CPU untuk jaringan");
static_assert(SAMPLE_PERIOD_MS % WINDOWS_PER_SAMPLE == 0,
              "SAMPLE_PERIOD_MS harus habis dibagi WINDOWS_PER_SAMPLE");
