from datetime import date, datetime, timedelta

import pytest

from app.nilm.classifier import ClassificationResult, NILMClassifier
from app.nilm.disaggregator import DisaggregationUpdate, HourlyEnergy, LoadDisaggregator
from app.nilm.event_detector import TelemetrySample
from app.nilm.profiles import BASELOAD_LABEL, PROFILE_BY_LABEL

T0 = datetime(2026, 11, 7, 9, 58, 0)
SETRIKA = "Setrika Pemanas Uap"
DRUM = "Motor Drum Pengering Laundry"
JAHIT = "Motor Jahit Induksi"


def _sample(t: int, p: float, q: float) -> TelemetrySample:
    return TelemetrySample(T0 + timedelta(seconds=t), p, q, 220.0, p / 220.0, 50.0)


class Feeder:
    """Bangun deret 1 Hz dari daftar segmen (durasi detik, mesin aktif)."""

    BASE_P, BASE_Q = 250.0, 60.0

    def __init__(self, disagg: LoadDisaggregator):
        self.d = disagg
        self.t = 0
        self.updates: list[DisaggregationUpdate] = []
        self.p_series: list[float] = []

    def run(self, seconds: int, machines: dict[str, float], inrush: dict[str, float] | None = None):
        for k in range(seconds):
            p = self.BASE_P
            q = self.BASE_Q
            for label, scale in machines.items():
                prof = PROFILE_BY_LABEL[label]
                mult = (inrush or {}).get(label, 1.0) if k == 0 else 1.0
                p += prof.power_w * scale * mult
                q += prof.power_w * scale * prof.q_ratio * mult
            self.updates.append(self.d.push(_sample(self.t, p, q)))
            self.p_series.append(p)
            self.t += 1


def _heuristic_disagg(**kw) -> LoadDisaggregator:
    return LoadDisaggregator(classifier=NILMClassifier(use_model=False), **kw)


def test_contract_default_constructor():
    d = LoadDisaggregator()
    assert isinstance(d.classifier, NILMClassifier)
    upd = d.push(_sample(0, 300, 50))
    assert isinstance(upd, DisaggregationUpdate)
    assert upd.event is None and upd.classification is None
    assert d.pop_hourly_energy() == []


def test_on_off_tracking_and_active_power():
    f = Feeder(_heuristic_disagg())
    f.run(10, {})
    f.run(30, {SETRIKA: 1.0})
    on_events = [u for u in f.updates if u.event is not None]
    assert len(on_events) == 1 and on_events[0].classification.label == SETRIKA
    assert f.updates[-1].active[SETRIKA] == pytest.approx(1200, abs=5)
    assert f.updates[-1].baseload_w == pytest.approx(250, abs=5)
    f.run(20, {})
    assert f.updates[-1].active == {}
    off = [u for u in f.updates if u.event is not None and u.event.event_type == "OFF"]
    assert len(off) == 1 and off[0].classification.label == SETRIKA


def test_overlapping_machines_off_matched_by_nearest_delta():
    f = Feeder(_heuristic_disagg())
    f.run(10, {})
    f.run(20, {SETRIKA: 1.0}, inrush={SETRIKA: 1.05})
    f.run(20, {SETRIKA: 1.0, JAHIT: 1.0}, inrush={JAHIT: 3.0})
    assert set(f.updates[-1].active) == {SETRIKA, JAHIT}
    f.run(20, {SETRIKA: 1.0})  # jahit OFF, setrika tetap
    assert set(f.updates[-1].active) == {SETRIKA}
    assert f.updates[-1].active[SETRIKA] == pytest.approx(1200, abs=10)


def test_off_matched_by_power_when_classifier_is_wrong():
    """OFF dicocokkan ke instans aktif dengan |ΔP| terdekat walau classifier salah label."""

    class Fixed:
        def __init__(self):
            self.calls = 0

        def predict(self, event):
            self.calls += 1
            if event.event_type == "ON":
                lab = SETRIKA if event.delta_p > 1100 else JAHIT
                return ClassificationResult(3 if lab == SETRIKA else 1, lab, 0.9, "heuristic")
            return ClassificationResult(5, "Kompresor Pendingin Freezer", 0.4, "heuristic")

    f = Feeder(LoadDisaggregator(classifier=Fixed()))
    f.run(10, {})
    f.run(20, {SETRIKA: 1.0})
    f.run(20, {SETRIKA: 1.0, JAHIT: 1.0})
    f.run(20, {JAHIT: 1.0})  # setrika OFF
    off = [u for u in f.updates if u.event is not None and u.event.event_type == "OFF"][0]
    assert off.classification.label == SETRIKA
    assert set(f.updates[-1].active) == {JAHIT}


def test_resistive_off_does_not_switch_off_motor_with_similar_power():
    """ΔQ ikut dicek: OFF resistif tidak boleh mematikan drum (motor) berdaya mirip."""

    class Clf:
        def predict(self, event):
            # ON resistif dianggap beban latar (tidak ada instans), drum dikenali.
            if abs(event.delta_q) < 100:
                return ClassificationResult(0, BASELOAD_LABEL, 0.6, "heuristic")
            return ClassificationResult(4, DRUM, 0.9, "heuristic")

    d = LoadDisaggregator(classifier=Clf())
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {DRUM: 1.0}, inrush={DRUM: 2.2})
    assert set(f.updates[-1].active) == {DRUM}
    drum_p, drum_q = 950.0, 950.0 * 0.40
    for _ in range(20):  # beban resistif ~950 W ON
        f.updates.append(d.push(_sample(f.t, 250 + drum_p + 950, 60 + drum_q)))
        f.t += 1
    for _ in range(20):  # … lalu OFF
        f.updates.append(d.push(_sample(f.t, 250 + drum_p, 60 + drum_q)))
        f.t += 1
    offs = [u for u in f.updates if u.event is not None and u.event.event_type == "OFF"]
    assert len(offs) == 1
    assert DRUM in f.updates[-1].active


