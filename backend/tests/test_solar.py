"""Tes mesin surya + cuaca. Tidak ada panggilan jaringan (HTTP di-mock)."""
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from app.core.config import settings
from app.digital_twin.solar_engine import SOURCE_CLEARSKY, SOURCE_NASA, SolarEngine
from app.digital_twin.weather import (
    WeatherProvider,
    build_request_url,
    parse_power_response,
    resolve_source_date,
)

LAT, LON = settings.site_latitude, settings.site_longitude
SOLAR_NOON_H = 11.6  # tengah hari matahari ~11:36 WIB di 110,8° BT


def _fake_power_payload(year: int, scale: float = 1.0, days: int | None = None) -> dict:
    """Respons mirip NASA POWER: lonceng GHI 06–18, suhu 23–32 °C."""
    ghi, t2m = {}, {}
    d = date(year, 1, 1)
    end = date(year, 12, 31) if days is None else d + timedelta(days=days - 1)
    while d <= end:
        for h in range(24):
            key = f"{d:%Y%m%d}{h:02d}"
            x = (h + 0.5 - SOLAR_NOON_H) / 6.0
            ghi[key] = round(max(0.0, 950.0 * (1 - x * x)) * scale, 2) if 6 <= h < 18 else 0.0
            t2m[key] = round(27.5 + 4.5 * np.cos(2 * np.pi * (h - 14) / 24), 2)
        d += timedelta(days=1)
    return {
        "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": ghi, "T2M": t2m}},
        "header": {"fill_value": -999.0},
    }


class FakeHttp:
    def __init__(self, scale: float = 1.0, fail: bool = False):
        self.calls: list[str] = []
        self.scale = scale
        self.fail = fail

    def __call__(self, url: str, timeout_s: float) -> dict:
        self.calls.append(url)
        if self.fail:
            raise OSError("jaringan mati (tes)")
        year = int(url.split("start=")[1][:4])
        return _fake_power_payload(year, self.scale)


@pytest.fixture
def offline_engine(tmp_path):
    """Mesin tanpa cache & tanpa jaringan → fallback clear-sky."""
    return SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False))


@pytest.fixture
def nasa_engine(tmp_path):
    http = FakeHttp()
    eng = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=True, http_get_json=http))
    eng.http = http
    return eng


class TestSolarEngineFallback:
    def test_simulate_day_shape(self, offline_engine):
        result = offline_engine.simulate_day(date(2026, 11, 7), kwp=2.0)
        assert result.shape == (96,)
        assert offline_engine.last_source == SOURCE_CLEARSKY

    def test_no_negative_power(self, offline_engine):
        assert np.all(offline_engine.simulate_day(date(2026, 11, 7), kwp=2.0) >= 0.0)

    def test_zero_at_night(self, offline_engine):
        result = offline_engine.simulate_day(date(2026, 6, 15), kwp=2.0)
        assert np.all(result[:16] == 0.0)   # 00:00–03:45
        assert np.all(result[80:] == 0.0)   # 20:00–23:45

    def test_peak_occurs_midday(self, offline_engine):
        peak_slot = int(np.argmax(offline_engine.simulate_day(date(2026, 6, 15), kwp=2.0)))
        assert 40 <= peak_slot <= 56

    def test_scales_linearly_with_kwp(self, offline_engine):
        p1 = offline_engine.simulate_day(date(2026, 6, 15), kwp=1.0)
        p2 = offline_engine.simulate_day(date(2026, 6, 15), kwp=2.0)
        assert np.sum(p2) / np.sum(p1) == pytest.approx(2.0, rel=1e-4)

    def test_zero_kwp_gives_zero(self, offline_engine):
        assert np.all(offline_engine.simulate_day(date(2026, 6, 15), kwp=0.0) == 0.0)

    def test_kwh_per_slot_non_negative(self, offline_engine):
        result = offline_engine.get_pv_curve_kwh_per_slot(date(2026, 11, 7), kwp=3.0)
        assert result.shape == (96,)
        assert np.all(result >= 0.0)

    def test_annual_yield_reasonable(self, offline_engine):
        """Yield 1 kWp di Sukoharjo kira-kira 1.100–1.500 kWh/kWp/tahun (fallback)."""
        total = sum(
            float(np.sum(offline_engine.get_pv_curve_kwh_per_slot(date(2025, m, 15), kwp=1.0))) * 30.4
            for m in range(1, 13)
        )
        assert 1000 <= total <= 1550, f"Yield {total:.0f} kWh/kWp di luar rentang wajar"

    def test_fallback_scales_with_clearness_index(self, tmp_path, monkeypatch):
        d = date(2025, 3, 10)
        monkeypatch.setattr(settings, "clearness_index_fallback", 0.5)
        low = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False)).simulate_day(d, 1.0)
        monkeypatch.setattr(settings, "clearness_index_fallback", 0.8)
        high = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False)).simulate_day(d, 1.0)
        assert high.sum() > low.sum() * 1.4

    def test_system_losses_reduce_output(self, tmp_path, monkeypatch):
        d = date(2025, 3, 10)
        monkeypatch.setattr(settings, "pv_system_losses_frac", 0.0)
        a = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False)).simulate_day(d, 1.0)
        monkeypatch.setattr(settings, "pv_system_losses_frac", 0.14)
        b = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False)).simulate_day(d, 1.0)
        assert b.sum() / a.sum() == pytest.approx(0.86, rel=1e-3)

    def test_use_nasa_power_false_skips_weather(self, tmp_path, monkeypatch):
        http = FakeHttp()
        monkeypatch.setattr(settings, "use_nasa_power", False)
        eng = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=True, http_get_json=http))
        eng.simulate_day(date(2025, 3, 10), 1.0)
        assert eng.last_source == SOURCE_CLEARSKY
        assert http.calls == []


