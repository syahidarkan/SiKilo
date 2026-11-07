import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Optional
import pvlib
from pvlib.location import Location
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from app.core.config import settings


class SolarEngine:
    """
    Simulasi output daya PLTS menggunakan pvlib untuk lokasi Sukoharjo.
    Menghasilkan kurva P_pv(t) per interval 15 menit (96 slot per hari).
    """

    INVERTER_EFF: float = 0.96
    TEMP_COEFF: float = 0.004  # per °C
    T_NOCT: float = 45.0       # °C, nominal operating cell temp
    T_AMBIENT_DEFAULT: float = 30.0  # °C

    def __init__(self) -> None:
        self.location = Location(
            latitude=settings.site_latitude,
            longitude=settings.site_longitude,
            altitude=settings.site_altitude_m,
            tz=settings.site_timezone,
        )

    def _get_clearsky_irradiance(self, target_date: date) -> pd.DataFrame:
        times = pd.date_range(
            start=datetime.combine(target_date, datetime.min.time()),
            periods=96,
            freq="15min",
            tz=settings.site_timezone,
        )
        solar_position = self.location.get_solarposition(times)
        clearsky = self.location.get_clearsky(times, model="ineichen")
        return pd.concat([solar_position, clearsky], axis=1)

    def simulate_day(
        self,
        target_date: date,
        kwp: float,
        t_ambient_series: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Hitung kurva P_pv(t) untuk satu hari, 96 slot x 15 menit.

        Returns:
            np.ndarray shape (96,): daya AC output dalam Watt per slot.
        """
        df = self._get_clearsky_irradiance(target_date)
        ghi = df["ghi"].values  # W/m²

        if t_ambient_series is None:
            # Model suhu harian sinusoidal sederhana: 24–34°C
            hours = np.linspace(0, 24, 96, endpoint=False)
            t_ambient_series = 29.0 + 5.0 * np.sin(np.pi * (hours - 6) / 12)
            t_ambient_series = np.clip(t_ambient_series, 24.0, 38.0)

        # T_cell dari model NOCT: T_cell = T_ambient + (NOCT - 20) * GHI / 800
        t_cell = t_ambient_series + (self.T_NOCT - 20.0) * ghi / 800.0

        # P_pv(t) = Inverter_Eff * kWp * (GHI / 1000) * [1 - Temp_Coeff * (T_cell - 25)]
        p_pv = (
            self.INVERTER_EFF
            * kwp
            * 1000.0  # kW → W
            * (ghi / 1000.0)
            * (1.0 - self.TEMP_COEFF * (t_cell - 25.0))
        )
        p_pv = np.clip(p_pv, 0.0, None)
        return p_pv.astype(np.float32)

    def get_pv_curve_kwh_per_slot(self, target_date: date, kwp: float) -> np.ndarray:
        """Energy per 15-menit slot dalam kWh."""
        p_w = self.simulate_day(target_date, kwp)
        return (p_w / 1000.0) * 0.25  # Watt → kWh per 15 menit


_solar_engine = SolarEngine()


def get_solar_engine() -> SolarEngine:
    return _solar_engine
