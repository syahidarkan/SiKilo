// Uji unit lib/waskita_core dengan gelombang sintetis (pio test -e native).
// Sinyal dibangkitkan seperti yang dilihat ADC ESP32: bias 1.65 V, 12 bit,
// dibulatkan ke count terdekat; sampel arus diambil sesudah sampel tegangan.

#include <math.h>
#include <stdint.h>
#include <string.h>
#include <unity.h>

#include "power_calc.h"
#include "sample_ring.h"
#include "telemetry_format.h"

using namespace waskita;

namespace {

const double kPi = 3.14159265358979323846;
const float kVpc = 3.3f / 4095.0f;
const int kFs = 4000;
const size_t kN = 960;  // 12 siklus @ 50 Hz

uint16_t g_v[kN];
uint16_t g_i[kN];

// Kalibrasi "benar" untuk sinyal sintetis: 230 V RMS <-> 0.42 V RMS di pin.
const float kVcal = 230.0f / 0.42f;
const float kIcal = 2000.0f / 33.0f;  // SCT-013-000 + burden 33 ohm

struct Wave {
  double v_rms = 230.0;
  double i_rms = 10.0;
  double phi_deg = 0.0;      // + = arus tertinggal (induktif)
  double freq = 50.0;
  double i_delay_us = 0.0;   // keterlambatan baca arus terhadap tegangan
  double v_bias = 1.65;
  double i_bias = 1.63;
  double i_h3_frac = 0.0;    // amplitudo harmonisa ke-3 relatif
  double start_phase = 0.3;
};

uint16_t toCounts(double volts) {
  double c = floor(volts / 3.3 * 4095.0 + 0.5);
  if (c < 0) c = 0;
  if (c > 4095) c = 4095;
  return (uint16_t)c;
}

void synth(const Wave& w) {
  const double vpk_pin = w.v_rms / kVcal * sqrt(2.0);
  const double ipk_pin = w.i_rms / kIcal * sqrt(2.0);
  const double om = 2.0 * kPi * w.freq;
  const double phi = w.phi_deg * kPi / 180.0;
  for (size_t k = 0; k < kN; ++k) {
    const double t = (double)k / kFs;
    const double ti = t + w.i_delay_us * 1e-6;
    g_v[k] = toCounts(w.v_bias + vpk_pin * sin(om * t + w.start_phase));
    const double i = ipk_pin * (sin(om * ti + w.start_phase - phi) +
                                w.i_h3_frac * sin(3.0 * (om * ti + w.start_phase)));
    g_i[k] = toCounts(w.i_bias + i);
  }
}

WindowConfig cfg() {
  WindowConfig c;
  c.sample_rate_hz = (float)kFs;
  c.nominal_freq_hz = 50.0f;
  c.target_cycles = 10;
  c.volts_per_count = kVpc;
  c.i_noise_floor_a = 0.08f;
  c.v_min_for_freq_v = 100.0f;
  c.min_hysteresis_counts = 4.0f;
  c.invert_current = false;
  return c;
}

Calibration cal(float phase_cal = 1.0f) {
  Calibration c;
  c.v_cal = kVcal;
  c.i_cal = kIcal;
  c.phase_cal = phase_cal;
  return c;
}

WindowResult run(const Wave& w, const WindowConfig& c, const Calibration& k) {
  synth(w);
  WindowResult r;
  TEST_ASSERT_TRUE(computeWindow(g_v, g_i, kN, c, k, &r));
  return r;
}

}  // namespace

void setUp() {}
void tearDown() {}

void test_resistive_load() {
  Wave w;
  const WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_FLOAT_WITHIN(230.0f * 0.01f, 230.0f, r.v_rms);
  TEST_ASSERT_FLOAT_WITHIN(10.0f * 0.01f, 10.0f, r.i_rms);
  TEST_ASSERT_FLOAT_WITHIN(2300.0f * 0.015f, 2300.0f, r.p_active);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.0f, r.power_factor);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 0.0f, r.phase_deg);
  TEST_ASSERT_TRUE(r.freq_valid);
  TEST_ASSERT_FLOAT_WITHIN(0.02f, 50.0f, r.frequency_hz);
  TEST_ASSERT_EQUAL_INT(10, r.cycles_used);
}

