// WASKITA - inti perhitungan daya AC satu fasa.
//
// Kode di file ini sengaja TIDAK memakai API Arduino agar bisa diuji di PC
// (pio test -e native). Firmware memanggil computeWindow() untuk setiap
// jendela pengukuran (mis. 10 siklus 50 Hz = 200 ms) lalu Aggregator
// menggabungkan beberapa jendela menjadi 1 sampel per detik.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace waskita {

// Konstanta kalibrasi (gaya EmonLib).
struct Calibration {
  // Volt jaringan (RMS) per Volt (RMS) di pin ADC. Bergantung pada trimpot
  // modul ZMPT101B -> WAJIB dikalibrasi dengan multimeter.
  float v_cal;
  // Ampere primer per Volt di pin ADC.
  //   SCT-013-000 (100 A : 50 mA, keluaran arus): rasio lilitan / R_burden
  //     = 2000 / 33 ohm = 60.6
  //   SCT-013-030 (30 A / 1 V, keluaran tegangan): 30
  float i_cal;
  // Koreksi fase: posisi sampel tegangan yang dipakai untuk P adalah
  // (k - 1 + phase_cal). 1.0 = tanpa koreksi; > 1 = tegangan dimajukan
  // (mengompensasi arus yang dibaca sesudah tegangan dan pergeseran fasa
  // trafo). Satuan: periode sampel.
  float phase_cal;
};

struct WindowConfig {
  float sample_rate_hz;      // laju sampel AKTUAL (pasangan V+I per detik)
  float nominal_freq_hz;     // 50 Hz di Indonesia
  int target_cycles;         // jumlah siklus penuh yang dihitung (mis. 10)
  float volts_per_count;     // Vref / 4095 untuk ADC 12 bit
  float i_noise_floor_a;     // Irms di bawah ini dianggap 0 (derau ADC)
  float v_min_for_freq_v;    // Vrms minimum agar frekuensi dianggap valid
  float min_hysteresis_counts;  // histeresis minimum deteksi zero-crossing
  bool invert_current;       // true bila CT terpasang terbalik
};

struct WindowResult {
  float v_rms;          // V
  float i_rms;          // A
  float p_active;       // W, bertanda (negatif = arah daya terbalik)
  float q_reactive;     // VAR, + induktif (arus tertinggal), - kapasitif
  float s_apparent;     // VA
  float power_factor;   // P/S, -1..1
  float frequency_hz;   // dari zero-crossing tegangan
  float phase_deg;      // beda fasa fundamental; + = arus tertinggal
  bool freq_valid;      // false bila tegangan terlalu kecil / tak ada zero-crossing
  bool ok;              // false bila input tidak layak
  int cycles_used;
  int samples_used;
};

// Hitung besaran daya dari satu jendela sampel mentah ADC.
// v_raw[k] dan i_raw[k] adalah pasangan sampel ke-k (tegangan dibaca dulu,
// arus segera sesudahnya). Offset DC (bias 1.65 V) dihapus secara numerik
// memakai rata-rata pada jumlah siklus bulat, jadi bias tidak perlu presisi.
bool computeWindow(const uint16_t* v_raw, const uint16_t* i_raw, size_t n,
                   const WindowConfig& cfg, const Calibration& cal,
                   WindowResult* out);

// Hitung phase_cal baru dari pengukuran pada beban RESISTIF murni
// (setrika/pemanas air/lampu pijar: beda fasa sebenarnya ~0).
// measured_phase_deg = WindowResult::phase_deg rata-rata dengan phase_cal lama.
float phaseCalFromResistiveLoad(float measured_phase_deg, float freq_hz,
                                float sample_rate_hz, float current_phase_cal);

// Bit flag pada TelemetrySample (hanya untuk diagnosa lokal, tidak dikirim).
enum SampleFlags : uint32_t {
  FLAG_REVERSE_POWER = 1u << 0,   // P < 0 sebelum di-clamp (CT terbalik / ekspor PV)
  FLAG_FREQ_INVALID = 1u << 1,    // frekuensi tidak terukur -> dikirim nilai nominal
  FLAG_CLAMPED = 1u << 2,         // ada nilai yang di-clamp ke rentang skema backend
};

// Satu sampel telemetri (agregat 1 detik). Ukuran tetap 32 byte supaya bisa
// disimpan apa adanya di LittleFS.
struct TelemetrySample {
  int64_t time_ms;     // di RAM: uptime ms; di spool LittleFS: epoch ms (UTC)
  float v_rms;
  float i_rms;
  float p_active;      // sudah >= 0 setelah sanitizeForBackend()
  float q_reactive;
  float frequency;
  uint32_t flags;
};
static_assert(sizeof(TelemetrySample) == 32, "TelemetrySample harus 32 byte");

// Menggabungkan beberapa WindowResult menjadi satu sampel per detik.
// Vrms/Irms digabung secara RMS (akar rata-rata kuadrat), P/Q dirata-rata
// (konsisten dengan energi), frekuensi dirata-rata dari jendela yang valid.
class Aggregator {
 public:
  Aggregator() { reset(); }
  void reset();
  void add(const WindowResult& r);
  int count() const { return n_; }
  // Mengisi out (belum disanitasi). Return false bila belum ada jendela.
  bool finish(int64_t time_ms, float nominal_freq_hz, TelemetrySample* out) const;

 private:
  float sv2_, si2_, sp_, sq_, sf_;
  int n_, nf_;
};

// Batas skema backend (app/schemas/telemetry.py).
struct BackendLimits {
  float v_max;      // 300
  float i_max;      // 200
  float f_min;      // 48
  float f_max;      // 52
};
BackendLimits defaultBackendLimits();

// Clamp nilai agar lolos validasi backend: p_active >= 0 (arah dicatat di
// flags), v/i dalam rentang, frekuensi 48..52 Hz, NaN/Inf -> 0.
void sanitizeForBackend(TelemetrySample* s, const BackendLimits& lim);

}  // namespace waskita