class TestSolarEngineNasa:
    @pytest.fixture(autouse=True)
    def _enable_nasa(self, monkeypatch):
        # conftest mematikan NASA POWER (USE_NASA_POWER=false); di sini HTTP di-mock.
        monkeypatch.setattr(settings, "use_nasa_power", True)

    def test_uses_nasa_power_and_caches(self, nasa_engine, tmp_path):
        p = nasa_engine.simulate_day(date(2025, 5, 20), kwp=1.0)
        assert nasa_engine.last_source == SOURCE_NASA
        assert p.shape == (96,) and np.all(p >= 0)
        assert len(nasa_engine.http.calls) == 1
        # Hari lain di tahun yang sama: dari memori, tanpa HTTP lagi.
        nasa_engine.simulate_day(date(2025, 8, 1), kwp=1.0)
        assert len(nasa_engine.http.calls) == 1
        # Provider baru membaca cache disk, tanpa HTTP.
        http2 = FakeHttp()
        eng2 = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=True, http_get_json=http2))
        eng2.simulate_day(date(2025, 5, 20), kwp=1.0)
        assert eng2.last_source == SOURCE_NASA and http2.calls == []

    def test_hourly_energy_preserved_flat_panel(self, nasa_engine, monkeypatch):
        """Dengan panel datar, GHI per jam hasil interpolasi slot = data NASA per jam."""
        monkeypatch.setattr(settings, "pv_tilt_deg", 0.0)
        res = nasa_engine.simulate_day_detailed(date(2025, 5, 20))
        ghi_hourly = res.ghi_w_m2.reshape(24, 4).mean(axis=1)
        expected = np.array([
            max(0.0, 950.0 * (1 - ((h + 0.5 - SOLAR_NOON_H) / 6.0) ** 2)) if 6 <= h < 18 else 0.0 for h in range(24)
        ])
        mid = slice(8, 15)  # jam 08–14: kt di bawah batas 1,3 (data uji lebih lebar dari clear-sky)
        np.testing.assert_allclose(ghi_hourly[mid], expected[mid], rtol=0.02)

    def test_performance_ratio_plausible(self, nasa_engine):
        res = nasa_engine.simulate_day_detailed(date(2025, 5, 20))
        e_pv = res.p_ac_per_kwp_w.sum() * 0.25 / 1000.0      # kWh/kWp
        e_ghi = res.ghi_w_m2.sum() * 0.25 / 1000.0           # kWh/m²
        pr = e_pv / e_ghi
        assert 0.65 <= pr <= 0.90, pr

    def test_cell_hotter_than_air_at_noon(self, nasa_engine):
        res = nasa_engine.simulate_day_detailed(date(2025, 5, 20))
        assert res.t_cell_c[48] > res.t_air_c[48] + 10

    def test_future_date_uses_last_complete_year(self, nasa_engine):
        target = date.today() + timedelta(days=30)
        nasa_engine.simulate_day(target, kwp=1.0)
        assert nasa_engine.last_source == SOURCE_NASA
        assert nasa_engine.last_source_date.year == date.today().year - 1
        assert (nasa_engine.last_source_date.month, nasa_engine.last_source_date.day) == (target.month, target.day) \
            or (target.month, target.day) == (2, 29)

    def test_cloudy_day_lower(self, tmp_path):
        clear = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path / "a", allow_network=True,
                                                    http_get_json=FakeHttp(1.0)))
        cloudy = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path / "b", allow_network=True,
                                                     http_get_json=FakeHttp(0.4)))
        d = date(2025, 2, 3)
        assert cloudy.simulate_day(d, 1.0).sum() < 0.5 * clear.simulate_day(d, 1.0).sum()

    def test_network_failure_falls_back_with_backoff(self, tmp_path):
        http = FakeHttp(fail=True)
        eng = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=True, http_get_json=http))
        p = eng.simulate_day(date(2025, 4, 1), kwp=1.0)
        assert eng.last_source == SOURCE_CLEARSKY and p.sum() > 0
        n = len(http.calls)
        eng.simulate_day(date(2025, 4, 2), kwp=1.0)
        assert len(http.calls) == n  # tidak mencoba ulang selama backoff

    def test_incomplete_year_falls_back_to_previous_year(self, tmp_path):
        prov = WeatherProvider(cache_dir=tmp_path, allow_network=False)
        # Cache 2025 hanya berisi Januari; 2024 lengkap.
        prov._write_cache(parse_power_response(_fake_power_payload(2025, days=31), LAT, LON, 2025), LAT, LON, 2025)
        prov._write_cache(parse_power_response(_fake_power_payload(2024), LAT, LON, 2024), LAT, LON, 2024)
        w = prov.get_day(date(2025, 6, 1), LAT, LON, today=date(2026, 11, 7))
        assert w is not None and w.source_date == date(2024, 6, 1)


