"""
Mesin surya tiruan digital WASKITA: kurva daya AC PLTS atap per 15 menit.

Alur per hari (96 slot × 15 menit, slot t ↔ jam t // 4):

1. Cuaca per jam dari NASA POWER (``weather.py``): GHI semua-langit + suhu
   udara. Untuk tanggal masa depan/tahun berjalan dipakai hari yang sama di
   tahun lengkap terakhir. Bila tidak tersedia → fallback GHI clear-sky
   (pvlib Ineichen) × ``settings.clearness_index_fallback`` dan suhu
   sinusoidal; ``last_source`` menjadi ``"clearsky_scaled"``.
2. Jam → slot: indeks kecerahan per jam (GHI NASA / rata-rata clear-sky jam
   itu) dikalikan bentuk clear-sky per slot, sehingga energi per jam tetap
   sama dengan data NASA sementara bentuk kurva di dalam jam tetap halus.
3. GHI → POA: dekomposisi Erbs + transposisi isotropik untuk kemiringan
   ``settings.pv_tilt_deg`` (default 10°, menghadap utara). Di dekat
   khatulistiwa selisih POA vs GHI kecil (beberapa persen), jadi model
   sederhana ini cukup; ``pv_tilt_deg = 0`` membuat POA = GHI.
4. Suhu sel: model Faiman pvlib (u0=25, u1=6,84, angin asumsi
   ``settings.pv_wind_speed_ms``).
5. Daya: ``P_ac = kWp·POA/1000·(1 + γ·(T_sel − 25))·(1 − rugi_sistem)·η_inv``,
   dibatasi kapasitas inverter (= kWp).

Catatan jujur: model ini belum divalidasi terhadap produksi PLTS nyata di
Sukoharjo; lihat ``docs/DIGITAL_TWIN.md`` dan ``scripts/validate_twin.py``.
"""
from __future__ import annotations

import calendar
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location

from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS
from app.digital_twin.weather import DailyWeather, WeatherProvider, get_weather_provider

SOURCE_NASA = "nasa_power"
SOURCE_CLEARSKY = "clearsky_scaled"

_SLOTS_PER_HOUR = int(round(1.0 / SLOT_HOURS))
_CACHE_MAX = 4096


@dataclass
class SolarDayResult:
    """Rincian simulasi satu hari untuk 1 kWp (kalikan kWp untuk daya)."""

    target_date: date
    source: str                 # "nasa_power" | "clearsky_scaled"
    source_date: date           # tanggal data cuaca yang dipakai
    ghi_w_m2: np.ndarray        # (96,)
    poa_w_m2: np.ndarray        # (96,)
    t_air_c: np.ndarray         # (96,)
    t_cell_c: np.ndarray        # (96,)
    p_ac_per_kwp_w: np.ndarray  # (96,) W AC per kWp

    def p_ac_w(self, kwp: float) -> np.ndarray:
        return (self.p_ac_per_kwp_w * float(kwp)).astype(np.float32)


def _sinusoidal_temperature(hours: np.ndarray) -> np.ndarray:
    """Suhu udara harian sederhana: ~24 °C menjelang subuh, ~33 °C pukul 14."""
    return 28.5 + 4.5 * np.cos(2.0 * np.pi * (hours - 14.0) / 24.0)


