from fastapi import APIRouter
from app.schemas.sizing import SizingRequest, SizingResult
from app.sizing.calculator import calculate_optimal_sizing

router = APIRouter(prefix="/sizing", tags=["Solar Sizing"])


@router.post("/calculate", response_model=SizingResult)
async def calculate_sizing(request: SizingRequest) -> SizingResult:
    """
    Hitung kapasitas PLTS optimal berdasarkan histori beban 30 hari.
    Menghasilkan rekomendasi kWp, CAPEX, LCOE, NPV, dan Payback Period
    sesuai Permen ESDM No. 2 Tahun 2024 (zero export, self-consumption).
    """
    return calculate_optimal_sizing(request)
