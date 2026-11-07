from fastapi import APIRouter, Query
from datetime import date
from typing import Optional
from app.schemas.dispatch import DispatchRequest, DispatchResponse
from app.services.whatsapp_agent import generate_daily_brief
from app.services.scorecard_generator import generate_bankability_scorecard
from app.schemas.sizing import SizingResult

router = APIRouter(prefix="/agent", tags=["Agent & Reports"])


@router.get("/whatsapp/daily-brief")
async def get_whatsapp_brief(
    umkm_name: str = Query(default="UMKM Pak Budi"),
    dispatch_savings_idr: float = Query(default=0.0),
    dispatch_savings_pct: float = Query(default=0.0),
    total_pv_kwh: float = Query(default=0.0),
    total_grid_kwh: float = Query(default=0.0),
    curtailment_kwh: float = Query(default=0.0),
    target_date: Optional[date] = Query(default=None),
) -> dict:
    """
    Generate draf pesan WhatsApp harian siap kirim ke pemilik UMKM.
    Endpoint ini dipanggil oleh scheduler pukul 17:30 WIB setiap hari.
    """
    # Build minimal DispatchResponse untuk pesan WhatsApp
    from app.schemas.dispatch import DispatchResponse, SlotSchedule
    mock_response = DispatchResponse(
        target_date=target_date or date.today(),
        schedule=[],
        total_grid_kwh=total_grid_kwh,
        total_pv_kwh=total_pv_kwh,
        total_cost_idr=0.0,
        baseline_cost_idr=0.0,
        savings_idr=dispatch_savings_idr,
        savings_pct=dispatch_savings_pct,
        solver_used="PPO-RL",
        curtailment_kwh=curtailment_kwh,
    )

    message = generate_daily_brief(
        dispatch=mock_response,
        umkm_name=umkm_name,
        target_date=target_date,
    )

    return {"message": message, "char_count": len(message)}


@router.post("/reports/bankability-scorecard")
async def get_bankability_scorecard(
    umkm_name: str = Query(...),
    umkm_address: str = Query(default="Sukoharjo, Jawa Tengah"),
    umkm_type: str = Query(default="Konveksi & Laundry"),
    avg_monthly_bill_idr: float = Query(..., description="Tagihan PLN rata-rata bulanan (Rp)"),
    sizing: SizingResult = ...,
) -> dict:
    """
    Generate Rapor Audit Energi & Kelayakan PLTS untuk green financing.
    """
    return generate_bankability_scorecard(
        umkm_name=umkm_name,
        umkm_address=umkm_address,
        umkm_type=umkm_type,
        sizing=sizing,
        avg_monthly_pln_bill_idr=avg_monthly_bill_idr,
    )
