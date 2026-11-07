"""
Satu-satunya sumber kebenaran tarif PLN untuk seluruh modul WASKITA.

UMKM binaan (golongan B-1/B-2) dikenai tarif flat per kWh, sehingga
menggeser jam pemakaian TIDAK menghemat apa pun kecuali ada produksi PLTS
yang bisa dipakai sendiri. Skema "tou" (WBP/LWBP) disediakan hanya untuk
golongan B-3/I-3 (>200 kVA) dengan WBP pukul 17:00–22:00.
"""
import numpy as np

from app.core.config import settings

N_SLOTS = 96
SLOT_HOURS = 0.25


def is_peak_hour(hour: int) -> bool:
    if settings.tariff_scheme != "tou":
        return False
    return settings.tariff_wbp_start_hour <= hour < settings.tariff_wbp_end_hour


def tariff_idr_per_kwh(hour: int) -> float:
    """Tarif energi (Rp/kWh) yang berlaku pada jam tertentu (0–23)."""
    if settings.tariff_scheme == "flat":
        return settings.tariff_flat_idr_per_kwh
    base = settings.tariff_lwbp_idr_per_kwh
    return base * settings.tariff_wbp_multiplier if is_peak_hour(hour) else base


def tariff_idr_per_wh(hour: int) -> float:
    return tariff_idr_per_kwh(hour) / 1000.0


def tariff_curve_idr_per_wh(n_slots: int = N_SLOTS) -> np.ndarray:
    """Kurva tarif per slot 15 menit dalam Rp/Wh, shape (n_slots,)."""
    slots_per_hour = n_slots // 24
    return np.array(
        [tariff_idr_per_wh(t // slots_per_hour) for t in range(n_slots)], dtype=np.float64
    )


def average_tariff_idr_per_kwh() -> float:
    """Tarif rata-rata harian sederhana (untuk estimasi kasar)."""
    return float(np.mean([tariff_idr_per_kwh(h) for h in range(24)]))
