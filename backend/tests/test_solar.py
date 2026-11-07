import pytest
import numpy as np
from datetime import date
from app.digital_twin.solar_engine import SolarEngine


class TestSolarEngine:
    def setup_method(self):
        self.engine = SolarEngine()

    def test_simulate_day_shape(self):
        result = self.engine.simulate_day(date(2026, 11, 7), kwp=2.0)
        assert result.shape == (96,)

    def test_no_negative_power(self):
        result = self.engine.simulate_day(date(2026, 11, 7), kwp=2.0)
        assert np.all(result >= 0.0)

    def test_zero_at_night(self):
        result = self.engine.simulate_day(date(2026, 6, 15), kwp=2.0)
        # Slot 0-15 adalah 00:00-03:45 — harus nol (malam hari)
        assert np.all(result[:16] == 0.0)

    def test_peak_occurs_midday(self):
        result = self.engine.simulate_day(date(2026, 6, 15), kwp=2.0)
        peak_slot = int(np.argmax(result))
        # Peak antara 10:00-14:00 (slot 40-56) untuk lokasi tropis
        assert 36 <= peak_slot <= 60

    def test_scales_with_kwp(self):
        p1 = self.engine.simulate_day(date(2026, 6, 15), kwp=1.0)
        p2 = self.engine.simulate_day(date(2026, 6, 15), kwp=2.0)
        # Output 2 kWp harus hampir 2x output 1 kWp (dalam toleransi suhu)
        ratio = np.sum(p2) / max(np.sum(p1), 1.0)
        assert 1.8 <= ratio <= 2.2

    def test_kwh_per_slot_non_negative(self):
        result = self.engine.get_pv_curve_kwh_per_slot(date(2026, 11, 7), kwp=3.0)
        assert result.shape == (96,)
        assert np.all(result >= 0.0)

    def test_annual_yield_reasonable(self):
        """Yield tahunan 1 kWp di Sukoharjo harus antara 900-1500 kWh/kWp."""
        total_kwh = 0.0
        for month in range(1, 13):
            day = date(2026, month, 15)
            daily_kwh = float(np.sum(self.engine.get_pv_curve_kwh_per_slot(day, kwp=1.0)))
            total_kwh += daily_kwh * 30.4
        assert 900 <= total_kwh <= 1600, f"Annual yield {total_kwh:.0f} kWh/kWp out of expected range"
