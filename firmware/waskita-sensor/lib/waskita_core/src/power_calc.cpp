#include "power_calc.h"

#include <math.h>

namespace waskita {

namespace {

const float kPi = 3.14159265358979f;
const size_t kMaxCrossings = 64;
const float kQSignDeadband = 0.02f;  // |Qf| < 2% S -> tanda dianggap +

// Interpolasi linear x[pos] (pos pecahan). Di luar rentang -> ekstrapolasi
// dari segmen tepi, sehingga phase_cal > 1 tetap aman di ujung buffer.
inline float interpAt(const uint16_t* x, size_t n, float pos) {
  long i0 = (long)floorf(pos);
  if (i0 < 0) i0 = 0;
  if (i0 > (long)n - 2) i0 = (long)n - 2;
  const float frac = pos - (float)i0;
  const float a = (float)x[i0];
  const float b = (float)x[i0 + 1];
  return a + frac * (b - a);
}

float meanOf(const uint16_t* x, size_t from, size_t to) {
  if (to <= from) return 0.0f;
  float s = 0.0f;
  for (size_t k = from; k < to; ++k) s += (float)x[k];
  return s / (float)(to - from);
}

// Cari zero-crossing naik (dari negatif ke >= 0) dengan histeresis: setelah
// satu crossing, sinyal harus turun di bawah -hyst dulu sebelum crossing
// berikutnya dihitung (mencegah crossing ganda akibat derau).
// Posisi diinterpolasi linear (indeks pecahan).
size_t findUpCrossings(const uint16_t* v, size_t n, size_t start, float mean,
                       float hyst, float* out, size_t max_out) {
  size_t count = 0;
  bool armed = false;
  for (size_t k = start; k + 1 < n && count < max_out; ++k) {
    const float a = (float)v[k] - mean;
    const float b = (float)v[k + 1] - mean;
    if (a < -hyst) armed = true;
    if (armed && a < 0.0f && b >= 0.0f) {
      out[count++] = (float)k + (-a) / (b - a);
      armed = false;
    }
  }
  return count;
}

inline float finiteOr(float x, float fallback) {
  return isfinite(x) ? x : fallback;
}

}  // namespace

bool computeWindow(const uint16_t* v_raw, const uint16_t* i_raw, size_t n,
                   const WindowConfig& cfg, const Calibration& cal,
                   WindowResult* out) {
  if (!out) return false;
  WindowResult r;
  r.v_rms = r.i_rms = r.p_active = r.q_reactive = 0.0f;
  r.s_apparent = r.power_factor = r.phase_deg = 0.0f;
  r.frequency_hz = cfg.nominal_freq_hz;
  r.freq_valid = false;
  r.ok = false;
  r.cycles_used = 0;
  r.samples_used = 0;
  *out = r;

  if (!v_raw || !i_raw || n < 64 || !(cfg.sample_rate_hz > 0.0f) ||
      !(cfg.nominal_freq_hz > 0.0f) || !(cfg.volts_per_count > 0.0f)) {
    return false;
  }

  const float fs = cfg.sample_rate_hz;
  const float spc_nom = fs / cfg.nominal_freq_hz;  // sampel per siklus
  const float quarter_nom = spc_nom * 0.25f;
  // Ruang di awal buffer untuk sampel tegangan yang digeser (phase_cal) dan
  // tegangan tertunda seperempat periode (penentu tanda Q). Frekuensi bisa
  // lebih rendah dari nominal, jadi beri cadangan 10%.
  const size_t margin =
      (size_t)ceilf(quarter_nom * 1.1f + fabsf(cal.phase_cal - 1.0f) + 3.0f);
  if (margin + (size_t)spc_nom + 2 >= n) return false;

  int target = cfg.target_cycles;
  if (target < 1) target = 1;
  if (target > (int)kMaxCrossings - 1) target = (int)kMaxCrossings - 1;

  // 1) Rata-rata kasar + amplitudo untuk histeresis.
  const float m0v = meanOf(v_raw, 0, n);
  float vmax = 0.0f;
  for (size_t k = 0; k < n; ++k) {
    const float d = fabsf((float)v_raw[k] - m0v);
    if (d > vmax) vmax = d;
  }
  float hyst = 0.15f * vmax;
  if (hyst < cfg.min_hysteresis_counts) hyst = cfg.min_hysteresis_counts;

  // 2) Zero-crossing tegangan -> jendela berisi siklus bulat + frekuensi.
  float crossings[kMaxCrossings];
  const size_t nc = findUpCrossings(v_raw, n, margin, m0v, hyst, crossings,
                                    (size_t)target + 1);
  size_t k0, k1;
  int cycles;
  bool fvalid = false;
  float freq = cfg.nominal_freq_hz;
  if (nc >= 2) {
    cycles = (int)nc - 1;
    const float span = crossings[nc - 1] - crossings[0];
    if (span > 0.0f) {
      freq = (float)cycles * fs / span;
      fvalid = true;
    }
    k0 = (size_t)lroundf(crossings[0]);
    k1 = (size_t)lroundf(crossings[nc - 1]);
  } else {
    // Tanpa zero-crossing (tegangan hilang / sensor V lepas): pakai siklus
    // bulat menurut frekuensi nominal.
    cycles = (int)floorf((float)(n - margin - 1) / spc_nom);
    if (cycles > target) cycles = target;
    if (cycles < 1) cycles = 1;
    k0 = margin;
    k1 = margin + (size_t)lroundf((float)cycles * spc_nom);
  }
  if (k1 > n - 1) k1 = n - 1;
  if (k1 <= k0 + 8) return false;
  const size_t N = k1 - k0;

  // 3) Hapus offset DC: rata-rata pada siklus bulat (eksak untuk sinyal
  //    periodik, setara high-pass tanpa transien awal).
  const float mv = meanOf(v_raw, k0, k1);
  const float mi = meanOf(i_raw, k0, k1);

  const float f_used = fvalid ? freq : cfg.nominal_freq_hz;
  const float quarter = fs / (4.0f * f_used);

  // 4) Akumulasi. Vrms dan P sama-sama memakai tegangan yang digeser
  //    phase_cal (interpolasi linear sedikit meredam amplitudo; memakai
  //    sinyal yang sama membuat PF beban resistif tetap 1). Qf memakai
  //    tegangan tertunda T/4 (hanya untuk tanda Q dan sudut fasa).
  float sv2 = 0.0f, si2 = 0.0f, sp = 0.0f, sq = 0.0f;
  for (size_t k = k0; k < k1; ++k) {
    const float base = (float)k - 1.0f + cal.phase_cal;
    const float vs = interpAt(v_raw, n, base) - mv;
    const float vq = interpAt(v_raw, n, base - quarter) - mv;
    const float ik = (float)i_raw[k] - mi;
    sv2 += vs * vs;
    si2 += ik * ik;
    sp += vs * ik;
    sq += vq * ik;
  }
  const float invN = 1.0f / (float)N;
  const float vpc = cfg.volts_per_count;
  float v_rms = cal.v_cal * vpc * sqrtf(sv2 * invN);
  float i_rms = cal.i_cal * vpc * sqrtf(si2 * invN);
  const float scale = cal.v_cal * cal.i_cal * vpc * vpc;
  float p = scale * sp * invN;
  float qf = scale * sq * invN;
  if (cfg.invert_current) {
    p = -p;
    qf = -qf;
  }

  if (i_rms < cfg.i_noise_floor_a) {
    i_rms = 0.0f;
    p = 0.0f;
    qf = 0.0f;
  }

  const float s = v_rms * i_rms;
  // Q = tanda * sqrt(S^2 - P^2). Catatan: dengan harmonisa, nilai ini juga
  // memuat daya distorsi (bukan hanya Q fundamental).
  const float qmag = sqrtf(fmaxf(s * s - p * p, 0.0f));
  // Tanda dari Qf (pergeseran fasa fundamental). Bila |Qf| sangat kecil
  // dibanding S (beban resistif / sisa Q hanya daya distorsi), tanda
  // ditentukan derau -> pakai konvensi positif.
  const float q = (qf < 0.0f && -qf > kQSignDeadband * s) ? -qmag : qmag;
  float pf = (s > 0.0f) ? p / s : 0.0f;
  if (pf > 1.0f) pf = 1.0f;
  if (pf < -1.0f) pf = -1.0f;

  if (fvalid) {
    const float lo = cfg.nominal_freq_hz * 0.9f;
    const float hi = cfg.nominal_freq_hz * 1.1f;
    if (v_rms < cfg.v_min_for_freq_v || freq < lo || freq > hi) fvalid = false;
  }

  r.v_rms = finiteOr(v_rms, 0.0f);
  r.i_rms = finiteOr(i_rms, 0.0f);
  r.p_active = finiteOr(p, 0.0f);
  r.q_reactive = finiteOr(q, 0.0f);
  r.s_apparent = finiteOr(s, 0.0f);
  r.power_factor = finiteOr(pf, 0.0f);
  r.phase_deg = (i_rms > 0.0f) ? finiteOr(atan2f(qf, p) * 180.0f / kPi, 0.0f) : 0.0f;
  r.freq_valid = fvalid;
  r.frequency_hz = fvalid ? freq : cfg.nominal_freq_hz;
  r.cycles_used = cycles;
  r.samples_used = (int)N;
  r.ok = true;
  *out = r;
  return true;
}

float phaseCalFromResistiveLoad(float measured_phase_deg, float freq_hz,
                                float sample_rate_hz, float current_phase_cal) {
  if (!(freq_hz > 0.0f) || !(sample_rate_hz > 0.0f)) return current_phase_cal;
  // Arus tampak tertinggal phi derajat -> tegangan perlu digeser mundur
  // sebesar phi/360 periode = phi/360 * fs/f sampel.
  return current_phase_cal - (measured_phase_deg / 360.0f) * (sample_rate_hz / freq_hz);
}

// ---------------------------------------------------------------------------
// Aggregator

void Aggregator::reset() {
  sv2_ = si2_ = sp_ = sq_ = sf_ = 0.0f;
  n_ = nf_ = 0;
}

void Aggregator::add(const WindowResult& r) {
  if (!r.ok) return;
  sv2_ += r.v_rms * r.v_rms;
  si2_ += r.i_rms * r.i_rms;
  sp_ += r.p_active;
  sq_ += r.q_reactive;
  if (r.freq_valid) {
    sf_ += r.frequency_hz;
    ++nf_;
  }
  ++n_;
}

bool Aggregator::finish(int64_t time_ms, float nominal_freq_hz,
                        TelemetrySample* out) const {
  if (!out || n_ == 0) return false;
  const float inv = 1.0f / (float)n_;
  out->time_ms = time_ms;
  out->v_rms = sqrtf(sv2_ * inv);
  out->i_rms = sqrtf(si2_ * inv);
  out->p_active = sp_ * inv;
  out->q_reactive = sq_ * inv;
  out->flags = 0;
  if (nf_ > 0) {
    out->frequency = sf_ / (float)nf_;
  } else {
    out->frequency = nominal_freq_hz;
    out->flags |= FLAG_FREQ_INVALID;
  }
  return true;
}

BackendLimits defaultBackendLimits() {
  BackendLimits l;
  l.v_max = 300.0f;
  l.i_max = 200.0f;
  l.f_min = 48.0f;
  l.f_max = 52.0f;
  return l;
}

void sanitizeForBackend(TelemetrySample* s, const BackendLimits& lim) {
  if (!s) return;
  bool clamped = false;
  s->v_rms = finiteOr(s->v_rms, 0.0f);
  s->i_rms = finiteOr(s->i_rms, 0.0f);
  s->p_active = finiteOr(s->p_active, 0.0f);
  s->q_reactive = finiteOr(s->q_reactive, 0.0f);
  s->frequency = finiteOr(s->frequency, 0.5f * (lim.f_min + lim.f_max));

  if (s->p_active < 0.0f) {
    s->flags |= FLAG_REVERSE_POWER;
    s->p_active = 0.0f;
  }
  if (s->v_rms < 0.0f) { s->v_rms = 0.0f; clamped = true; }
  if (s->v_rms > lim.v_max) { s->v_rms = lim.v_max; clamped = true; }
  if (s->i_rms < 0.0f) { s->i_rms = 0.0f; clamped = true; }
  if (s->i_rms > lim.i_max) { s->i_rms = lim.i_max; clamped = true; }
  if (s->frequency < lim.f_min) { s->frequency = lim.f_min; clamped = true; }
  if (s->frequency > lim.f_max) { s->frequency = lim.f_max; clamped = true; }
  if (clamped) s->flags |= FLAG_CLAMPED;
}

}  // namespace waskita