class SolarEngine:
    """
    Simulasi output daya PLTS (W AC, 96 slot/hari) untuk lokasi UMKM.
    Default lokasi Sukoharjo (settings.site_latitude/longitude).
    """

    INVERTER_EFF: float = 0.96

    def __init__(self, weather: Optional[WeatherProvider] = None) -> None:
        self._weather = weather
        self.last_source: str = SOURCE_CLEARSKY
        self.last_source_date: Optional[date] = None
        self._cache: "OrderedDict[tuple, SolarDayResult]" = OrderedDict()

    @property
    def weather(self) -> WeatherProvider:
        return self._weather if self._weather is not None else get_weather_provider()

    # ── geometri & clear-sky ───────────────────────────────────────────────
    @staticmethod
    def _location(lat: float, lon: float) -> Location:
        is_site = abs(lat - settings.site_latitude) < 1e-6 and abs(lon - settings.site_longitude) < 1e-6
        return Location(
            latitude=lat,
            longitude=lon,
            altitude=settings.site_altitude_m if is_site else 0.0,
            tz=settings.site_timezone,
        )

    @staticmethod
    def _slot_times(target_date: date) -> pd.DatetimeIndex:
        start = pd.Timestamp(datetime.combine(target_date, datetime.min.time()), tz=settings.site_timezone)
        # Titik tengah tiap slot 15 menit.
        return pd.date_range(start=start + pd.Timedelta(minutes=7.5), periods=N_SLOTS, freq="15min")

    # ── jam → slot ─────────────────────────────────────────────────────────
    @staticmethod
    def _hourly_ghi_to_slots(ghi_hourly: np.ndarray, cs_slot: np.ndarray) -> np.ndarray:
        cs_by_hour = cs_slot.reshape(24, _SLOTS_PER_HOUR)
        cs_hour_mean = cs_by_hour.mean(axis=1)
        out = np.zeros_like(cs_by_hour)
        for h in range(24):
            g = float(ghi_hourly[h])
            if g <= 0.0:
                continue
            if cs_hour_mean[h] > 5.0:
                kt = min(g / cs_hour_mean[h], 1.3)
                out[h] = cs_by_hour[h] * kt
            else:
                # Jam fajar/senja: clear-sky ~0 tetapi data menunjukkan cahaya.
                out[h] = g
        return out.reshape(-1)

    @staticmethod
    def _hourly_temp_to_slots(t_hourly: np.ndarray) -> np.ndarray:
        x_hour = np.arange(24) + 0.5
        x_slot = (np.arange(N_SLOTS) + 0.5) * SLOT_HOURS
        return np.interp(x_slot, x_hour, t_hourly, period=24.0)

    # ── inti simulasi ──────────────────────────────────────────────────────
    def _simulate_block(self, dates: list[date], lat: float, lon: float) -> list[SolarDayResult]:
        """
        Simulasi beberapa hari sekaligus (untuk 1 kWp). Posisi matahari,
        clear-sky, transposisi, dan suhu sel dihitung tervektorisasi agar
        perhitungan setahun (sizing) cepat.
        """
        n = len(dates)
        loc = self._location(lat, lon)
        times = self._slot_times(dates[0])
        if n > 1:
            times = times.append([self._slot_times(d) for d in dates[1:]])
        solpos = loc.get_solarposition(times)
        clearsky = loc.get_clearsky(times, model="ineichen", solar_position=solpos)
        cs_ghi = np.clip(clearsky["ghi"].to_numpy(dtype=np.float64), 0.0, None).reshape(n, N_SLOTS)
        hours = (np.arange(N_SLOTS) + 0.5) * SLOT_HOURS

        ghi = np.zeros((n, N_SLOTS))
        t_air = np.zeros((n, N_SLOTS))
        sources: list[tuple[str, date]] = []
        for i, d in enumerate(dates):
            weather: Optional[DailyWeather] = None
            if settings.use_nasa_power:
                weather = self.weather.get_day(d, lat, lon)
            if weather is not None:
                ghi[i] = self._hourly_ghi_to_slots(weather.ghi_hourly, cs_ghi[i])
                t_air[i] = self._hourly_temp_to_slots(weather.t2m_hourly)
                sources.append((SOURCE_NASA, weather.source_date))
            else:
                ghi[i] = cs_ghi[i] * float(settings.clearness_index_fallback)
                t_air[i] = _sinusoidal_temperature(hours)
                sources.append((SOURCE_CLEARSKY, d))

        ghi_flat = ghi.reshape(-1)
        t_air_flat = t_air.reshape(-1)
        poa = self._poa(ghi_flat, solpos, times)
        t_cell = np.asarray(
            pvlib.temperature.faiman(poa, t_air_flat, wind_speed=settings.pv_wind_speed_ms), dtype=np.float64
        )
        p_dc = poa * (1.0 + settings.pv_temp_coeff_per_c * (t_cell - 25.0))  # W per kWp (STC 1000 W/m²)
        p_ac = p_dc * (1.0 - settings.pv_system_losses_frac) * self.INVERTER_EFF
        p_ac = np.clip(p_ac, 0.0, 1000.0)  # batas inverter = 1 kW per kWp

        out = []
        for i, d in enumerate(dates):
            sl = slice(i * N_SLOTS, (i + 1) * N_SLOTS)
            out.append(SolarDayResult(
                target_date=d,
                source=sources[i][0],
                source_date=sources[i][1],
                ghi_w_m2=ghi[i].astype(np.float32),
                poa_w_m2=poa[sl].astype(np.float32),
                t_air_c=t_air[i].astype(np.float32),
                t_cell_c=t_cell[sl].astype(np.float32),
                p_ac_per_kwp_w=p_ac[sl].astype(np.float64),
            ))
        return out

    @staticmethod
    def _poa(ghi: np.ndarray, solpos: pd.DataFrame, times: pd.DatetimeIndex) -> np.ndarray:
        tilt = float(settings.pv_tilt_deg)
        if tilt <= 0.0:
            return np.clip(ghi, 0.0, None)
        ghi_s = pd.Series(ghi, index=times)
        zen = solpos["zenith"]
        parts = pvlib.irradiance.erbs(ghi_s, zen, times)
        dni = parts["dni"].fillna(0.0)
        dhi = parts["dhi"].fillna(0.0)
        total = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilt,
            surface_azimuth=float(settings.pv_azimuth_deg),
            solar_zenith=solpos["apparent_zenith"],
            solar_azimuth=solpos["azimuth"],
            dni=dni,
            ghi=ghi_s,
            dhi=dhi,
            albedo=0.2,
            model="isotropic",
        )
        poa = total["poa_global"].fillna(0.0).to_numpy(dtype=np.float64)
        poa = np.where(ghi > 0.0, np.clip(poa, 0.0, None), 0.0)
        return poa

    # ── API publik (kontrak) ───────────────────────────────────────────────
    def simulate_day_detailed(
        self,
        target_date: date,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> SolarDayResult:
        lat = settings.site_latitude if lat is None else float(lat)
        lon = settings.site_longitude if lon is None else float(lon)
        key = (target_date, round(lat, 4), round(lon, 4))
        result = self._cache.get(key)
        if result is None:
            # Hitung sebulan sekaligus: panggilan berikutnya (mis. sizing 365 hari) jadi instan.
            first = target_date.replace(day=1)
            n_days = calendar.monthrange(first.year, first.month)[1]
            block = [first + timedelta(days=i) for i in range(n_days)]
            block = [d for d in block if (d, key[1], key[2]) not in self._cache]
            for res in self._simulate_block(block, lat, lon):
                self._cache[(res.target_date, key[1], key[2])] = res
            while len(self._cache) > _CACHE_MAX:
                self._cache.popitem(last=False)
            result = self._cache[key]
        else:
            self._cache.move_to_end(key)
        self.last_source = result.source
        self.last_source_date = result.source_date
        return result

    def simulate_day(
        self,
        target_date: date,
        kwp: float,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> np.ndarray:
        """
        Kurva daya AC PLTS satu hari.

        Returns:
            np.ndarray shape (96,), Watt AC per slot 15 menit (≥ 0).
        """
        if kwp <= 0:
            return np.zeros(N_SLOTS, dtype=np.float32)
        return self.simulate_day_detailed(target_date, lat, lon).p_ac_w(kwp)

    def get_pv_curve_kwh_per_slot(
        self, target_date: date, kwp: float, lat: Optional[float] = None, lon: Optional[float] = None
    ) -> np.ndarray:
        """Energi per slot 15 menit dalam kWh."""
        p_w = self.simulate_day(target_date, kwp, lat, lon)
        return (p_w / 1000.0) * SLOT_HOURS

    def clear_cache(self) -> None:
        self._cache.clear()


_solar_engine: Optional[SolarEngine] = None


def get_solar_engine() -> SolarEngine:
    global _solar_engine
    if _solar_engine is None:
        _solar_engine = SolarEngine()
    return _solar_engine
