"""
Pemeriksaan regulasi PLTS atap yang bisa dipertanggungjawabkan.

WASKITA TIDAK membuat klaim kepatuhan terhadap Permen ESDM No. 2/2024.
Yang dilakukan hanya:

1. Batas praktis kapasitas: kWp ≤ daya tersambung PLN (kVA) bila diketahui.
2. Model energi menganggap ekspor ke jaringan tidak dikreditkan (surplus PV
   terbuang), sesuai ketentuan Permen ESDM No. 2/2024 bahwa kelebihan energi
   tidak diperhitungkan dalam tagihan.
3. Pengingat jendela permohonan (Pasal 14: permohonan pemasangan diajukan
   pada periode yang dibuka PLN, yaitu Januari dan Juli, mengikuti kuota
   sistem setempat).

Kepatuhan final (kuota, persetujuan teknis, inverter, proteksi) ditentukan
PLN berdasarkan permohonan resmi.
"""
from __future__ import annotations

from typing import Optional

from app.schemas.sizing import RegulatoryChecks

APPLICATION_WINDOW_NOTE = (
    "Permen ESDM No. 2/2024 Pasal 14: permohonan pemasangan PLTS atap diajukan pada periode "
    "pendaftaran yang dibuka PLN (Januari dan Juli) dan bergantung pada kuota sistem setempat. "
    "Siapkan dokumen sebelum jendela berikutnya."
)
DISCLAIMER = (
    "Ini bukan pernyataan kepatuhan. Persetujuan dan kepatuhan final terhadap Permen ESDM "
    "No. 2/2024 ditentukan oleh PLN setelah permohonan resmi, pemeriksaan kuota, dan pemeriksaan "
    "teknis (inverter, proteksi, sambungan)."
)


def connected_kva(connected_power_va: Optional[float]) -> Optional[float]:
    return None if not connected_power_va else float(connected_power_va) / 1000.0


def build_regulatory_checks(kwp: float, connected_power_va: Optional[float]) -> RegulatoryChecks:
    kva = connected_kva(connected_power_va)
    notes = [
        "Surplus PV dimodelkan terbuang (curtailment) dan tidak mengurangi tagihan; "
        "inverter perlu diatur agar tidak mengekspor bila diminta PLN.",
    ]
    within: Optional[bool]
    if kva is None:
        within = None
        notes.append(
            "Daya tersambung PLN belum diisi, sehingga batas kapasitas terhadap daya tersambung belum diperiksa."
        )
    else:
        within = kwp <= kva + 1e-9
        notes.append(
            f"Kapasitas {kwp:.2f} kWp {'tidak melebihi' if within else 'MELEBIHI'} daya tersambung "
            f"{kva:.1f} kVA (batas praktis yang dipakai WASKITA)."
        )
    return RegulatoryChecks(
        connected_power_kva=kva,
        kwp_within_connected_power=within,
        export_not_credited_modeled=True,
        application_window_note=APPLICATION_WINDOW_NOTE,
        disclaimer=DISCLAIMER,
        notes=notes,
    )