void test_inductive_load_positive_q() {
  Wave w;
  w.phi_deg = 30.0;
  const WindowResult r = run(w, cfg(), cal());
  const float s = 2300.0f;
  TEST_ASSERT_FLOAT_WITHIN(s * 0.02f, s * cosf(30.0f * 3.14159265f / 180.0f), r.p_active);
  TEST_ASSERT_FLOAT_WITHIN(s * 0.03f, s * 0.5f, r.q_reactive);
  TEST_ASSERT_FLOAT_WITHIN(0.02f, 0.866f, r.power_factor);
  TEST_ASSERT_FLOAT_WITHIN(1.5f, 30.0f, r.phase_deg);
}

void test_capacitive_load_negative_q() {
  Wave w;
  w.phi_deg = -40.0;
  const WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_TRUE(r.q_reactive < 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(2300.0f * 0.03f, -2300.0f * sinf(40.0f * 3.14159265f / 180.0f),
                           r.q_reactive);
  TEST_ASSERT_FLOAT_WITHIN(1.5f, -40.0f, r.phase_deg);
}

void test_frequency_off_nominal() {
  Wave w;
  w.freq = 49.6;
  WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_TRUE(r.freq_valid);
  TEST_ASSERT_FLOAT_WITHIN(0.02f, 49.6f, r.frequency_hz);
  TEST_ASSERT_FLOAT_WITHIN(230.0f * 0.01f, 230.0f, r.v_rms);

  w.freq = 50.4;
  r = run(w, cfg(), cal());
  TEST_ASSERT_FLOAT_WITHIN(0.02f, 50.4f, r.frequency_hz);
}

void test_dc_bias_is_removed() {
  Wave w;
  w.v_bias = 1.50;
  w.i_bias = 1.80;
  const WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_FLOAT_WITHIN(230.0f * 0.01f, 230.0f, r.v_rms);
  TEST_ASSERT_FLOAT_WITHIN(2300.0f * 0.015f, 2300.0f, r.p_active);
}

void test_noise_floor_zeroes_current() {
  Wave w;
  w.i_rms = 0.0;
  const WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_EQUAL_FLOAT(0.0f, r.i_rms);
  TEST_ASSERT_EQUAL_FLOAT(0.0f, r.p_active);
  TEST_ASSERT_EQUAL_FLOAT(0.0f, r.q_reactive);
  TEST_ASSERT_FLOAT_WITHIN(230.0f * 0.01f, 230.0f, r.v_rms);
}

void test_inverted_ct_gives_negative_p_and_sanitize_clamps() {
  WindowConfig c = cfg();
  c.invert_current = true;
  Wave w;
  const WindowResult r = run(w, c, cal());
  TEST_ASSERT_TRUE(r.p_active < -2000.0f);

  Aggregator agg;
  agg.add(r);
  agg.add(r);
  TelemetrySample s;
  TEST_ASSERT_TRUE(agg.finish(1234, 50.0f, &s));
  sanitizeForBackend(&s, defaultBackendLimits());
  TEST_ASSERT_EQUAL_FLOAT(0.0f, s.p_active);
  TEST_ASSERT_TRUE((s.flags & FLAG_REVERSE_POWER) != 0);
}

void test_no_voltage_frequency_invalid() {
  Wave w;
  w.v_rms = 0.0;
  const WindowResult r = run(w, cfg(), cal());
  TEST_ASSERT_FALSE(r.freq_valid);
  TEST_ASSERT_EQUAL_FLOAT(50.0f, r.frequency_hz);
  TEST_ASSERT_FLOAT_WITHIN(10.0f * 0.02f, 10.0f, r.i_rms);
}

void test_phase_calibration_from_resistive_load() {
  // Arus dibaca 40 us sesudah tegangan -> arus tampak mendahului ~0.72 deg.
  Wave w;
  w.i_delay_us = 40.0;
  const WindowResult before = run(w, cfg(), cal(1.0f));
  TEST_ASSERT_TRUE(before.phase_deg < -0.4f);
  const float pc = phaseCalFromResistiveLoad(before.phase_deg, before.frequency_hz,
                                             (float)kFs, 1.0f);
  // Seharusnya ~1 + 40us * 4000 Hz = 1.16
  TEST_ASSERT_FLOAT_WITHIN(0.03f, 1.16f, pc);
  const WindowResult after = run(w, cfg(), cal(pc));
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, after.phase_deg);
  TEST_ASSERT_FLOAT_WITHIN(0.002f, 1.0f, after.power_factor);
}

