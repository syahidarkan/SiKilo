"""
Rapor Energi & Kelayakan PLTS WASKITA (JSON + PDF).

``generate_bankability_scorecard(...) -> dict``
    Menyusun rapor dari hasil sizing (``SizingResult`` atau objek/dict dengan
    field yang sama). Opsional: sizing SETELAH jadwal agen, profil pemakaian
    per mesin (dari ``EnergyLedger``), periode audit, dan sumber data.
``render_scorecard_pdf(scorecard) -> bytes``
    Render rapor ke PDF A4 (reportlab).

PENTING — skor kelayakan adalah HEURISTIK DRAF:
bobot (lihat ``SCORE_WEIGHTS``) dan ambang kategori belum dikalibrasi dengan
data kredit bank/koperasi mana pun. Skor ini alat bantu diskusi, bukan
keputusan kredit, dan tidak menjanjikan produk/bunga tertentu dari lembaga
keuangan mana pun. Lihat ``docs/WHATSAPP.md`` §Rapor.
"""
from __future__ import annotations

import io
import math
from datetime import date
from typing import Any, Iterable, Optional, Sequence

from app.core.config import settings

REPORT_VERSION = "2.0"

# Bobot heuristik draf (jumlah = 1). WAJIB dikalibrasi bersama bank/koperasi.
SCORE_WEIGHTS: dict[str, float] = {
    "payback": 0.30,
    "npv": 0.25,
    "self_consumption": 0.25,
    "compliance": 0.20,
}
# Ambang skor PBP: ≤ PBP_BEST tahun → 100, ≥ PBP_WORST tahun → 0 (linier di antaranya).
PBP_BEST_YEARS = 3.0
PBP_WORST_YEARS = 13.0
# Skor NPV dari indeks profitabilitas NPV/CAPEX: ≥ 1,0 → 100, ≤ 0 → 0.
NPV_PI_FULL = 1.0

CATEGORIES: tuple[tuple[float, str, str], ...] = (
    (80.0, "indikasi_kuat", "Indikasi kelayakan kuat"),
    (60.0, "indikasi_sedang", "Indikasi kelayakan sedang"),
    (0.0, "perlu_kajian", "Perlu kajian lanjut"),
)

SCORE_NOTE = (
    "Skor adalah heuristik draf WASKITA (bobot: PBP 30%, NPV 25%, konsumsi sendiri 25%, "
    "kesesuaian kWp dengan daya tersambung PLN 20%; 50 poin bila daya tersambung belum diketahui). Bobot dan ambang belum dikalibrasi dengan lembaga "
    "keuangan mana pun; bukan keputusan kredit dan tidak menjanjikan skema atau bunga tertentu."
)
DISCLAIMER = (
    "Rapor ini dibuat otomatis oleh WASKITA dari data perangkat (bila ada) dan simulasi "
    "tiruan digital (pvlib, data cuaca NASA POWER atau model clear-sky). Angka finansial "
    "memakai asumsi biaya dan tarif yang tercantum dan belum divalidasi auditor energi. "
    "Survei lokasi oleh penyedia PLTS serta verifikasi auditor energi tersertifikasi tetap "
    "diperlukan sebelum pengajuan pembiayaan resmi."
)


