from datetime import date
from typing import List, Dict, Any
from app.schemas.sizing import SizingResult


def generate_bankability_scorecard(
    umkm_name: str,
    umkm_address: str,
    umkm_type: str,
    sizing: SizingResult,
    avg_monthly_pln_bill_idr: float,
    audit_period_days: int = 30,
    prepared_date: date | None = None,
) -> Dict[str, Any]:
    """
    Generate Rapor Audit Energi & Kelayakan PLTS untuk pengajuan pinjaman bank.
    Format JSON siap render ke PDF atau dikirim ke BNI/BRI/BSI green financing.
    """
    if prepared_date is None:
        prepared_date = date.today()

    # Scoring: 0-100 berdasarkan metrik keuangan dan compliance
    score_pbp = max(0, 100 - int((sizing.payback_period_years - 3) * 10))
    score_npv = min(100, max(0, int(sizing.npv_idr / 1_000_000)))
    score_self_consumption = int(sizing.self_consumption_rate_pct)
    score_compliance = 100 if sizing.permen_esdm_compliant else 50

    total_score = int(
        0.3 * score_pbp
        + 0.25 * min(score_npv, 100)
        + 0.25 * score_self_consumption
        + 0.20 * score_compliance
    )

    if total_score >= 80:
        risk_category = "RENDAH"
        recommendation = "LAYAK untuk green financing tier A (bunga preferensial)"
    elif total_score >= 60:
        risk_category = "SEDANG"
        recommendation = "LAYAK untuk green financing tier B (bunga standar)"
    else:
        risk_category = "TINGGI"
        recommendation = "Perlu peninjauan lebih lanjut sebelum pengajuan pembiayaan"

    return {
        "report_meta": {
            "title": "Rapor Audit Energi & Kelayakan PLTS",
            "subtitle": "Nota Listrik AI Energy Audit",
            "prepared_date": prepared_date.isoformat(),
            "audit_period_days": audit_period_days,
            "version": "1.0",
        },
        "umkm_profile": {
            "name": umkm_name,
            "address": umkm_address,
            "type": umkm_type,
            "avg_monthly_pln_bill_idr": avg_monthly_pln_bill_idr,
            "avg_annual_pln_bill_idr": avg_monthly_pln_bill_idr * 12,
        },
        "plts_recommendation": {
            "capacity_kwp": sizing.recommended_kwp,
            "capex_idr": sizing.capex_idr,
            "annual_generation_kwh": sizing.annual_generation_kwh,
            "annual_savings_idr": sizing.annual_savings_idr,
            "payback_period_years": sizing.payback_period_years,
            "npv_25_years_idr": sizing.npv_idr,
            "lcoe_idr_per_kwh": sizing.lcoe_idr_per_kwh,
            "co2_avoided_kg_per_year": sizing.co2_avoided_kg_per_year,
            "permen_esdm_2_2024_compliant": sizing.permen_esdm_compliant,
        },
        "bankability_score": {
            "total_score": total_score,
            "risk_category": risk_category,
            "recommendation": recommendation,
            "breakdown": {
                "payback_period_score": score_pbp,
                "npv_score": min(score_npv, 100),
                "self_consumption_score": score_self_consumption,
                "compliance_score": score_compliance,
            },
        },
        "environmental_impact": {
            "co2_avoided_kg_per_year": sizing.co2_avoided_kg_per_year,
            "co2_avoided_ton_lifetime": round(sizing.co2_avoided_kg_per_year * 25 / 1000, 1),
            "trees_equivalent_per_year": round(sizing.co2_avoided_kg_per_year / 21, 0),
        },
        "disclaimer": (
            "Laporan ini dibuat secara otomatis oleh sistem NOTA LISTRIK AI "
            "berdasarkan data telemetri IoT dan simulasi pvlib. "
            "Verifikasi lapangan oleh auditor energi tersertifikasi diperlukan "
            "sebelum pengajuan pembiayaan resmi."
        ),
    }
