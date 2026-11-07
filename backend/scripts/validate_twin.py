"""
Validasi tiruan digital WASKITA terhadap data nyata (replay).

Membandingkan simulasi tiruan digital (beban kebiasaan lama + baseload + PLTS
+ baterai, cuaca NASA POWER pada tanggal yang sama) dengan:

  * CSV meteran/telemetri: ``timestamp,p_active`` (W, interval bebas) atau
    ``timestamp,kwh`` (energi per jam atau lebih halus). Diasumsikan mengukur
    impor dari PLN di titik sambung.
  * CSV tagihan bulanan PLN: ``bulan,kwh,rp`` (bulan = YYYY-MM). Periode baca
    meter PLN didekati dengan bulan kalender.

Biaya dihitung dengan ``app/core/tariff.py`` (+ PPJ opsional dari profil).
Hasil ditulis ke ``settings.twin_validation_path`` (atau ``--output``):

    {"bill_error_pct": float, "energy_error_pct": float, "n_days": int,
     "source": str, "generated_at": iso, ...rincian}

Target proposal: selisih tagihan ≤ 10 %. Hasil dengan ``source="example"``
memakai data CONTOH SINTETIS dan TIDAK menunjukkan akurasi di lapangan.

Usage (dari folder backend):
    python scripts/validate_twin.py --example
    python scripts/validate_twin.py --profile profil.json --bills tagihan.csv --meter meter.csv
    python scripts/validate_twin.py --write-example-inputs docs/examples
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.tariff import N_SLOTS, SLOT_HOURS, tariff_idr_per_kwh  # noqa: E402
from app.digital_twin.battery import Battery  # noqa: E402
from app.digital_twin.orders import OrderBook  # noqa: E402
from app.digital_twin.solar_engine import SolarEngine, get_solar_engine  # noqa: E402
from app.digital_twin.weather import resolve_backend_path  # noqa: E402

EXAMPLE_DIR = BACKEND_ROOT / "docs" / "examples"
TARGET_BILL_ERROR_PCT = 10.0
SLOTS_PER_HOUR = int(round(1 / SLOT_HOURS))


# ── profil UMKM ──────────────────────────────────────────────────────────────
@dataclass
class TwinMachine:
    machine_id: str
    label: str
    power_w: float
    daily_runtime_minutes: int
    habit_start_hour: Optional[int] = None
    duty_cycle: float = 1.0  # rata-rata daya/daya nominal saat ON (mis. setrika bertermostat)


@dataclass
class TwinProfile:
    name: str
    machines: list[TwinMachine]
    latitude: float = settings.site_latitude
    longitude: float = settings.site_longitude
    pv_kwp: float = 0.0
    battery_kwh: float = 0.0
    baseload_w: float = 150.0          # beban 24 jam (kulkas, router, CCTV)
    work_hours_load_w: float = 0.0     # lampu/kipas selama jam kerja
    work_start_hour: int = settings.work_start_hour
    work_end_hour: int = settings.work_end_hour
    ppj_pct: float = 0.0               # Pajak Penerangan Jalan daerah, % dari biaya energi
    connected_power_va: Optional[float] = None  # untuk rekening minimum 40 jam nyala
    orders_csv: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: Path) -> "TwinProfile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        machines = [TwinMachine(**m) for m in raw.pop("machines", [])]
        known = {f for f in cls.__dataclass_fields__ if f != "machines"}
        kwargs = {k: v for k, v in raw.items() if k in known}
        extra = {k: v for k, v in raw.items() if k not in known}
        prof = cls(machines=machines, extra=extra, **kwargs)
        if prof.orders_csv and not Path(prof.orders_csv).is_absolute():
            prof.orders_csv = str((Path(path).parent / prof.orders_csv).resolve())
        return prof


# ── simulasi ─────────────────────────────────────────────────────────────────
def habit_load_w(machines: list[TwinMachine], default_start: int) -> np.ndarray:
    """Kebiasaan lama: mesin mulai di habit_start_hour lalu jalan terus sampai runtime terpenuhi."""
    load = np.zeros(N_SLOTS)
    for m in machines:
        n = int(math.ceil(m.daily_runtime_minutes / (SLOT_HOURS * 60)))
        if n <= 0:
            continue
        start_h = m.habit_start_hour if m.habit_start_hour is not None else default_start
        s = int(start_h) * SLOTS_PER_HOUR
        load[s:min(s + n, N_SLOTS)] += m.power_w * m.duty_cycle
    return load


class TwinReplay:
    def __init__(self, profile: TwinProfile, solar: Optional[SolarEngine] = None,
                 order_book: Optional[OrderBook] = None) -> None:
        self.p = profile
        self.solar = solar or get_solar_engine()
        if order_book is not None:
            self.orders = order_book
        elif profile.orders_csv:
            self.orders = OrderBook.from_csv(profile.orders_csv)
        else:
            self.orders = OrderBook()
        self.solar_sources: set[str] = set()

    def load_w(self, day: date) -> np.ndarray:
        jobs = self.orders.jobs_for(day, self.p.machines)
        load = habit_load_w(jobs, settings.default_habit_start_hour)
        load += self.p.baseload_w
        if self.orders.factor_for(day) > 0 and self.p.work_hours_load_w > 0:
            s, e = self.p.work_start_hour * SLOTS_PER_HOUR, self.p.work_end_hour * SLOTS_PER_HOUR
            load[s:e] += self.p.work_hours_load_w
        return load

    def grid_import_wh(self, day: date) -> np.ndarray:
        """Impor PLN per slot (Wh), shape (96,)."""
        load = self.load_w(day)
        if self.p.pv_kwp > 0:
            pv = self.solar.simulate_day(day, self.p.pv_kwp, self.p.latitude, self.p.longitude).astype(np.float64)
            self.solar_sources.add(self.solar.last_source)
        else:
            pv = np.zeros(N_SLOTS)
        net = pv - load
        if self.p.battery_kwh > 0:
            return Battery.from_kwh(self.p.battery_kwh).run(net, SLOT_HOURS).grid_import_wh
        return np.clip(-net, 0.0, None) * SLOT_HOURS

    def hourly_kwh(self, day: date) -> np.ndarray:
        return self.grid_import_wh(day).reshape(24, SLOTS_PER_HOUR).sum(axis=1) / 1000.0


def energy_cost_idr(hourly_kwh: np.ndarray) -> float:
    return float(sum(hourly_kwh[h] * tariff_idr_per_kwh(h) for h in range(24)))


def bill_idr(energy_cost: float, total_kwh: float, profile: TwinProfile) -> float:
    """Biaya energi + PPJ, dengan rekening minimum 40 jam nyala bila VA diketahui."""
    cost = energy_cost
    if profile.connected_power_va:
        avg_tariff = energy_cost / total_kwh if total_kwh > 0 else tariff_idr_per_kwh(12)
        cost = max(cost, 40.0 * profile.connected_power_va / 1000.0 * avg_tariff)
    return cost * (1.0 + profile.ppj_pct / 100.0)


# ── pembacaan data nyata ─────────────────────────────────────────────────────
def read_meter_csv(path: Path, tz: str = settings.site_timezone) -> pd.DataFrame:
    """Kembalikan DataFrame index (day, hour) kolom kwh; hanya hari dengan 24 jam data."""
    df = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in df.columns}
    tcol = cols.get("timestamp") or cols.get("ts") or cols.get("waktu")
    if tcol is None:
        raise ValueError("CSV meter butuh kolom 'timestamp'")
    ts = pd.to_datetime(df[tcol], utc=False, format="mixed")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert(tz).dt.tz_localize(None)
    hour_key = ts.dt.floor("h")
    if "kwh" in cols:
        hourly = pd.Series(df[cols["kwh"]].astype(float).to_numpy(), index=hour_key).groupby(level=0).sum()
    elif "p_active" in cols:
        # Rata-rata daya per jam × 1 jam. Butuh sampel tersebar merata dalam jam itu.
        hourly = (pd.Series(df[cols["p_active"]].astype(float).clip(lower=0).to_numpy(), index=hour_key)
                  .groupby(level=0).mean() / 1000.0)
    else:
        raise ValueError("CSV meter butuh kolom 'kwh' atau 'p_active'")
    out = pd.DataFrame({"kwh": hourly})
    out["day"] = [t.date() for t in out.index]
    out["hour"] = [t.hour for t in out.index]
    counts = out.groupby("day")["hour"].nunique()
    full_days = set(counts[counts == 24].index)
    out = out[out["day"].isin(full_days)]
    return out.set_index(["day", "hour"]).sort_index()


def read_bills_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"bulan": str})
    cols = {c.strip().lower(): c for c in df.columns}
    for need in ("bulan", "kwh", "rp"):
        if need not in cols:
            raise ValueError(f"CSV tagihan butuh kolom 'bulan,kwh,rp' (kolom '{need}' tidak ada)")
    out = pd.DataFrame({
        "bulan": df[cols["bulan"]].astype(str).str.slice(0, 7),
        "kwh": df[cols["kwh"]].astype(float),
        "rp": df[cols["rp"]].astype(float),
    })
    return out


def _month_days(ym: str) -> list[date]:
    y, m = int(ym[:4]), int(ym[5:7])
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def _pct(sim: float, real: float) -> float:
    return abs(sim - real) / real * 100.0 if real > 0 else float("nan")


# ── validasi ─────────────────────────────────────────────────────────────────
def validate(profile: TwinProfile, meter: Optional[pd.DataFrame] = None,
             bills: Optional[pd.DataFrame] = None, source: str = "meter",
             replay: Optional[TwinReplay] = None) -> dict:
    if meter is None and bills is None:
        raise ValueError("Butuh minimal satu input: --meter atau --bills")
    replay = replay or TwinReplay(profile)
    result: dict = {"profile": profile.name, "target_bill_error_pct": TARGET_BILL_ERROR_PCT}
    days_seen: set[date] = set()
    meter_bill_err = meter_energy_err = bills_bill_err = bills_energy_err = None

    if meter is not None and len(meter):
        days = sorted({d for d, _ in meter.index})
        real_kwh = sim_kwh = real_cost = sim_cost = 0.0
        daily = []
        for d in days:
            real_h = np.array([meter.loc[(d, h), "kwh"] for h in range(24)], dtype=float)
            sim_h = replay.hourly_kwh(d)
            real_kwh += real_h.sum()
            sim_kwh += sim_h.sum()
            real_cost += energy_cost_idr(real_h)
            sim_cost += energy_cost_idr(sim_h)
            daily.append({"day": d.isoformat(), "real_kwh": round(float(real_h.sum()), 3),
                          "sim_kwh": round(float(sim_h.sum()), 3),
                          "error_pct": round(_pct(sim_h.sum(), real_h.sum()), 2)})
        days_seen.update(days)
        meter_energy_err = _pct(sim_kwh, real_kwh)
        meter_bill_err = _pct(sim_cost, real_cost)
        daily_errs = [x["error_pct"] for x in daily if not math.isnan(x["error_pct"])]
        result["meter"] = {
            "n_days": len(days),
            "real_kwh": round(real_kwh, 2), "sim_kwh": round(sim_kwh, 2),
            "real_cost_idr": round(real_cost), "sim_cost_idr": round(sim_cost),
            "energy_error_pct": round(meter_energy_err, 2),
            "cost_error_pct": round(meter_bill_err, 2),
            "daily_mape_pct": round(float(np.mean(daily_errs)), 2) if daily_errs else None,
            "daily": daily,
        }

    if bills is not None and len(bills):
        months = []
        real_rp = sim_rp = real_kwh_b = sim_kwh_b = 0.0
        for _, row in bills.iterrows():
            days = _month_days(row["bulan"])
            hourly = np.zeros(24)
            for d in days:
                hourly += replay.hourly_kwh(d)
            kwh = float(hourly.sum())
            rp = bill_idr(energy_cost_idr(hourly), kwh, profile)
            days_seen.update(days)
            real_rp += row["rp"]
            sim_rp += rp
            real_kwh_b += row["kwh"]
            sim_kwh_b += kwh
            months.append({"bulan": row["bulan"], "real_kwh": row["kwh"], "sim_kwh": round(kwh, 1),
                           "real_rp": round(row["rp"]), "sim_rp": round(rp),
                           "bill_error_pct": round(_pct(rp, row["rp"]), 2)})
        bills_bill_err = _pct(sim_rp, real_rp)
        bills_energy_err = _pct(sim_kwh_b, real_kwh_b)
        within = [m for m in months if m["bill_error_pct"] <= TARGET_BILL_ERROR_PCT]
        result["pln_bill"] = {
            "n_months": len(months),
            "real_rp": round(real_rp), "sim_rp": round(sim_rp),
            "bill_error_pct": round(bills_bill_err, 2),
            "energy_error_pct": round(bills_energy_err, 2),
            "max_monthly_bill_error_pct": max(m["bill_error_pct"] for m in months),
            "months_within_target": f"{len(within)}/{len(months)}",
            "months": months,
        }

    # Metrik utama: tagihan dari tagihan PLN bila ada; energi dari meteran bila ada.
    bill_err = bills_bill_err if bills_bill_err is not None else meter_bill_err
    energy_err = meter_energy_err if meter_energy_err is not None else bills_energy_err
    result.update({
        "bill_error_pct": round(float(bill_err), 2),
        "energy_error_pct": round(float(energy_err), 2),
        "n_days": len(days_seen),
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_met": bool(bill_err <= TARGET_BILL_ERROR_PCT),
        "solar_source": sorted(replay.solar_sources) or None,
        "orders_source": replay.orders.source,
    })
    if source == "example":
        result["catatan"] = ("Data CONTOH SINTETIS — angka ini hanya menguji pipeline, "
                             "BELUM divalidasi dengan data lapangan UMKM.")
    return result


def write_result(result: dict, output: Optional[str] = None) -> Path:
    path = resolve_backend_path(output or settings.twin_validation_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


# ── data contoh (sintetis) ───────────────────────────────────────────────────
EXAMPLE_PROFILE = {
    "name": "Contoh konveksi kecil Sukoharjo (SINTETIS)",
    "latitude": -7.68, "longitude": 110.83,
    "pv_kwp": 0.0, "battery_kwh": 0.0,
    "baseload_w": 120.0, "work_hours_load_w": 250.0,
    "work_start_hour": 7, "work_end_hour": 17,
    "ppj_pct": 0.0, "connected_power_va": 3500,
    "orders_csv": "orders_history_example.csv",
    "machines": [
        {"machine_id": "jahit-01", "label": "Mesin Jahit (4 unit)", "power_w": 1000.0,
         "daily_runtime_minutes": 420, "habit_start_hour": 8, "duty_cycle": 0.6},
        {"machine_id": "setrika-01", "label": "Setrika Uap", "power_w": 1200.0,
         "daily_runtime_minutes": 240, "habit_start_hour": 9, "duty_cycle": 0.55},
        {"machine_id": "kompresor-01", "label": "Kompresor Sablon", "power_w": 750.0,
         "daily_runtime_minutes": 120, "habit_start_hour": 13, "duty_cycle": 0.7},
    ],
}


def write_example_inputs(out_dir: Path, seed: int = 2026) -> list[Path]:
    """
    Buat file contoh SINTETIS. "Kenyataan" dibangkitkan dengan model yang sengaja
    berbeda dari profil (variasi harian acak, jam mulai bergeser, baseload lain)
    agar validasi tidak sirkular — tetapi tetap BUKAN data lapangan.
    """
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    prof_path = out_dir / "twin_profile_example.json"
    prof_path.write_text(json.dumps(EXAMPLE_PROFILE, ensure_ascii=False, indent=2), encoding="utf-8")

    # Riwayat pesanan 8 minggu (Agustus–September 2025).
    orders_path = out_dir / "orders_history_example.csv"
    start = date(2025, 8, 4)
    lines = ["tanggal,pesanan"]
    for i in range(56):
        d = start + timedelta(days=i)
        base = (40, 40, 42, 38, 34, 50, 0)[d.weekday()]
        n = 0 if base == 0 else int(max(0, rng.normal(base, 4)))
        lines.append(f"{d.isoformat()},{n}")
    orders_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    profile = TwinProfile.from_json(prof_path)
    book = OrderBook.from_csv(orders_path)

    def true_hourly(d: date) -> np.ndarray:
        f = book.factor_for(d) * float(rng.lognormal(0.0, 0.12))
        load = np.full(N_SLOTS, profile.baseload_w * 1.15)  # baseload nyata sedikit lebih tinggi
        if f > 0:
            load[7 * 4:17 * 4] += profile.work_hours_load_w
            for m in profile.machines:
                n = int(round(m.daily_runtime_minutes * f / 15))
                s = int(m.habit_start_hour * 4 + rng.integers(-2, 3))
                load[s:min(s + n, N_SLOTS)] += m.power_w * m.duty_cycle * float(rng.normal(1.0, 0.08))
        load *= rng.normal(1.0, 0.04, N_SLOTS).clip(0.8, 1.2)
        return load.reshape(24, 4).sum(axis=1) * SLOT_HOURS / 1000.0

    meter_path = out_dir / "meter_example.csv"
    rows = ["timestamp,kwh"]
    for i in range(14):
        d = date(2025, 10, 6) + timedelta(days=i)
        for h, kwh in enumerate(true_hourly(d)):
            rows.append(f"{d.isoformat()}T{h:02d}:00:00+07:00,{kwh:.4f}")
    meter_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    bills_path = out_dir / "pln_bills_example.csv"
    rows = ["bulan,kwh,rp"]
    for month in range(4, 10):
        ym = f"2025-{month:02d}"
        hourly = np.zeros(24)
        for d in _month_days(ym):
            hourly += true_hourly(d)
        kwh = round(float(hourly.sum()))
        rows.append(f"{ym},{kwh},{round(kwh * tariff_idr_per_kwh(12))}")
    bills_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return [prof_path, orders_path, meter_path, bills_path]


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validasi tiruan digital WASKITA vs data nyata")
    ap.add_argument("--profile", type=Path, help="JSON profil UMKM (lihat docs/examples)")
    ap.add_argument("--meter", type=Path, help="CSV timestamp,p_active atau timestamp,kwh")
    ap.add_argument("--bills", type=Path, help="CSV bulan,kwh,rp")
    ap.add_argument("--orders", type=Path, help="CSV riwayat pesanan (menimpa orders_csv di profil)")
    ap.add_argument("--output", help="default: settings.twin_validation_path")
    ap.add_argument("--source", help="label sumber data; default meter/pln_bill/meter+pln_bill")
    ap.add_argument("--example", action="store_true", help="pakai data contoh di docs/examples (source=example)")
    ap.add_argument("--write-example-inputs", type=Path, metavar="DIR", help="tulis ulang file contoh sintetis lalu keluar")
    args = ap.parse_args(argv)

    if args.write_example_inputs:
        for p in write_example_inputs(args.write_example_inputs):
            print(f"[contoh] {p}")
        return 0

    if args.example:
        args.profile = args.profile or EXAMPLE_DIR / "twin_profile_example.json"
        args.meter = args.meter or EXAMPLE_DIR / "meter_example.csv"
        args.bills = args.bills or EXAMPLE_DIR / "pln_bills_example.csv"
    if args.profile is None:
        ap.error("--profile wajib (atau gunakan --example)")
    if args.meter is None and args.bills is None:
        ap.error("butuh --meter dan/atau --bills")

    profile = TwinProfile.from_json(args.profile)
    if args.orders:
        profile.orders_csv = str(args.orders)
    meter = read_meter_csv(args.meter) if args.meter else None
    bills = read_bills_csv(args.bills) if args.bills else None
    if args.example:
        source = "example"
    else:
        source = args.source or "+".join(s for s, v in (("meter", meter), ("pln_bill", bills)) if v is not None)

    result = validate(profile, meter, bills, source=source)
    path = write_result(result, args.output)
    status = "TERCAPAI" if result["target_met"] else "BELUM tercapai"
    print(f"Sumber data      : {result['source']}")
    print(f"Hari dibandingkan: {result['n_days']}")
    print(f"Selisih tagihan  : {result['bill_error_pct']:.2f} % (target ≤ {TARGET_BILL_ERROR_PCT:.0f} %: {status})")
    print(f"Selisih energi   : {result['energy_error_pct']:.2f} %")
    if "catatan" in result:
        print(f"Catatan          : {result['catatan']}")
    print(f"Ditulis ke       : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
