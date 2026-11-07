"""
Generator data sintetis NILM WASKITA (1 Hz).

Mensimulasikan satu panel UMKM berisi beberapa mesin (motor jahit, kompresor
sablon, setrika uap resistif dengan termostat, drum pengering, freezer
bersiklus) ditambah beban kecil yang TIDAK dipasangi smart plug (lampu, kipas)
dan baseload yang melayang pelan. Variasi daya per pemakaian ±12%, noise
sensor, inrush motor, dan pemakaian tumpang-tindih. Karakter mesin per site
digeser dari prototipe (--site-jitter) supaya data tidak identik dengan
prototipe heuristik.

Menulis DUA file:
  <out-dir>/<prefix>_panel.csv  – agregat panel (seperti kotak sensor):
      timestamp,v_rms,i_rms,p_active,q_reactive,frequency
  <out-dir>/<prefix>_plugs.csv  – ground truth per mesin (seperti smart plug):
      timestamp,appliance_label,p_active,status
      Satu baris per mesin tiap --plug-interval-s detik + saat status berubah.
      p_active = daya rata-rata sejak baris itu sampai baris berikutnya.

Contoh (dataset kecil, cepat):
    python scripts/generate_synthetic_data.py --days 4 --seed 1 --prefix train
    python scripts/generate_synthetic_data.py --days 2 --seed 2 --prefix test --start 2026-10-20
(site-seed sama → mesin yang sama; seed beda → hari/pemakaian berbeda)
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.nilm.profiles import APPLIANCE_PROFILES, ApplianceProfile  # noqa: E402

DAY_S = 86_400
V_NOMINAL = 220.0
F_NOMINAL = 50.0
POWER_VARIATION = 0.12     # variasi daya antar pemakaian (uniform ±12%)
Q_VARIATION = 0.08
INRUSH_VARIATION = 0.20
SAMPLE_NOISE = 0.01        # fluktuasi daya mesin per detik (1σ relatif)
SENSOR_NOISE_REL = 0.003
SENSOR_NOISE_ABS_W = 2.0


Run = tuple[int, int]  # (detik mulai, detik selesai) dalam hari


def _cycles(rng, start: float, end: float, on_rng, off_rng, first_on: bool = True) -> list[Run]:
    """Siklus ON/OFF (termostat/pressure switch) di dalam jendela [start, end)."""
    runs: list[Run] = []
    t = start if first_on else start + rng.uniform(*off_rng)
    while t < end:
        dur = rng.uniform(*on_rng)
        s, e = int(t), int(min(t + dur, end))
        if e - s >= 8:
            runs.append((s, e))
        t = e + rng.uniform(*off_rng)
    return runs


def _sessions(rng, n: int, lo_h: float, hi_h: float, dur_min_rng) -> list[tuple[float, float]]:
    out = []
    for _ in range(n):
        s = rng.uniform(lo_h, hi_h) * 3600
        out.append((s, s + rng.uniform(*dur_min_rng) * 60))
    return sorted(out)


def _merge_runs(runs: list[Run], min_gap: int = 20) -> list[Run]:
    """Pastikan run satu mesin tidak tumpang-tindih (mesin yang sama)."""
    runs = sorted(runs)
    out: list[Run] = []
    for s, e in runs:
        if out and s < out[-1][1] + min_gap:
            s = out[-1][1] + min_gap
        if e - s >= 8:
            out.append((s, min(e, DAY_S - 1)))
    return out


def machine_runs(prof: ApplianceProfile, rng, weekday: int) -> list[Run]:
    ws, we = settings.work_start_hour, settings.work_end_hour
    if weekday == 5:          # Sabtu: setengah hari
        we = min(we, 12)
    closed = weekday == 6     # Minggu: hanya freezer
    cls = prof.appliance_class
    runs: list[Run] = []

    if cls == 5:  # freezer: sepanjang hari
        runs = _cycles(rng, rng.uniform(0, 600), DAY_S - 1, (8 * 60, 20 * 60), (12 * 60, 30 * 60))
    elif closed:
        return []
    elif cls == 1:  # motor jahit: sesi kerja, istirahat 12–13
        t = ws * 3600 + rng.uniform(0, 1800)
        while t < we * 3600:
            if 12 * 3600 <= t < 13 * 3600:
                t = 13 * 3600 + rng.uniform(0, 600)
                continue
            e = min(t + rng.uniform(10, 40) * 60, we * 3600)
            if t < 12 * 3600 < e:
                e = 12 * 3600
            runs.append((int(t), int(e)))
            t = e + rng.uniform(2, 15) * 60
    elif cls == 2:  # kompresor sablon: blok kerja, pressure switch bersiklus
        blocks = [(rng.uniform(8, 10), rng.uniform(1.5, 3.0)), (rng.uniform(13, 14), rng.uniform(1.0, 2.5))]
        for start_h, dur_h in blocks:
            s, e = start_h * 3600, min((start_h + dur_h) * 3600, we * 3600)
            runs += _cycles(rng, s, e, (60, 180), (120, 480))
    elif cls == 3:  # setrika uap: sesi, termostat bersiklus
        for s, e in _sessions(rng, int(rng.integers(2, 4)), ws, max(ws + 0.5, we - 1), (30, 90)):
            runs += _cycles(rng, s, min(e, we * 3600), (40, 120), (20, 90))
    elif cls == 4:  # drum pengering: 3–5 batch
        for s, e in _sessions(rng, int(rng.integers(3, 6)), ws, max(ws + 0.5, we - 0.5), (30, 50)):
            runs.append((int(s), int(e)))
    return _merge_runs(runs)


def render_runs(prof: ApplianceProfile, runs: list[Run], rng) -> tuple[np.ndarray, np.ndarray]:
    """Kurva P dan Q (1 Hz) satu mesin, termasuk inrush dan variasi per pemakaian."""
    p = np.zeros(DAY_S)
    q = np.zeros(DAY_S)
    for s, e in runs:
        n = e - s
        pf = 1.0 + rng.uniform(-POWER_VARIATION, POWER_VARIATION)
        qf = 1.0 + rng.uniform(-Q_VARIATION, Q_VARIATION)
        p_run = prof.power_w * pf * (1.0 + rng.normal(0, SAMPLE_NOISE, n))
        q_run = prof.power_w * pf * prof.q_ratio * qf * (1.0 + rng.normal(0, SAMPLE_NOISE * 2, n))
        inrush = max(1.0, prof.inrush_ratio * (1.0 + rng.uniform(-INRUSH_VARIATION, INRUSH_VARIATION)))
        for k in range(min(max(1, prof.inrush_s), n)):
            mult = inrush if k == 0 else 1.0 + (inrush - 1.0) * 0.35
            p_run[k] *= mult
            q_run[k] *= mult
        p[s:e] = p_run
        q[s:e] = q_run
    return p, q


def background(rng, weekday: int) -> tuple[np.ndarray, np.ndarray]:
    """Baseload yang melayang pelan + beban kecil tanpa smart plug (lampu, kipas, dll.)."""
    t = np.arange(DAY_S)
    base = 220.0 + 25.0 * np.sin(2 * np.pi * (t / DAY_S) * 4 + rng.uniform(0, 6.28))
    p = base + rng.normal(0, 3.0, DAY_S)
    q = 60.0 + 0.1 * (base - 220.0)
    n_small = 4 if weekday == 6 else 10
    for _ in range(n_small):
        w = rng.uniform(40, 150)
        qp = rng.uniform(0.0, 0.4)
        s = int(rng.uniform(6, 20) * 3600)
        e = min(DAY_S, s + int(rng.uniform(5, 120) * 60))
        p[s:e] += w
        q[s:e] += w * qp
    return p, q


def plug_rows(label: str, p: np.ndarray, runs: list[Run], day_start: datetime, interval: int, rng) -> pd.DataFrame:
    on = np.zeros(DAY_S, dtype=bool)
    for s, e in runs:
        on[s:e] = True
    idx = set(range(0, DAY_S, interval))
    for s, e in runs:
        idx.add(s)
        idx.add(min(e, DAY_S - 1))
    rows = np.array(sorted(idx))
    nxt = np.append(rows[1:], DAY_S)
    csum = np.concatenate([[0.0], np.cumsum(p)])
    avg = (csum[nxt] - csum[rows]) / (nxt - rows)
    avg = avg * (1.0 + rng.normal(0, 0.005, len(rows)))
    ts = pd.Timestamp(day_start) + pd.to_timedelta(rows, unit="s")
    return pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "appliance_label": label,
            "p_active": np.round(np.clip(avg, 0, None), 2),
            "status": np.where(on[rows], "ON", "OFF"),
        }
    )


def site_profiles(site_seed: int, jitter: float) -> list[ApplianceProfile]:
    """
    Mesin di satu UMKM tidak persis sama dengan prototipe "buku teks". Dengan
    jitter > 0, nilai nominal tiap mesin digeser acak (tetap untuk site_seed yang
    sama) sehingga classifier heuristik (yang memakai prototipe) tidak otomatis
    "tahu jawaban", sedangkan model yang dilatih dari smart plug site itu bisa
    menyesuaikan.
    """
    if jitter <= 0:
        return list(APPLIANCE_PROFILES)
    r = np.random.default_rng(site_seed)
    out = []
    for prof in APPLIANCE_PROFILES:
        out.append(
            replace(
                prof,
                power_w=prof.power_w * (1 + r.uniform(-jitter, jitter)),
                q_ratio=prof.q_ratio * (1 + r.uniform(-0.75 * jitter, 0.75 * jitter)),
                inrush_ratio=max(1.0, prof.inrush_ratio * (1 + r.uniform(-1.25 * jitter, 1.25 * jitter))),
            )
        )
    return out


def generate_day(
    day_start: datetime, rng, plug_interval_s: int, profiles: list[ApplianceProfile] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekday = day_start.weekday()
    p_tot, q_tot = background(rng, weekday)
    plug_frames = []
    for prof in profiles or APPLIANCE_PROFILES:
        runs = machine_runs(prof, rng, weekday)
        p_m, q_m = render_runs(prof, runs, rng)
        p_tot += p_m
        q_tot += q_m
        plug_frames.append(plug_rows(prof.label, p_m, runs, day_start, plug_interval_s, rng))

    p_meas = p_tot * (1 + rng.normal(0, SENSOR_NOISE_REL, DAY_S)) + rng.normal(0, SENSOR_NOISE_ABS_W, DAY_S)
    q_meas = q_tot * (1 + rng.normal(0, SENSOR_NOISE_REL, DAY_S)) + rng.normal(0, SENSOR_NOISE_ABS_W, DAY_S)
    t = np.arange(DAY_S)
    v = V_NOMINAL + 3.0 * np.sin(2 * np.pi * t / DAY_S) - 0.0008 * p_tot + rng.normal(0, 0.8, DAY_S)
    i = np.sqrt(p_meas ** 2 + q_meas ** 2) / v
    f = F_NOMINAL + rng.normal(0, 0.02, DAY_S)
    ts = pd.Timestamp(day_start) + pd.to_timedelta(t, unit="s")
    panel = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "v_rms": np.round(v, 2),
            "i_rms": np.round(i, 3),
            "p_active": np.round(np.clip(p_meas, 0, None), 2),
            "q_reactive": np.round(q_meas, 2),
            "frequency": np.round(f, 3),
        }
    )
    return panel, pd.concat(plug_frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generator data sintetis NILM WASKITA")
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--start", type=str, default="2026-10-05", help="tanggal mulai (YYYY-MM-DD)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-dir", type=str, default="data/synthetic")
    parser.add_argument("--prefix", type=str, default="train")
    parser.add_argument("--plug-interval-s", type=int, default=10)
    parser.add_argument("--site-seed", type=int, default=42, help="seed karakter mesin site (samakan untuk data latih & uji)")
    parser.add_argument("--site-jitter", type=float, default=0.2, help="deviasi nominal mesin dari prototipe (0 = persis prototipe)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    start = datetime.fromisoformat(args.start)
    panel_path = os.path.join(args.out_dir, f"{args.prefix}_panel.csv")
    plug_path = os.path.join(args.out_dir, f"{args.prefix}_plugs.csv")
    profiles = site_profiles(args.site_seed, args.site_jitter)
    for prof in profiles:
        print(f"  {prof.label:30s} P={prof.power_w:6.0f} W  Q/P={prof.q_ratio:.2f}  inrush={prof.inrush_ratio:.2f}")

    for d in range(args.days):
        day_start = start + timedelta(days=d)
        print(f"Membuat hari {d + 1}/{args.days}: {day_start.date()}")
        panel, plugs = generate_day(day_start, rng, args.plug_interval_s, profiles)
        mode, header = ("w", True) if d == 0 else ("a", False)
        panel.to_csv(panel_path, mode=mode, header=header, index=False)
        plugs.sort_values(["timestamp", "appliance_label"]).to_csv(plug_path, mode=mode, header=header, index=False)

    print(f"Selesai: {panel_path} ({args.days * DAY_S:,} baris) dan {plug_path}")


if __name__ == "__main__":
    main()