# ── util ───────────────────────────────────────────────────────────────────
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def sizing_dict(sizing: Any) -> Optional[dict[str, Any]]:
    """Ringkasan sizing yang JSON-safe (nilai tak hingga/NaN → None)."""
    if sizing is None:
        return None
    capex = _num(_get(sizing, "capex_idr"))
    npv = _num(_get(sizing, "npv_idr"))
    within = _within_connected_power(sizing)
    return {
        "capacity_kwp": _num(_get(sizing, "recommended_kwp")),
        "capex_idr": capex,
        "annual_generation_kwh": _num(_get(sizing, "annual_generation_kwh")),
        "annual_self_consumption_kwh": _num(_get(sizing, "annual_self_consumption_kwh")),
        "annual_curtailment_kwh": _num(_get(sizing, "annual_curtailment_kwh")),
        "self_consumption_rate_pct": _num(_get(sizing, "self_consumption_rate_pct")),
        "annual_savings_idr": _num(_get(sizing, "annual_savings_idr")),
        "payback_period_years": _num(_get(sizing, "payback_period_years")),
        "npv_idr": npv,
        "npv_to_capex_ratio": round(npv / capex, 3) if npv is not None and capex else None,
        "lcoe_idr_per_kwh": _num(_get(sizing, "lcoe_idr_per_kwh")),
        "co2_avoided_kg_per_year": _num(_get(sizing, "co2_avoided_kg_per_year")),
        # Tri-state: None bila daya tersambung belum diketahui (belum diperiksa),
        # bukan False — jangan menyatakan "tidak patuh" untuk hal yang tidak dicek.
        "permen_esdm_2_2024_compliant": within,
        "kwp_within_connected_power": within,
        "connected_power_kva": _num(_get(_get(sizing, "regulatory_checks"), "connected_power_kva")),
        "export_not_credited_modeled": bool(
            _get(_get(sizing, "regulatory_checks"), "export_not_credited_modeled", True)
        ),
        "recommended_battery_kwh": _num(_get(sizing, "recommended_battery_kwh")),
        "pv_source": str(_get(sizing, "pv_source", "") or ""),
        "note": str(_get(sizing, "recommendation_note", "") or ""),
    }


def _within_connected_power(sizing: Any) -> Optional[bool]:
    """True/False dari ``regulatory_checks``; None bila daya tersambung tidak diketahui."""
    checks = _get(sizing, "regulatory_checks")
    if checks is not None:
        v = _get(checks, "kwp_within_connected_power")
        return None if v is None else bool(v)
    legacy = _get(sizing, "permen_esdm_compliant")
    return None if legacy is None else bool(legacy)


def compare_dict(compare: Any) -> Optional[dict[str, Any]]:
    """Ringkasan ``CompareResult`` (kWp minimum kebiasaan lama vs jadwal agen)."""
    if compare is None:
        return None
    return {
        "target_monthly_savings_idr": _num(_get(compare, "target_monthly_savings_idr")),
        "target_savings_pct": _num(_get(compare, "target_savings_pct")),
        "reference_annual_bill_idr": _num(_get(compare, "reference_annual_bill_idr")),
        "min_kwp_habit": _num(_get(compare, "min_kwp_habit")),
        "min_kwp_habit_no_idle": _num(_get(compare, "min_kwp_habit_no_idle")),
        "min_kwp_agent": _num(_get(compare, "min_kwp_agent")),
        "kwp_reduction": _num(_get(compare, "kwp_reduction")),
        "kwp_reduction_pct": _num(_get(compare, "kwp_reduction_pct")),
        "capex_reduction_idr": _num(_get(compare, "capex_reduction_idr")),
        "agent_reduces_panel": bool(_get(compare, "agent_reduces_panel", False)),
        "headline": str(_get(compare, "headline", "") or ""),
        "pv_source": str(_get(compare, "pv_source", "") or ""),
        "notes": [str(n) for n in (_get(compare, "notes") or [])][:5],
    }


def score_components(s: dict[str, Any]) -> dict[str, float]:
    """Skor 0–100 per komponen dari ``sizing_dict``."""
    pbp = s.get("payback_period_years")
    if pbp is None or pbp <= 0:
        pbp_score = 0.0
    else:
        pbp_score = _clip((PBP_WORST_YEARS - pbp) / (PBP_WORST_YEARS - PBP_BEST_YEARS) * 100.0)
    pi = s.get("npv_to_capex_ratio")
    npv_score = 0.0 if pi is None else _clip(pi / NPV_PI_FULL * 100.0)
    sc = s.get("self_consumption_rate_pct")
    sc_score = 0.0 if sc is None else _clip(sc)
    within = s.get("kwp_within_connected_power")
    # Diketahui di bawah batas daya tersambung → 100; tidak diketahui → 50; melebihi → 0.
    comp_score = 50.0 if within is None else (100.0 if within else 0.0)
    return {
        "payback": round(pbp_score, 1),
        "npv": round(npv_score, 1),
        "self_consumption": round(sc_score, 1),
        "compliance": round(comp_score, 1),
    }


def categorize(total: float) -> tuple[str, str]:
    for threshold, code, label in CATEGORIES:
        if total >= threshold:
            return code, label
    return CATEGORIES[-1][1], CATEGORIES[-1][2]