void test_harmonics_q_magnitude_includes_distortion() {
  Wave w;
  w.i_h3_frac = 0.3;  // beban non-linear (mis. adaptor/LED driver)
  const WindowResult r = run(w, cfg(), cal());
  // P hanya dari fundamental (tegangan sinus murni).
  TEST_ASSERT_FLOAT_WITHIN(2300.0f * 0.02f, 2300.0f, r.p_active);
  TEST_ASSERT_TRUE(r.s_apparent > r.p_active);
  TEST_ASSERT_TRUE(r.q_reactive >= 0.0f);
}

void test_aggregator_rms_and_mean() {
  WindowResult a = {};
  a.ok = true;
  a.v_rms = 220.0f;
  a.i_rms = 3.0f;
  a.p_active = 600.0f;
  a.q_reactive = 100.0f;
  a.frequency_hz = 49.9f;
  a.freq_valid = true;
  WindowResult b = a;
  b.i_rms = 4.0f;
  b.p_active = 800.0f;
  b.frequency_hz = 50.1f;
  Aggregator agg;
  agg.add(a);
  agg.add(b);
  TelemetrySample s;
  TEST_ASSERT_TRUE(agg.finish(5000, 50.0f, &s));
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, sqrtf((9.0f + 16.0f) / 2.0f), s.i_rms);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 700.0f, s.p_active);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 50.0f, s.frequency);
  TEST_ASSERT_TRUE((s.time_ms) == (int64_t)(5000));
}

void test_sanitize_limits() {
  TelemetrySample s = {};
  s.v_rms = 400.0f;
  s.i_rms = 250.0f;
  s.p_active = NAN;
  s.q_reactive = 1.0f;
  s.frequency = 55.0f;
  sanitizeForBackend(&s, defaultBackendLimits());
  TEST_ASSERT_EQUAL_FLOAT(300.0f, s.v_rms);
  TEST_ASSERT_EQUAL_FLOAT(200.0f, s.i_rms);
  TEST_ASSERT_EQUAL_FLOAT(0.0f, s.p_active);
  TEST_ASSERT_EQUAL_FLOAT(52.0f, s.frequency);
  TEST_ASSERT_TRUE((s.flags & FLAG_CLAMPED) != 0);
}

void test_iso8601_wib() {
  char buf[40];
  TEST_ASSERT_TRUE(formatIso8601(0, 7 * 3600, buf, sizeof(buf)) > 0);
  TEST_ASSERT_EQUAL_STRING("1970-01-01T07:00:00.000+07:00", buf);
  // 2026-11-07T05:34:56.789Z -> 12:34:56.789 WIB
  TEST_ASSERT_TRUE(formatIso8601(1794029696789LL, 7 * 3600, buf, sizeof(buf)) > 0);
  TEST_ASSERT_EQUAL_STRING("2026-11-07T12:34:56.789+07:00", buf);
  // 2024-02-29T23:30:00Z -> 2024-03-01T06:30 WIB (tahun kabisat, ganti bulan)
  TEST_ASSERT_TRUE(formatIso8601(1709249400000LL, 7 * 3600, buf, sizeof(buf)) > 0);
  TEST_ASSERT_EQUAL_STRING("2024-03-01T06:30:00.000+07:00", buf);
  TEST_ASSERT_EQUAL_UINT(0, formatIso8601(0, 0, buf, 10));
}

