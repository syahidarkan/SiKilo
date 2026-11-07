"""
Simulasi tahunan ringkas untuk sizing PLTS.

Setahun diwakili 12 hari representatif (satu per bulan) dengan bobot jumlah
hari sebenarnya di bulan itu pada tahun acuan (28/29/30/31). Hari
representatif = hari yang energi PV hariannya paling dekat ke median bulan
tersebut (bukan tanggal tetap), sehingga hari sangat mendung/sangat cerah
tidak mendominasi.

Neraca energi tanpa ekspor (Permen ESDM No. 2/2024: energi yang diekspor
tidak mengurangi tagihan): PV terpakai = min(PV, beban) per slot 15 menit;
sisanya terbuang (curtailment). Dengan baterai, ``Battery.step`` menyerap
surplus dan menutup defisit.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS
from app.digital_twin.battery import Battery


@dataclass
class RepresentativeDay:
    month: int
    day: date
    weight_days: int              # jumlah hari di bulan itu (tahun acuan)
    pv_per_kwp_w: np.ndarray      # (96,) W AC per kWp
    source: str                   # "nasa_power" | "clearsky_scaled" | ...

    @property
    def pv_per_kwp_wh(self) -> np.ndarray:
        return self.pv_per_kwp_w * SLOT_HOURS


def default_reference_year(today: Optional[date] = None) -> int:
    """Tahun lengkap terakhir (data cuaca NASA POWER untuk tahun berjalan belum lengkap)."""
    return (today or date.today()).year - 1


def resolve_location(lat: Optional[float], lon: Optional[float]) -> tuple[float, float]:
    return (
        settings.site_latitude if lat is None else float(lat),
        settings.site_longitude if lon is None else float(lon),
    )


def representative_days(
    year: int, lat: float, lon: float, solar: Any = None
) -> list[RepresentativeDay]:
    """12 hari representatif (median energi PV harian per bulan) untuk tahun ``year``."""
    if solar is None:
        from app.digital_twin.solar_engine import get_solar_engine

        solar = get_solar_engine()
    out: list[RepresentativeDay] = []
    for month in range(1, 13):
        n_days = calendar.monthrange(year, month)[1]
        days = [date(year, month, 1) + timedelta(days=i) for i in range(n_days)]
        curves = [np.asarray(solar.simulate_day(d, 1.0, lat=lat, lon=lon), dtype=np.float64) for d in days]
        energy = np.array([c.sum() for c in curves])
        idx = int(np.argmin(np.abs(energy - np.median(energy))))
        # Panggil sekali lagi agar last_source sesuai hari terpilih.
        chosen = np.asarray(solar.simulate_day(days[idx], 1.0, lat=lat, lon=lon), dtype=np.float64)
        out.append(
            RepresentativeDay(
                month=month,
                day=days[idx],
                weight_days=n_days,
                pv_per_kwp_w=np.clip(chosen, 0.0, None),
                source=str(getattr(solar, "last_source", "unknown")),
            )
        )
    return out


def summarize_source(rep_days: Sequence[RepresentativeDay]) -> str:
    sources = sorted({r.source for r in rep_days})
    return sources[0] if len(sources) == 1 else "+".join(sources)


def month_load_matrix(
    profiles: Iterable[tuple[date, Sequence[float]]], max_days_per_month: int = 62
) -> dict[int, np.ndarray]:
    """
    Beban per slot (Wh) dikelompokkan per bulan kalender: {bulan: (D, 96)}.

    Bulan tanpa data memakai semua hari yang ada (paling banyak
    ``max_days_per_month`` hari terbaru). Energi per jam dibagi rata ke 4 slot.
    """
    rows = sorted(((d, np.asarray(p, dtype=np.float64)) for d, p in profiles), key=lambda x: x[0])
    if not rows:
        raise ValueError("Profil beban kosong")
    slots_per_hour = int(round(1.0 / SLOT_HOURS))

    def to_slots(hourly_kwh: np.ndarray) -> np.ndarray:
        return np.repeat(hourly_kwh * 1000.0 / slots_per_hour, slots_per_hour)

    all_days = np.stack([to_slots(p) for _, p in rows])
    if float(all_days.sum()) <= 0:
        raise ValueError("Total beban nol; tidak ada dasar untuk menghitung ukuran PLTS")
    fallback = all_days[-max_days_per_month:]
    out: dict[int, np.ndarray] = {}
    for month in range(1, 13):
        idx = [i for i, (d, _) in enumerate(rows) if d.month == month]
        out[month] = all_days[idx][-max_days_per_month:] if idx else fallback
    return out


@dataclass
class AnnualEnergy:
    """Neraca energi & biaya setahun (tahun pertama, sebelum degradasi)."""

    generation_kwh: np.ndarray    # (K,)
    used_kwh: np.ndarray          # (K,) PV yang dipakai sendiri (termasuk lewat baterai)
    curtail_kwh: np.ndarray       # (K,)
    savings_idr: np.ndarray       # (K,) tagihan yang dihindari
    load_kwh: float
    bill_before_idr: float

    @property
    def self_consumption(self) -> np.ndarray:
        return np.where(self.generation_kwh > 0, self.used_kwh / np.maximum(self.generation_kwh, 1e-9), 1.0)


def annual_no_battery(
    kwps: Sequence[float],
    rep_days: Sequence[RepresentativeDay],
    loads: dict[int, np.ndarray],
    tariff_idr_per_wh: np.ndarray,
) -> AnnualEnergy:
    """Neraca setahun tanpa baterai, tervektorisasi untuk banyak kWp sekaligus."""
    k = np.asarray(kwps, dtype=np.float64).reshape(-1)
    gen = np.zeros_like(k)
    used = np.zeros_like(k)
    savings = np.zeros_like(k)
    load_kwh = 0.0
    bill = 0.0
    for rep in rep_days:
        L = loads[rep.month]                                   # (D, 96) Wh
        pv = k[:, None] * rep.pv_per_kwp_wh[None, :]           # (K, 96) Wh
        u = np.minimum(pv[:, None, :], L[None, :, :])          # (K, D, 96)
        w = rep.weight_days
        gen += pv.sum(axis=1) * w / 1000.0
        used += u.sum(axis=2).mean(axis=1) * w / 1000.0
        savings += (u * tariff_idr_per_wh[None, None, :]).sum(axis=2).mean(axis=1) * w
        load_kwh += float(L.sum(axis=1).mean()) * w / 1000.0
        bill += float((L * tariff_idr_per_wh[None, :]).sum(axis=1).mean()) * w
    return AnnualEnergy(gen, used, np.maximum(gen - used, 0.0), savings, load_kwh, bill)


def annual_with_battery(
    kwp: float,
    battery_kwh: float,
    rep_days: Sequence[RepresentativeDay],
    loads: dict[int, np.ndarray],
    tariff_idr_per_wh: np.ndarray,
    c_rate: Optional[float] = None,
) -> AnnualEnergy:
    """
    Neraca setahun dengan baterai (satu kombinasi kWp × kWh).

    Per bulan, hari-hari beban dijalankan berurutan dengan PV hari
    representatif; SoC berlanjut antarhari dan hari pertama dijalankan dua kali
    sebagai pemanasan agar SoC awal tidak memihak.
    """
    if battery_kwh <= 0:
        return annual_no_battery([kwp], rep_days, loads, tariff_idr_per_wh)
    c_rate = settings.battery_c_rate if c_rate is None else c_rate
    gen = used = savings = load_kwh = bill = 0.0
    for rep in rep_days:
        L = loads[rep.month]
        n_days = L.shape[0]
        pv_wh = kwp * rep.pv_per_kwp_wh
        pv_w = np.tile(pv_wh / SLOT_HOURS, n_days)
        load_w = L.reshape(-1) / SLOT_HOURS
        net = pv_w - load_w
        bat = Battery.from_kwh(battery_kwh, c_rate=c_rate)
        bat.run(net[:N_SLOTS], dt_h=SLOT_HOURS, reset=True)        # pemanasan
        run = bat.run(net, dt_h=SLOT_HOURS, reset=False)
        load_wh = L.reshape(-1)
        avoided_wh = load_wh - run.grid_import_wh                    # beban yang tidak dari PLN
        w = rep.weight_days / n_days
        gen += float(pv_wh.sum()) * rep.weight_days / 1000.0
        used += float((pv_w * SLOT_HOURS - run.curtail_wh).sum()) * w / 1000.0
        tariff = np.tile(tariff_idr_per_wh, n_days)
        savings += float((avoided_wh * tariff).sum()) * w
        load_kwh += float(load_wh.sum()) * w / 1000.0
        bill += float((load_wh * tariff).sum()) * w
    g = np.array([gen])
    u = np.array([used])
    return AnnualEnergy(g, u, np.maximum(g - u, 0.0), np.array([savings]), load_kwh, bill)
