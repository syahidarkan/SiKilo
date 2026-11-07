"""Tes komponen tiruan digital: baterai, pola pesanan, validasi, skrip NASA."""
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel

from app.core.config import settings
from app.core.tariff import tariff_idr_per_kwh
from app.digital_twin.battery import Battery
from app.digital_twin.orders import IDUL_FITRI_DATES, OrderBook, SeasonalWindow
from app.digital_twin.solar_engine import SolarEngine
from app.digital_twin.weather import WeatherProvider

BACKEND = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = BACKEND / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"waskita_script_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


validate_twin = _load_script("validate_twin")


# ── Baterai ──────────────────────────────────────────────────────────────────
class TestBattery:
    def test_soc_never_below_min(self):
        b = Battery(10_000, 5_000, 5_000, soc_min_frac=0.2, soc_init_frac=0.5)
        for _ in range(200):
            b.step(-4_000)
            assert b.soc_wh >= b.soc_min_wh - 1e-9
        assert b.soc_wh == pytest.approx(2_000)

    def test_init_soc_clipped_to_min(self):
        b = Battery(10_000, 1_000, 1_000, soc_min_frac=0.3, soc_init_frac=0.1)
        assert b.soc_wh == pytest.approx(3_000)

    def test_efficiency_split_evenly(self):
        b = Battery(10_000, 2_000, 2_000, efficiency_rt=0.81, soc_init_frac=0.2)
        start = b.soc_wh
        grid, curtail = b.step(1_000, dt_h=1.0)
        assert (grid, curtail) == (0.0, 0.0)
        assert b.soc_wh - start == pytest.approx(900.0)  # √0,81 = 0,9
        # Keluarkan semua yang baru masuk: AC keluar = 900 × 0,9 = 810 Wh
        grid, _ = b.step(-810, dt_h=1.0)
        assert grid == pytest.approx(0.0, abs=1e-9)
        assert b.soc_wh == pytest.approx(start, abs=1e-6)

    def test_round_trip_efficiency(self):
        b = Battery(10_000, 10_000, 10_000, efficiency_rt=0.90, soc_min_frac=0.0, soc_init_frac=0.0)
        b.step(5_000, dt_h=1.0)
        delivered = 0.0
        for _ in range(10):
            before = b.soc_wh
            grid, _ = b.step(-1_000, dt_h=1.0)
            delivered += 1_000 - grid
            if b.soc_wh == before:
                break
        assert delivered == pytest.approx(5_000 * 0.90, rel=1e-6)

    def test_charge_power_limit_curtails(self):
        b = Battery(10_000, 1_000, 1_000, soc_init_frac=0.2)
        grid, curtail = b.step(5_000, dt_h=0.25)
        assert grid == 0.0
        assert curtail == pytest.approx((5_000 - 1_000) * 0.25)

    def test_discharge_power_limit_imports(self):
        b = Battery(10_000, 1_000, 1_000, soc_init_frac=1.0)
        grid, curtail = b.step(-3_000, dt_h=0.25)
        assert curtail == 0.0
        assert grid == pytest.approx((3_000 - 1_000) * 0.25)

    def test_full_battery_curtails_everything(self):
        b = Battery(1_000, 5_000, 5_000, soc_init_frac=1.0)
        _, curtail = b.step(2_000, dt_h=0.25)
        assert curtail == pytest.approx(500.0)
        assert b.soc_wh == pytest.approx(1_000.0)

    def test_zero_capacity_is_passthrough(self):
        b = Battery(0, 0, 0)
        assert b.step(-1_000) == (pytest.approx(250.0), 0.0)
        assert b.step(800) == (0.0, pytest.approx(200.0))

    def test_reset_and_run(self):
        b = Battery.from_kwh(5.0)
        net = np.concatenate([np.full(48, 1_500.0), np.full(48, -1_500.0)])
        run = b.run(net)
        assert run.grid_import_wh.shape == (96,) and run.soc_wh.shape == (96,)
        assert np.all(run.soc_wh >= b.soc_min_wh - 1e-9)
        assert np.all(run.soc_wh <= b.capacity_wh + 1e-9)
        b.reset()
        assert b.soc_wh == pytest.approx(2_500.0)

    def test_invalid_args(self):
        with pytest.raises(ValueError):
            Battery(-1, 1, 1)
        with pytest.raises(ValueError):
            Battery(1, 1, 1, efficiency_rt=1.5)


