"""
Profil tanda tangan listrik (signature) mesin UMKM yang dikenali WASKITA.

Satu sumber untuk:
- prototipe classifier heuristik (`classifier._heuristic_classify`), dan
- simulator data sintetis (`scripts/generate_synthetic_data.py`).

Nilai di sini adalah perkiraan tipikal dari pelat nama / literatur, BUKAN hasil
pengukuran lapangan. Untuk pemasangan nyata, latih model dengan data smart plug
(lihat docs/NILM.md) agar classifier tidak bergantung pada prototipe ini.

Definisi fitur yang dipakai prototipe (diukur pada panel, sampling 1 Hz):
- power_w        : daya aktif tunak (steady) tambahan saat mesin ON.
- q_ratio        : ΔQ / ΔP tunak (≈ tan φ). Resistif ≈ 0, motor induksi besar.
- inrush_ratio   : (P puncak − P sebelum) / ΔP tunak pada event ON.
- inrush_s       : lama arus awal (detik) yang terlihat di sampel 1 Hz.
"""
from __future__ import annotations

from dataclasses import dataclass

BASELOAD_LABEL = "Baseload / Background"


@dataclass(frozen=True)
class ApplianceProfile:
    appliance_class: int
    label: str
    power_w: float
    q_ratio: float
    inrush_ratio: float
    inrush_s: int
    # Toleransi relatif yang dipakai untuk menghitung jarak ke prototipe.
    power_tol: float = 0.15
    q_ratio_tol: float = 0.08
    inrush_tol: float = 0.35


APPLIANCE_PROFILES: tuple[ApplianceProfile, ...] = (
    ApplianceProfile(1, "Motor Jahit Induksi", power_w=300.0, q_ratio=1.00, inrush_ratio=3.0, inrush_s=1),
    ApplianceProfile(2, "Kompresor Udara Sablon", power_w=1100.0, q_ratio=0.62, inrush_ratio=4.0, inrush_s=2),
    ApplianceProfile(3, "Setrika Pemanas Uap", power_w=1200.0, q_ratio=0.03, inrush_ratio=1.05, inrush_s=0),
    ApplianceProfile(4, "Motor Drum Pengering Laundry", power_w=950.0, q_ratio=0.40, inrush_ratio=2.2, inrush_s=2),
    ApplianceProfile(5, "Kompresor Pendingin Freezer", power_w=180.0, q_ratio=0.85, inrush_ratio=3.5, inrush_s=1),
)

PROFILE_BY_LABEL: dict[str, ApplianceProfile] = {p.label: p for p in APPLIANCE_PROFILES}
