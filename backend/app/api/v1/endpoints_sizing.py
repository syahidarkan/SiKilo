"""
Endpoint sizing PLTS WASKITA (tahap "Punya PLTS"). Semua butuh login.

- ``POST /sizing/calculate``: ukuran PLTS (dan baterai opsional) dengan NPV
  maksimum di bawah aturan ekspor tidak dikreditkan, dari histori beban per jam.
- ``POST /sizing/compare``: kWp minimum untuk target penghematan tagihan dengan
  jadwal kebiasaan lama vs jadwal agen (target < 60 detik dengan default).

Pemeriksaan regulasi di respons BUKAN pernyataan kepatuhan; kepatuhan final
ditentukan PLN.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.models import User
from app.schemas.sizing import CompareRequest, CompareResult, SizingRequest, SizingResult
from app.sizing.calculator import calculate_optimal_sizing
from app.sizing.compare import compare_sizing_with_agent

router = APIRouter(prefix="/sizing", tags=["Solar Sizing"])


@router.post("/calculate", response_model=SizingResult)
async def calculate_sizing(
    request: SizingRequest, user: User = Depends(get_current_user)
) -> SizingResult:
    """
    Rekomendasi kWp (dan baterai bila diminta) dari histori beban per jam:
    NPV maksimum dengan batasan self-consumption ≥ target dan kWp ≤ daya
    tersambung (bila diisi). Energi ekspor tidak dikreditkan (Permen ESDM
    No. 2/2024). Estimasi model, belum divalidasi lapangan.
    """
    try:
        return await run_in_threadpool(calculate_optimal_sizing, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compare", response_model=CompareResult)
async def compare_sizing(
    request: CompareRequest, user: User = Depends(get_current_user)
) -> CompareResult:
    """
    Bandingkan ukuran PLTS minimum untuk mencapai target penghematan tagihan
    dengan jadwal kebiasaan lama vs jadwal agen WASKITA, beserta kurva
    penghematan vs kWp untuk kedua jadwal.
    """
    try:
        return await run_in_threadpool(compare_sizing_with_agent, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