def _machine_usage(rows: Optional[Sequence[Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    items = []
    for r in rows:
        label = str(_get(r, "label") or _get(r, "appliance_label") or "-")
        kwh = _num(_get(r, "kwh")) or 0.0
        cost = _num(_get(r, "cost_idr")) or 0.0
        items.append({"label": label, "kwh": round(kwh, 3), "cost_idr": round(cost, 0)})
    total = sum(i["kwh"] for i in items)
    for i in items:
        i["share_pct"] = round(i["kwh"] / total * 100.0, 1) if total > 0 else 0.0
    return sorted(items, key=lambda i: i["kwh"], reverse=True)


def assumptions() -> dict[str, Any]:
    from app.core.tariff import average_tariff_idr_per_kwh

    return {
        "tariff_scheme": settings.tariff_scheme,
        "tariff_group": settings.tariff_group,
        "avg_tariff_idr_per_kwh": round(average_tariff_idr_per_kwh(), 2),
        "capex_per_kwp_idr": settings.capex_per_kwp_idr,
        "opex_pct_of_capex": settings.opex_pct_of_capex,
        "discount_rate": settings.discount_rate,
        "panel_lifetime_years": settings.panel_lifetime_years,
        "panel_degradation_per_year": settings.panel_degradation_per_year,
        "grid_emission_kg_per_kwh": settings.grid_emission_kg_per_kwh,
        "export_credit": "Tidak ada (Permen ESDM 2/2024); surplus PLTS dianggap terbuang.",
    }


# ── rapor ──────────────────────────────────────────────────────────────────
def generate_bankability_scorecard(
    umkm_name: str,
    umkm_address: str,
    umkm_type: str,
    sizing: Any,
    avg_monthly_pln_bill_idr: float,
    audit_period_days: int = 30,
    prepared_date: Optional[date] = None,
    *,
    sizing_after_agent: Any = None,
    agent_compare: Any = None,
    machine_usage: Optional[Sequence[Any]] = None,
    audit_period_start: Optional[date] = None,
    audit_period_end: Optional[date] = None,
    load_data_source: str = "input_pengguna",
    pv_data_source: Optional[str] = None,
    bill_source: str = "input_pengguna",
    umkm_id: Optional[int] = None,
    kecamatan: Optional[str] = None,
    extra_notes: Iterable[str] = (),
    verified: Optional[bool] = None,
    agent_compare_basis: Optional[str] = None,
) -> dict[str, Any]:
    """
    Rapor energi & kelayakan PLTS (dict JSON-safe).

    ``sizing`` = rekomendasi berdasarkan pola pakai saat ini (kebiasaan lama).
    ``sizing_after_agent`` = rekomendasi bila beban digeser jadwal agen; bila
    ada, skor dihitung dari sizing ini (skenario yang diusulkan WASKITA).
    ``agent_compare`` = ``CompareResult`` (``app.sizing``): kWp minimum untuk
    target hemat yang sama dengan kebiasaan lama vs jadwal agen.
    ``load_data_source``: ``terukur`` (EnergyLedger perangkat) | ``simulasi`` |
    ``input_pengguna``.
    ``verified``: apakah angka berasal dari data yang dibaca WASKITA sendiri
    (default: True hanya bila ``load_data_source == "terukur"``). Rapor yang
    tidak terverifikasi diberi tanda "Data dari pengguna – tidak diverifikasi
    WASKITA" di JSON & PDF, dan tidak pernah berlabel terukur.
    ``agent_compare_basis``: keterangan dasar beban perbandingan agen (dicetak
    di rapor). Perbandingan agen TIDAK ikut skor.
    """
    prepared_date = prepared_date or date.today()
    before = sizing_dict(sizing)
    after = sizing_dict(sizing_after_agent)
    basis_key = "after_agent" if after is not None else "current_habit"
    basis = after if after is not None else before
    if basis is None:
        raise ValueError("sizing wajib diisi")

    comps = score_components(basis)
    total = round(sum(SCORE_WEIGHTS[k] * comps[k] for k in SCORE_WEIGHTS), 1)
    code, label = categorize(total)

    monthly = float(avg_monthly_pln_bill_idr or 0.0)
    usage = _machine_usage(machine_usage)

    comparison = None
    if before is not None and after is not None:
        kb, ka = before.get("capacity_kwp"), after.get("capacity_kwp")
        comparison = {
            "kwp_current_habit": kb,
            "kwp_after_agent": ka,
            "kwp_difference": round(ka - kb, 2) if ka is not None and kb is not None else None,
            "capex_difference_idr": (
                round(after["capex_idr"] - before["capex_idr"], 0)
                if after.get("capex_idr") is not None and before.get("capex_idr") is not None else None
            ),
            "pbp_current_habit_years": before.get("payback_period_years"),
            "pbp_after_agent_years": after.get("payback_period_years"),
        }

    agent_cmp = compare_dict(agent_compare)
    if agent_cmp is not None:
        agent_cmp["basis"] = agent_compare_basis or "simulasi profil mesin di tiruan digital, bukan beban terukur"
        agent_cmp["included_in_score"] = False
    co2 = basis.get("co2_avoided_kg_per_year")
    if verified is None:
        verified = load_data_source == "terukur"
    if not verified and load_data_source == "terukur":
        load_data_source = "input_pengguna"
    if not verified and bill_source == "terukur":
        bill_source = "input_pengguna"
    measured = verified and load_data_source == "terukur"
    verification_label = (
        "Terverifikasi: dihitung WASKITA dari data perangkat"
        if verified else "Data dari pengguna – tidak diverifikasi WASKITA"
    )
    pv_src = pv_data_source or "simulasi pvlib (NASA POWER bila tersedia, jika tidak model clear-sky)"
    notes = list(extra_notes)
    if not measured:
        notes.append("Profil beban BUKAN hasil ukur perangkat; hasil hanya indikatif.")
    if after is None and agent_cmp is None:
        notes.append("Rekomendasi kWp setelah jadwal agen belum tersedia; skor memakai pola pakai saat ini.")
    if agent_cmp is not None:
        notes.append(
            "Perbandingan kWp kebiasaan lama vs jadwal agen memakai profil mesin di tiruan digital "
            "(simulasi), bukan hasil ukur setelah jadwal diterapkan; tidak ikut dihitung dalam skor."
        )
    if not verified:
        notes.insert(0, "Rapor ini disusun dari angka yang dikirim pengguna; WASKITA tidak memverifikasinya.")
    if basis.get("kwp_within_connected_power") is None:
        notes.append("Daya tersambung PLN belum diketahui; batas kWp terhadap daya tersambung belum dicek.")

    return {
        "report_meta": {
            "title": "Rapor Energi & Kelayakan PLTS",
            "subtitle": "WASKITA – agen AI pengatur energi UMKM",
            "prepared_date": prepared_date.isoformat(),
            "version": REPORT_VERSION,
            "validation_status": "belum divalidasi auditor energi",
            "data_verified_by_waskita": bool(verified),
            "data_verification": verification_label,
        },
        "umkm_profile": {
            "umkm_id": umkm_id,
            "name": umkm_name,
            "address": umkm_address,
            "kecamatan": kecamatan,
            "type": umkm_type,
            "avg_monthly_pln_bill_idr": round(monthly, 0),
            "avg_annual_pln_bill_idr": round(monthly * 12, 0),
            "bill_source": bill_source,
        },
        "audit_period": {
            "days": int(audit_period_days),
            "start": audit_period_start.isoformat() if audit_period_start else None,
            "end": audit_period_end.isoformat() if audit_period_end else None,
        },
        "machine_usage": usage,
        "plts_recommendation": {
            "basis": basis_key,
            "current_habit": before,
            "after_agent": after,
            "comparison": comparison,
            "agent_compare": agent_cmp,
            # Ringkas (kompatibel dengan versi sebelumnya):
            "capacity_kwp": basis.get("capacity_kwp"),
            "capex_idr": basis.get("capex_idr"),
            "annual_generation_kwh": basis.get("annual_generation_kwh"),
            "annual_savings_idr": basis.get("annual_savings_idr"),
            "payback_period_years": basis.get("payback_period_years"),
            "npv_25_years_idr": basis.get("npv_idr"),
            "lcoe_idr_per_kwh": basis.get("lcoe_idr_per_kwh"),
            "co2_avoided_kg_per_year": co2,
            "permen_esdm_2_2024_compliant": basis.get("permen_esdm_2_2024_compliant"),
            "kwp_within_connected_power": basis.get("kwp_within_connected_power"),
        },
        "bankability_score": {
            "total_score": total,
            "category_code": code,
            "risk_category": label,
            "recommendation": label,
            "weights": dict(SCORE_WEIGHTS),
            "breakdown": {
                "payback_period_score": comps["payback"],
                "npv_score": comps["npv"],
                "self_consumption_score": comps["self_consumption"],
                "compliance_score": comps["compliance"],
            },
            "method_note": SCORE_NOTE,
            "calibrated": False,
        },
        "environmental_impact": {
            "co2_avoided_kg_per_year": co2,
            "co2_avoided_ton_lifetime": (
                round(co2 * settings.panel_lifetime_years / 1000.0, 1) if co2 is not None else None
            ),
        },
        "data_sources": {
            "load_profile": load_data_source,
            "load_profile_measured": measured,
            "pv_generation": pv_src,
            "tariff": f"app.core.tariff (skema {settings.tariff_scheme}, golongan {settings.tariff_group})",
            "financial_assumptions": assumptions(),
        },
        "notes": notes,
        "disclaimer": DISCLAIMER,
    }


# ── PDF ────────────────────────────────────────────────────────────────────
_ASCII_MAP = {
    "≥": ">=", "≤": "<=", "–": "-", "—": "-", "…": "...", "×": "x", "₂": "2",
    "‘": "'", "’": "'", "“": '"', "”": '"', "→": "->", "•": "-", "±": "+/-", "%": "%",
}


def _pdf_text(value: Any) -> str:
    """Teks aman untuk font Helvetica bawaan + escape XML untuk Paragraph."""
    s = "-" if value is None else str(value)
    for k, v in _ASCII_MAP.items():
        s = s.replace(k, v)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rp(v: Any) -> str:
    f = _num(v)
    if f is None:
        return "-"
    s = f"{abs(round(f)):,.0f}".replace(",", ".")
    return f"-Rp {s}" if round(f) < 0 else f"Rp {s}"


def _n(v: Any, d: int = 1, unit: str = "") -> str:
    f = _num(v)
    if f is None:
        return "-"
    s = f"{f:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} {unit}".strip()


_SOURCE_LABEL = {
    "terukur": "Terukur (perangkat WASKITA, EnergyLedger)",
    "simulasi": "Simulasi tiruan digital",
    "input_pengguna": "Input pengguna (belum terukur)",
}


def render_scorecard_pdf(scorecard: dict[str, Any]) -> bytes:
    """Render rapor (hasil ``generate_bankability_scorecard``) ke PDF A4."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#14532d"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.8, leading=11.5)
    small = ParagraphStyle("small", parent=body, fontSize=7.6, leading=9.6, textColor=colors.HexColor("#444444"))

    def P(text: Any, style=body) -> Paragraph:
        return Paragraph(_pdf_text(text), style)

    def table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
        data = [[c if isinstance(c, Paragraph) else P(c) for c in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")))
        t.setStyle(TableStyle(style))
        return t

    meta = scorecard.get("report_meta", {})
    prof = scorecard.get("umkm_profile", {})
    period = scorecard.get("audit_period", {})
    usage = scorecard.get("machine_usage", []) or []
    rec = scorecard.get("plts_recommendation", {})
    score = scorecard.get("bankability_score", {})
    env = scorecard.get("environmental_impact", {})
    src = scorecard.get("data_sources", {})
    fin = src.get("financial_assumptions", {}) or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=_pdf_text(meta.get("title", "Rapor WASKITA")), author="WASKITA",
    )
    W = A4[0] - 32 * mm
    story: list[Any] = [
        P(meta.get("title", "Rapor Energi & Kelayakan PLTS"), h1),
        P(f"{meta.get('subtitle', 'WASKITA')} | Tanggal: {meta.get('prepared_date', '-')} | "
          f"Versi {meta.get('version', '-')} | Status: {meta.get('validation_status', '-')}", small),
        Spacer(1, 4),
    ]
    if not meta.get("data_verified_by_waskita", False):
        warn = ParagraphStyle("warn", parent=body, fontSize=10, leading=13, textColor=colors.HexColor("#b91c1c"),
                              borderColor=colors.HexColor("#b91c1c"), borderWidth=1, borderPadding=4,
                              backColor=colors.HexColor("#fef2f2"))
        story.append(P(
            f"{meta.get('data_verification') or 'Data dari pengguna – tidak diverifikasi WASKITA'}. "
            "Angka beban & tagihan berasal dari pemanggil, bukan dari perangkat WASKITA.", warn))
        story.append(Spacer(1, 6))

    # 1. Profil UMKM & periode audit
    story.append(P("1. Profil UMKM & periode data", h2))
    period_txt = f"{period.get('days', '-')} hari"
    if period.get("start") and period.get("end"):
        period_txt += f" ({period['start']} s/d {period['end']})"
    story.append(table([
        ["Nama", prof.get("name"), "Jenis usaha", prof.get("type")],
        ["Alamat", prof.get("address") or "-", "Kecamatan", prof.get("kecamatan") or "-"],
        ["Biaya listrik / bulan", _rp(prof.get("avg_monthly_pln_bill_idr")),
         "Sumber biaya", _SOURCE_LABEL.get(prof.get("bill_source"), prof.get("bill_source"))],
        ["Periode audit", period_txt, "Sumber profil beban",
         _SOURCE_LABEL.get(src.get("load_profile"), src.get("load_profile"))],
    ], [0.18 * W, 0.32 * W, 0.18 * W, 0.32 * W], header=False))

    # 2. Profil pemakaian per mesin
    story.append(P("2. Profil pemakaian per mesin", h2))
    if usage:
        rows: list[list[Any]] = [["Peralatan / mesin", "kWh", "Biaya", "Porsi"]]
        for u in usage[:15]:
            rows.append([u.get("label"), _n(u.get("kwh"), 2), _rp(u.get("cost_idr")), _n(u.get("share_pct"), 1, "%")])
        if len(usage) > 15:
            rows.append([f"(+{len(usage) - 15} lainnya)", "", "", ""])
        story.append(table(rows, [0.46 * W, 0.18 * W, 0.2 * W, 0.16 * W]))
        story.append(P("Pembagian per mesin adalah estimasi disagregasi beban (NILM) dari satu titik ukur panel.", small))
    else:
        story.append(P("Belum ada data pemakaian per mesin dari perangkat WASKITA.", body))

    # 3. Rekomendasi PLTS
    story.append(P("3. Rekomendasi PLTS atap", h2))
    cur, aft = rec.get("current_habit"), rec.get("after_agent")
    cols = [("Pola pakai saat ini", cur)] + ([("Setelah jadwal agen", aft)] if aft else [])
    rows = [["Metrik"] + [c[0] for c in cols]]
    fields = [
        ("Kapasitas", lambda s: _n(s.get("capacity_kwp"), 2, "kWp")),
        ("CAPEX", lambda s: _rp(s.get("capex_idr"))),
        ("Produksi / tahun", lambda s: _n(s.get("annual_generation_kwh"), 0, "kWh")),
        ("Konsumsi sendiri", lambda s: _n(s.get("self_consumption_rate_pct"), 1, "%")),
        ("Hemat / tahun", lambda s: _rp(s.get("annual_savings_idr"))),
        ("Payback (PBP)", lambda s: _n(s.get("payback_period_years"), 1, "tahun")),
        ("NPV", lambda s: _rp(s.get("npv_idr"))),
        ("LCOE", lambda s: _rp(s.get("lcoe_idr_per_kwh")) + "/kWh" if s.get("lcoe_idr_per_kwh") is not None else "-"),
        ("kWp <= daya tersambung", lambda s: {True: "Ya", False: "Tidak"}.get(s.get("kwp_within_connected_power"), "Belum diketahui")),
    ]
    for name, fn in fields:
        rows.append([name] + [fn(c[1]) if c[1] else "-" for c in cols])
    width_metric = 0.34 * W
    other = (W - width_metric) / max(1, len(cols))
    story.append(table(rows, [width_metric] + [other] * len(cols)))
    cmp_ = rec.get("agent_compare")
    if cmp_:
        story.append(Spacer(1, 4))
        story.append(P("Ukuran PLTS minimum untuk target hemat yang sama: kebiasaan lama vs jadwal agen", body))
        story.append(table([
            ["Target hemat / bulan", "kWp kebiasaan lama", "kWp jadwal agen", "Selisih kWp", "Selisih CAPEX"],
            [_rp(cmp_.get("target_monthly_savings_idr")), _n(cmp_.get("min_kwp_habit"), 2, "kWp"),
             _n(cmp_.get("min_kwp_agent"), 2, "kWp"), _n(cmp_.get("kwp_reduction"), 2, "kWp"),
             _rp(cmp_.get("capex_reduction_idr"))],
        ], [0.2 * W] * 5))
        if cmp_.get("headline"):
            story.append(P(cmp_["headline"], small))
        if cmp_.get("basis"):
            story.append(P(f"Dasar beban perbandingan: {cmp_['basis']}. Tidak ikut dihitung dalam skor.", small))
    elif not aft:
        story.append(P("Rekomendasi kWp setelah jadwal agen belum tersedia untuk rapor ini.", small))

    # 4. Skor
    story.append(P("4. Skor indikatif kelayakan (heuristik draf)", h2))
    br = score.get("breakdown", {})
    wts = score.get("weights", SCORE_WEIGHTS)
    story.append(table([
        ["Komponen", "Bobot", "Skor 0-100"],
        ["Payback period", _n(wts.get("payback", 0) * 100, 0, "%"), _n(br.get("payback_period_score"), 1)],
        ["NPV / CAPEX", _n(wts.get("npv", 0) * 100, 0, "%"), _n(br.get("npv_score"), 1)],
        ["Konsumsi sendiri", _n(wts.get("self_consumption", 0) * 100, 0, "%"), _n(br.get("self_consumption_score"), 1)],
        ["kWp vs daya tersambung PLN", _n(wts.get("compliance", 0) * 100, 0, "%"), _n(br.get("compliance_score"), 1)],
        ["Total", "100%", f"{_n(score.get('total_score'), 1)} - {score.get('risk_category', '-')}"],
    ], [0.5 * W, 0.15 * W, 0.35 * W]))
    story.append(P(score.get("method_note", SCORE_NOTE), small))

    # 5. Dampak lingkungan
    story.append(P("5. Dampak lingkungan (estimasi)", h2))
    story.append(P(
        f"Emisi CO2 terhindar sekitar {_n(env.get('co2_avoided_kg_per_year'), 0, 'kg')} per tahun "
        f"(sekitar {_n(env.get('co2_avoided_ton_lifetime'), 1, 'ton')} selama umur panel, tanpa degradasi), "
        f"memakai faktor emisi {_n(fin.get('grid_emission_kg_per_kwh'), 3)} kg CO2/kWh.", body))

    # 6. Sumber data & asumsi
    story.append(P("6. Sumber data & asumsi", h2))
    story.append(table([
        ["Profil beban", _SOURCE_LABEL.get(src.get("load_profile"), src.get("load_profile"))],
        ["Produksi PLTS", src.get("pv_generation")],
        ["Tarif", f"{src.get('tariff')}; rata-rata {_rp(fin.get('avg_tariff_idr_per_kwh'))}/kWh"],
        ["CAPEX / kWp", _rp(fin.get("capex_per_kwp_idr"))],
        ["O&M, diskonto, umur", f"O&M {_n((fin.get('opex_pct_of_capex') or 0) * 100, 1, '%')} CAPEX/tahun; "
                                f"diskonto {_n((fin.get('discount_rate') or 0) * 100, 1, '%')}; "
                                f"umur {fin.get('panel_lifetime_years', '-')} tahun"],
        ["Ekspor ke PLN", fin.get("export_credit")],
    ], [0.22 * W, 0.78 * W], header=False))
    for note in scorecard.get("notes", []) or []:
        story.append(P(f"- {note}", small))

    story.append(P("Disclaimer", h2))
    story.append(P(scorecard.get("disclaimer", DISCLAIMER), small))

    doc.build(story)
    return buf.getvalue()


__all__ = [
    "CATEGORIES",
    "DISCLAIMER",
    "SCORE_WEIGHTS",
    "categorize",
    "generate_bankability_scorecard",
    "render_scorecard_pdf",
    "score_components",
    "sizing_dict",
]