# ── Pola pesanan ─────────────────────────────────────────────────────────────
class PydJob(BaseModel):
    machine_id: str
    daily_runtime_minutes: int
    earliest_hour: int = 7
    deadline_hour: int = 17


@dataclass
class DcJob:
    machine_id: str
    daily_runtime_minutes: int


class PlainJob:
    def __init__(self, minutes: int):
        self.daily_runtime_minutes = minutes


# 2025-10-06 adalah Senin (di luar jendela musiman default).
MONDAY = date(2025, 10, 6)


class TestOrderBook:
    def test_weekly_pattern(self):
        book = OrderBook()
        sat, sun = MONDAY + timedelta(days=5), MONDAY + timedelta(days=6)
        assert book.factor_for(MONDAY) == pytest.approx(1.0)
        assert book.factor_for(sat) > book.factor_for(MONDAY)
        assert book.factor_for(sun) == 0.0
        assert "libur" in book.explain(sun)

    def test_lebaran_windows(self):
        book = OrderBook(weekday_factors=(1.0,) * 7)
        lebaran = IDUL_FITRI_DATES[2026]
        assert book.factor_for(lebaran - timedelta(days=14)) > 1.2
        assert book.factor_for(lebaran) == 0.0
        assert "Lebaran" in book.explain(lebaran - timedelta(days=14))

    def test_school_year_window(self):
        book = OrderBook(weekday_factors=(1.0,) * 7)
        assert book.factor_for(date(2026, 7, 1)) > 1.0
        assert book.factor_for(date(2026, 8, 20)) == pytest.approx(1.0)

    def test_custom_windows_and_cap(self):
        w = [SeasonalWindow("Pesanan besar", MONDAY, MONDAY, 5.0)]
        book = OrderBook(seasonal_windows=w, max_factor=2.0)
        assert book.factor_for(MONDAY) == 2.0

    def test_jobs_for_pydantic_dataclass_plain_dict(self):
        book = OrderBook()
        sat = MONDAY + timedelta(days=5)
        jobs = [PydJob(machine_id="a", daily_runtime_minutes=200), DcJob("b", 100), PlainJob(60),
                {"machine_id": "d", "daily_runtime_minutes": 30}]
        out = book.jobs_for(sat, jobs)
        assert len(out) == len(jobs)
        assert isinstance(out[0], PydJob) and isinstance(out[1], DcJob) and isinstance(out[2], PlainJob)
        assert out[0].daily_runtime_minutes == 240     # 200×1,2 = 240
        assert out[1].daily_runtime_minutes == 120
        assert out[2].daily_runtime_minutes == 75      # 72 → 75 (kelipatan 15)
        assert out[3]["daily_runtime_minutes"] == 30   # 36 → 30
        # Input tidak berubah
        assert jobs[0].daily_runtime_minutes == 200 and jobs[1].daily_runtime_minutes == 100
        for j in out[:3]:
            assert j.daily_runtime_minutes % 15 == 0

    def test_sunday_zero_runtime_keeps_jobs(self):
        out = OrderBook().jobs_for(MONDAY + timedelta(days=6), [DcJob("a", 120), DcJob("b", 60)])
        assert [j.daily_runtime_minutes for j in out] == [0, 0]

    def test_runtime_capped_by_window(self):
        book = OrderBook(weekday_factors=(2.0,) * 7)
        out = book.jobs_for(MONDAY, [PydJob(machine_id="a", daily_runtime_minutes=400, earliest_hour=8,
                                            deadline_hour=14)])
        assert out[0].daily_runtime_minutes == 360

    def test_small_positive_factor_keeps_minimum_slot(self):
        book = OrderBook(weekday_factors=(0.05,) * 7)
        assert book.jobs_for(MONDAY, [DcJob("a", 60)])[0].daily_runtime_minutes == 15

    def test_from_csv_learns_weekday_and_overrides(self, tmp_path):
        rows = ["tanggal,pesanan"]
        for i in range(28):
            d = MONDAY + timedelta(days=i)
            n = {5: 60, 6: 0}.get(d.weekday(), 40)
            rows.append(f"{d.isoformat()},{n}")
        future = MONDAY + timedelta(days=60)  # pesanan terkonfirmasi
        rows.append(f"{future.isoformat()},88")
        path = tmp_path / "pesanan.csv"
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        book = OrderBook.from_csv(path, seasonal_windows=[])
        assert book.source == "csv"
        mean_open = (40 * 20 + 60 * 4 + 88) / 25
        assert book.weekday_factors[6] == 0.0
        assert book.weekday_factors[5] > book.weekday_factors[0]
        assert book.factor_for(future) == pytest.approx(88 / mean_open)
        # Tanggal di luar riwayat → pola mingguan hasil belajar
        later_mon = MONDAY + timedelta(days=70)
        assert later_mon.weekday() == 0
        assert book.factor_for(later_mon) == pytest.approx(40 / mean_open, rel=1e-6)

    def test_from_csv_bad_header(self, tmp_path):
        path = tmp_path / "x.csv"
        path.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError):
            OrderBook.from_csv(path)

    def test_example_orders_csv_loads(self):
        book = OrderBook.from_csv(BACKEND / "docs" / "examples" / "orders_history_example.csv")
        assert book.source == "csv" and len(book.daily_overrides) == 56