void test_sample_json() {
  TelemetrySample s = {};
  s.v_rms = 229.5f;
  s.i_rms = 1.25f;
  s.p_active = 280.0f;
  s.q_reactive = -12.5f;
  s.frequency = 50.0f;
  char buf[256];
  const char* ts = "2026-11-07T12:34:56.789+07:00";
  TEST_ASSERT_TRUE(formatSampleJson(buf, sizeof(buf), "WSK-ABC123", ts, s) > 0);
  TEST_ASSERT_EQUAL_STRING(
      "{\"device_id\":\"WSK-ABC123\",\"timestamp\":\"2026-11-07T12:34:56.789+07:00\","
      "\"v_rms\":229.50,\"i_rms\":1.250,\"p_active\":280.0,\"q_reactive\":-12.5,"
      "\"frequency\":50.000}",
      buf);
  TEST_ASSERT_TRUE(formatSampleJson(buf, sizeof(buf), nullptr, ts, s) > 0);
  TEST_ASSERT_NULL(strstr(buf, "device_id"));
  TEST_ASSERT_EQUAL_UINT(0, formatSampleJson(buf, 20, nullptr, ts, s));
}

void test_normalize_api_base_and_device_id() {
  char out[128];
  TEST_ASSERT_TRUE(normalizeApiBase("  http://192.168.1.10:8000/api/v1/ ", out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("http://192.168.1.10:8000", out);
  TEST_ASSERT_TRUE(normalizeApiBase("https://waskita.example.id/", out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("https://waskita.example.id", out);
  TEST_ASSERT_FALSE(normalizeApiBase("192.168.1.10:8000", out, sizeof(out)));
  TEST_ASSERT_FALSE(normalizeApiBase("http://", out, sizeof(out)));
  TEST_ASSERT_TRUE(isValidDeviceId("WSK-A1B2C3"));
  TEST_ASSERT_FALSE(isValidDeviceId(""));
  TEST_ASSERT_FALSE(isValidDeviceId("ada spasi"));
  TEST_ASSERT_FALSE(isValidDeviceId("kutip\""));
}

void test_ring_buffer_fifo_and_eviction() {
  TelemetrySample storage[4];
  SampleRing ring;
  ring.attach(storage, 4);
  TelemetrySample s = {};
  for (int k = 0; k < 4; ++k) {
    s.time_ms = k;
    TEST_ASSERT_FALSE(ring.push(s, nullptr));
  }
  TEST_ASSERT_TRUE(ring.full());
  TelemetrySample ev = {};
  s.time_ms = 4;
  TEST_ASSERT_TRUE(ring.push(s, &ev));
  TEST_ASSERT_TRUE((ev.time_ms) == (int64_t)(0));
  TEST_ASSERT_TRUE((ring.at(0).time_ms) == (int64_t)(1));
  TEST_ASSERT_TRUE((ring.at(3).time_ms) == (int64_t)(4));
  TEST_ASSERT_EQUAL_UINT(2, ring.popFront(2));
  TEST_ASSERT_EQUAL_UINT(2, ring.size());
  TEST_ASSERT_TRUE((ring.at(0).time_ms) == (int64_t)(3));
  s.time_ms = 5;
  ring.push(s, nullptr);
  TEST_ASSERT_TRUE((ring.at(2).time_ms) == (int64_t)(5));
  TEST_ASSERT_EQUAL_UINT(3, ring.popFront(10));
  TEST_ASSERT_TRUE(ring.empty());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_resistive_load);
  RUN_TEST(test_inductive_load_positive_q);
  RUN_TEST(test_capacitive_load_negative_q);
  RUN_TEST(test_frequency_off_nominal);
  RUN_TEST(test_dc_bias_is_removed);
  RUN_TEST(test_noise_floor_zeroes_current);
  RUN_TEST(test_inverted_ct_gives_negative_p_and_sanitize_clamps);
  RUN_TEST(test_no_voltage_frequency_invalid);
  RUN_TEST(test_phase_calibration_from_resistive_load);
  RUN_TEST(test_harmonics_q_magnitude_includes_distortion);
  RUN_TEST(test_aggregator_rms_and_mean);
  RUN_TEST(test_sanitize_limits);
  RUN_TEST(test_iso8601_wib);
  RUN_TEST(test_sample_json);
  RUN_TEST(test_normalize_api_base_and_device_id);
  RUN_TEST(test_ring_buffer_fifo_and_eviction);
  return UNITY_END();
}