class TestWeatherHelpers:
    def test_resolve_source_date(self):
        today = date(2026, 11, 7)
        assert resolve_source_date(date(2024, 5, 1), today) == date(2024, 5, 1)
        assert resolve_source_date(date(2026, 3, 1), today) == date(2025, 3, 1)
        assert resolve_source_date(date(2027, 8, 17), today) == date(2025, 8, 17)
        assert resolve_source_date(date(2028, 2, 29), today) == date(2025, 2, 28)

    def test_request_url_parameters(self):
        url = build_request_url(-7.68, 110.83, 2025)
        assert url.startswith("https://power.larc.nasa.gov/api/temporal/hourly/point?")
        for part in ("ALLSKY_SFC_SW_DWN", "T2M", "community=RE", "time-standard=LST",
                     "start=20250101", "end=20251231"):
            assert part in url

    def test_parse_handles_fill_values(self):
        payload = _fake_power_payload(2025, days=1)
        payload["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["2025010112"] = -999.0
        data = parse_power_response(payload, LAT, LON, 2025)
        assert data["days"]["2025-01-01"]["ghi"][12] is None
        prov_day = data["days"]["2025-01-01"]
        assert len(prov_day["ghi"]) == 24 and len(prov_day["t2m"]) == 24
        json.dumps(data)  # bisa diserialisasi

    def test_day_with_missing_ghi_is_skipped(self, tmp_path):
        prov = WeatherProvider(cache_dir=tmp_path, allow_network=False)
        payload = _fake_power_payload(2025, days=2)
        payload["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["2025010112"] = -999.0
        prov._write_cache(parse_power_response(payload, LAT, LON, 2025), LAT, LON, 2025)
        assert prov.get_day(date(2025, 1, 1), LAT, LON, today=date(2026, 1, 1)) is None
        assert prov.get_day(date(2025, 1, 2), LAT, LON, today=date(2026, 1, 1)) is not None

    def test_network_disabled_under_pytest_by_default(self, tmp_path):
        assert WeatherProvider(cache_dir=tmp_path).network_allowed is False

    def test_import_does_not_touch_network(self):
        """Import modul + get_solar_engine() di proses terpisah dengan urlopen & socket diblokir."""
        code = "\n".join([
            "import socket, urllib.request",
            "def boom(*a, **k): raise SystemExit('jaringan dipanggil saat import')",
            "urllib.request.urlopen = boom",
            "socket.socket.connect = boom",
            "import app.digital_twin.weather, app.digital_twin.solar_engine as se",
            "assert se.get_solar_engine() is not None",
            "print('ok')",
        ])
        backend = Path(__file__).resolve().parents[1]
        res = subprocess.run([sys.executable, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
        assert res.returncode == 0, res.stderr
        assert "ok" in res.stdout