# ── Validasi tiruan digital ─────────────────────────────────────────────────
def _small_profile(**kw) -> "validate_twin.TwinProfile":
    base = dict(
        name="uji",
        machines=[validate_twin.TwinMachine("m1", "Mesin", 1000.0, 120, habit_start_hour=8)],
        baseload_w=100.0,
    )
    base.update(kw)
    return validate_twin.TwinProfile(**base)


class TestValidateTwin:
    def test_habit_load(self):
        m = [validate_twin.TwinMachine("m", "M", 1000.0, 60, habit_start_hour=9, duty_cycle=0.5)]
        load = validate_twin.habit_load_w(m, 8)
        assert load[36:40].tolist() == [500.0] * 4
        assert load.sum() == pytest.approx(2000.0)

    def test_read_meter_p_active_and_partial_days(self, tmp_path):
        ts = pd.date_range("2025-10-06 00:00", "2025-10-07 11:59", freq="5min")
        df = pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "p_active": 1200.0})
        path = tmp_path / "m.csv"
        df.to_csv(path, index=False)
        meter = validate_twin.read_meter_csv(path)
        days = sorted({d for d, _ in meter.index})
        assert days == [date(2025, 10, 6)]  # hari kedua tidak lengkap
        assert meter["kwh"].sum() == pytest.approx(1.2 * 24)

    def test_read_meter_kwh_with_timezone(self, tmp_path):
        rows = ["timestamp,kwh"] + [f"2025-10-06T{h:02d}:00:00+07:00,0.5" for h in range(24)]
        path = tmp_path / "m.csv"
        path.write_text("\n".join(rows), encoding="utf-8")
        meter = validate_twin.read_meter_csv(path)
        assert len(meter) == 24 and meter.loc[(date(2025, 10, 6), 0), "kwh"] == 0.5

    def test_perfect_twin_has_zero_error(self, tmp_path):
        prof = _small_profile()
        replay = validate_twin.TwinReplay(prof)
        rows = ["timestamp,kwh"]
        for i in range(7):
            d = MONDAY + timedelta(days=i)
            for h, kwh in enumerate(replay.hourly_kwh(d)):
                rows.append(f"{d.isoformat()}T{h:02d}:00:00,{kwh:.6f}")
        path = tmp_path / "m.csv"
        path.write_text("\n".join(rows), encoding="utf-8")
        res = validate_twin.validate(prof, meter=validate_twin.read_meter_csv(path), source="uji")
        assert res["energy_error_pct"] == pytest.approx(0.0, abs=0.01)
        assert res["bill_error_pct"] == pytest.approx(0.0, abs=0.01)
        assert res["n_days"] == 7 and res["target_met"] is True

    def test_bills_comparison_uses_tariff(self):
        prof = _small_profile()
        replay = validate_twin.TwinReplay(prof)
        hourly = sum(replay.hourly_kwh(date(2025, 10, d)) for d in range(1, 32))
        kwh = float(np.sum(hourly))
        expected_rp = sum(hourly[h] * tariff_idr_per_kwh(h) for h in range(24))
        bills = pd.DataFrame({"bulan": ["2025-10"], "kwh": [kwh * 1.2], "rp": [expected_rp * 1.2]})
        res = validate_twin.validate(prof, bills=bills, source="pln_bill")
        # sim = real/1,2 → selisih 16,67 %
        assert res["bill_error_pct"] == pytest.approx(100 * (1 - 1 / 1.2), abs=0.05)
        assert res["n_days"] == 31 and res["target_met"] is False

    def test_ppj_and_minimum_charge(self):
        prof = _small_profile(ppj_pct=10.0, connected_power_va=100_000)
        cost = validate_twin.bill_idr(1000.0, 1.0, prof)
        assert cost == pytest.approx(40 * 100 * 1000.0 * 1.1)

    def test_pv_and_battery_reduce_import(self, tmp_path):
        solar = SolarEngine(weather=WeatherProvider(cache_dir=tmp_path, allow_network=False))
        base = validate_twin.TwinReplay(_small_profile(), solar=solar).hourly_kwh(MONDAY).sum()
        pv = validate_twin.TwinReplay(_small_profile(pv_kwp=2.0), solar=solar)
        pv_kwh = pv.hourly_kwh(MONDAY).sum()
        bat_kwh = validate_twin.TwinReplay(_small_profile(pv_kwp=2.0, battery_kwh=5.0), solar=solar) \
            .hourly_kwh(MONDAY).sum()
        assert pv_kwh < base
        assert bat_kwh <= pv_kwh
        assert pv.solar_sources == {"clearsky_scaled"}

    def test_example_run_writes_contract_json(self, tmp_path):
        out = tmp_path / "twin_validation.json"
        rc = validate_twin.main(["--example", "--output", str(out)])
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        for key, typ in (("bill_error_pct", float), ("energy_error_pct", float), ("n_days", int),
                         ("source", str), ("generated_at", str)):
            assert isinstance(data[key], typ), key
        assert data["source"] == "example"
        assert "BELUM divalidasi" in data["catatan"]
        assert data["n_days"] > 0

    def test_requires_some_input(self):
        with pytest.raises(ValueError):
            validate_twin.validate(_small_profile())


# ── Skrip NASA POWER ─────────────────────────────────────────────────────────
def test_fetch_script_uses_provider_without_real_network(tmp_path, monkeypatch):
    fetch = _load_script("fetch_nasa_power")
    calls = []

    def fake_fetch(self, lat, lon, year, save=True):
        calls.append(year)
        data = {"days": {f"{year}-01-01": {"ghi": [0.0] * 6 + [500.0] * 12 + [0.0] * 6, "t2m": [27.0] * 24}}}
        self._write_cache(data, lat, lon, year)
        return data

    monkeypatch.setattr(fetch.WeatherProvider, "fetch_year", fake_fetch)
    last = date.today().year - 1
    rc = fetch.main(["--years", str(last), str(last + 1), "--cache-dir", str(tmp_path)])
    assert rc == 0
    assert calls == [last]  # tahun berjalan dilewati
    assert (tmp_path / f"nasa_power_{settings.site_latitude:.2f}_{settings.site_longitude:.2f}_{last}.json").exists()
    # Jalankan lagi: cache sudah ada, tidak mengunduh ulang
    fetch.main(["--years", str(last), "--cache-dir", str(tmp_path)])
    assert calls == [last]