def _energy_by_hour(items: list[HourlyEnergy]) -> dict[tuple[date, int], float]:
    out: dict[tuple[date, int], float] = {}
    for h in items:
        out[(h.day, h.hour)] = out.get((h.day, h.hour), 0.0) + h.kwh
    return out


def test_energy_conservation_and_hourly_pop():
    f = Feeder(_heuristic_disagg())
    f.run(30, {})
    f.run(100, {SETRIKA: 1.0})          # melewati 10:00
    f.run(60, {SETRIKA: 1.0, JAHIT: 1.0}, inrush={JAHIT: 3.0})
    f.run(50, {JAHIT: 1.0})
    # Jam 09 sudah selesai (sampel terakhir di jam 10) → dikeluarkan sekali.
    popped = f.d.pop_hourly_energy()
    assert popped and {h.hour for h in popped} == {9}
    assert f.d.pop_hourly_energy() == []
    rest = f.d.flush_hourly_energy()
    assert {h.hour for h in rest} == {10}

    measured = sum(f.p_series[1:]) * 1.0 / 3.6e6  # Δt = 1 s, sampel pertama tak punya Δt
    total = sum(h.kwh for h in popped + rest)
    assert total == pytest.approx(measured, rel=1e-9)

    labels = {h.appliance_label for h in popped + rest}
    assert {SETRIKA, JAHIT, BASELOAD_LABEL} <= labels
    setrika_kwh = sum(h.kwh for h in popped + rest if h.appliance_label == SETRIKA)
    assert setrika_kwh == pytest.approx(1200 * 160 / 3.6e6, rel=0.1)


def test_estimates_scaled_when_exceeding_measured_total():
    d = _heuristic_disagg()
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {SETRIKA: 1.0})
    # Paksa estimasi melebihi total terukur (mis. OFF terlewat).
    d._instances.append(type(d._instances[0])(JAHIT, 1, 5000.0, 1000.0, T0))  # noqa: SLF001
    upd = d.push(_sample(f.t, 1450, 100))
    assert sum(upd.active.values()) == pytest.approx(1450)
    assert upd.baseload_w == 0.0
    assert upd.active[JAHIT] / upd.active[SETRIKA] == pytest.approx(5000 / 1200, rel=0.02)


def test_stale_instance_pruned_after_missed_off():
    d = _heuristic_disagg(stale_s=30)
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {SETRIKA: 1.0})
    # Setrika mati di tengah lonjakan beban lain (OFF tak terdeteksi) → simulasikan
    # dengan menghapus detektor transien: daya turun drastis & lama.
    d.detector.reset()
    for k in range(60):
        d.push(_sample(f.t + k, 250, 60))
    assert d.active_appliances() == {}


def test_hourly_energy_contains_only_completed_hours():
    d = _heuristic_disagg()
    for k in range(10):
        d.push(_sample(k, 400, 50))
    assert d.pop_hourly_energy() == []  # jam 09 belum selesai


def test_max_instances_per_label_replaces_stale_instance():
    d = _heuristic_disagg(max_instances_per_label=1)
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {JAHIT: 1.0}, inrush={JAHIT: 3.0})
    # OFF jahit "terlewat": level turun tanpa event (reset detektor), lalu ON lagi.
    d.detector.reset()
    f.run(5, {})
    d.detector.reset()
    f.run(5, {})
    f.run(20, {JAHIT: 1.0}, inrush={JAHIT: 3.0})
    jahit = [i for i in d._instances if i.label == JAHIT]  # noqa: SLF001
    assert len(jahit) == 1


def test_unlimited_instances_by_default():
    d = _heuristic_disagg()
    assert d.max_instances_per_label is None


def test_classified_off_matches_same_label_with_loose_tolerance():
    """ON terdistorsi (ΔP terukur 140 W untuk freezer 180 W) tetap bisa dimatikan OFF freezer."""

    class Clf:
        def predict(self, event):
            return ClassificationResult(5, "Kompresor Pendingin Freezer", 0.9, "heuristic")

    d = LoadDisaggregator(classifier=Clf())
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {"Kompresor Pendingin Freezer": 140 / 180})
    f.run(20, {})  # OFF terukur 140 W → cocok; uji tahap 2 lewat instans 140 vs OFF 180:
    assert d.active_appliances() == {}
    f.run(20, {"Kompresor Pendingin Freezer": 140 / 180})
    # OFF 180 W (lebih besar dari instans 140 W, di luar toleransi ketat 25%)
    for _ in range(20):
        d.push(_sample(f.t, Feeder.BASE_P - 40, Feeder.BASE_Q - 30))
        f.t += 1
    assert d.active_appliances() == {}


def test_q_deficit_prunes_small_machine_hidden_by_baseload():
    d = _heuristic_disagg(stale_s=30)
    f = Feeder(d)
    f.run(10, {})
    f.run(20, {"Kompresor Pendingin Freezer": 1.0}, inrush={"Kompresor Pendingin Freezer": 3.5})
    assert "Kompresor Pendingin Freezer" in d.active_appliances()
    # Freezer mati bersamaan dengan beban resistif 180 W menyala → P tetap, Q turun.
    d.detector.reset()
    for _ in range(80):
        d.push(_sample(f.t, Feeder.BASE_P + 180, Feeder.BASE_Q))
        f.t += 1
    assert d.active_appliances() == {}
