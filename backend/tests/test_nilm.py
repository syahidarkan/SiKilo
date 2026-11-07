import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.nilm.classifier import (
    APPLIANCE_LABELS,
    MODEL_FORMAT_VERSION,
    NILMClassifier,
    _heuristic_classify,
)
from app.nilm.event_detector import EventDetector, TelemetrySample, TransientEvent
from app.nilm.feature_extractor import FEATURE_NAMES, extract_features
from app.nilm.ground_truth import (
    extract_plug_transitions,
    label_events,
    load_plug_csv,
    match_events_to_transitions,
    plug_hourly_energy_kwh,
)
from app.nilm.profiles import APPLIANCE_PROFILES, BASELOAD_LABEL, PROFILE_BY_LABEL

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 11, 7, 10, 0, 0)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _s(p: float, q: float = 100.0, t: int = 0) -> TelemetrySample:
    return TelemetrySample(
        timestamp=T0 + timedelta(seconds=t), p_active=p, q_reactive=q, v_rms=220.0, i_rms=p / 220.0, frequency=50.0
    )


def _run(detector: EventDetector, series: list[tuple[float, float]]) -> list[TransientEvent]:
    events = []
    for t, (p, q) in enumerate(series):
        ev = detector.push(_s(p, q, t))
        if ev is not None:
            events.append(ev)
    return events


def _event(dp: float, dq: float, inrush: float = 1.0, kind: str | None = None, t: int = 0) -> TransientEvent:
    return TransientEvent(
        timestamp=T0 + timedelta(seconds=t),
        delta_p=dp, delta_q=dq,
        p_before=300.0, q_before=50.0, p_after=300.0 + dp, q_after=50.0 + dq,
        v_rms=220.0, i_rms=(300.0 + dp) / 220.0,
        inrush_peak_ratio=inrush,
        event_type=kind or ("ON" if dp > 0 else "OFF"),
    )


def _proto_event(label: str, on: bool = True, scale: float = 1.0) -> TransientEvent:
    p = PROFILE_BY_LABEL[label]
    dp, dq = p.power_w * scale, p.power_w * scale * p.q_ratio
    if on:
        return _event(dp, dq, inrush=p.inrush_ratio)
    return _event(-dp, -dq, inrush=1.0)


# ── Event detector ───────────────────────────────────────────────────────────
class TestEventDetector:
    def test_uses_settings_defaults(self):
        d = EventDetector()
        assert d.threshold_w == settings.nilm_event_threshold_w
        assert d.window_size == settings.nilm_event_window_s

    def test_no_event_below_threshold(self):
        events = _run(EventDetector(), [(300 + n, 100) for n in [0, 2, 1, -1, 3, 0, 2, 1]])
        assert events == []

    def test_step_on_measured_from_stable_baseline(self):
        events = _run(EventDetector(), [(300, 100)] * 5 + [(1600, 120)] * 6)
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "ON"
        assert ev.delta_p == pytest.approx(1300, abs=1)
        assert ev.delta_q == pytest.approx(20, abs=1)
        assert ev.timestamp == T0 + timedelta(seconds=5)  # onset

    def test_step_off(self):
        events = _run(EventDetector(), [(1600, 500)] * 6 + [(300, 100)] * 6)
        assert len(events) == 1
        assert events[0].event_type == "OFF"
        assert events[0].delta_p == pytest.approx(-1300, abs=1)
        assert events[0].inrush_peak_ratio == 1.0

    def test_two_sample_ramp_measures_full_step(self):
        # Ramp 300 → 900 → 1600: beda sampel berturut-turut hanya 600/700 W.
        events = _run(EventDetector(), [(300, 100)] * 5 + [(900, 200), (1600, 300)] + [(1600, 300)] * 6)
        assert len(events) == 1
        assert events[0].delta_p == pytest.approx(1300, abs=1)
        assert events[0].inrush_peak_ratio == pytest.approx(1.0)

    def test_inrush_single_event_with_ratio(self):
        series = [(300, 100)] * 5 + [(300 + 3 * 1100, 2000), (300 + 1.35 * 1100, 700)] + [(1400, 780)] * 8
        events = _run(EventDetector(), series)
        assert len(events) == 1
        ev = events[0]
        assert ev.delta_p == pytest.approx(1100, abs=1)
        assert ev.inrush_peak_ratio == pytest.approx(3.0, abs=0.01)
        assert ev.transient_duration_s == pytest.approx(2.0)

    def test_short_spike_returning_to_baseline_is_ignored(self):
        events = _run(EventDetector(), [(300, 100)] * 5 + [(900, 100)] + [(300, 100)] * 6)
        assert events == []

    def test_custom_threshold(self):
        events = _run(EventDetector(threshold_w=200), [(300, 100)] * 5 + [(420, 100)] * 6)
        assert events == []
        events = _run(EventDetector(threshold_w=50), [(300, 100)] * 5 + [(420, 100)] * 6)
        assert len(events) == 1

    def test_unstable_transient_is_forced_closed(self):
        d = EventDetector(max_transient_s=8)
        series = [(300, 100)] * 5 + [(1500 + (400 if i % 2 else 0), 300) for i in range(12)]
        events = _run(d, series)
        assert len(events) == 1
        assert events[0].delta_p > 1000


# ── Fitur ────────────────────────────────────────────────────────────────────
class TestFeatureExtractor:
    def test_feature_vector_shape_and_order(self):
        f = extract_features(_event(1000, 100, inrush=1.8))
        assert f.shape == (len(FEATURE_NAMES),)
        assert f[FEATURE_NAMES.index("abs_delta_p")] == pytest.approx(1000)
        assert f[FEATURE_NAMES.index("ratio_q_p")] == pytest.approx(0.1)
        assert f[FEATURE_NAMES.index("is_on")] == 1.0

    def test_off_event_uses_absolute_values(self):
        f = extract_features(_event(-1000, -400))
        assert f[FEATURE_NAMES.index("abs_delta_p")] == pytest.approx(1000)
        assert f[FEATURE_NAMES.index("ratio_q_p")] == pytest.approx(0.4)
        assert f[FEATURE_NAMES.index("is_on")] == 0.0

    def test_no_time_features(self):
        assert not any("hour" in n or "day" in n for n in FEATURE_NAMES)


# ── Classifier ───────────────────────────────────────────────────────────────
class TestHeuristic:
    @pytest.mark.parametrize("prof", APPLIANCE_PROFILES, ids=lambda p: p.label)
    def test_prototypes_on_and_off(self, prof):
        assert _heuristic_classify(_proto_event(prof.label, on=True)).appliance_class == prof.appliance_class
        assert _heuristic_classify(_proto_event(prof.label, on=False)).appliance_class == prof.appliance_class

    def test_small_event_is_background(self):
        r = _heuristic_classify(_event(30, 5))
        assert r.appliance_class == 0 and r.label == BASELOAD_LABEL

    def test_far_from_all_prototypes_is_background(self):
        r = _heuristic_classify(_event(5000, 100, inrush=1.0))
        assert r.appliance_class == 0

    def test_overlapping_power_separated_by_q_and_inrush(self):
        # ΔP sama 1050 W: resistif → setrika; Q/P 0.62 + inrush 4 → kompresor; Q/P 0.4 + inrush 2.2 → drum
        assert _heuristic_classify(_event(1050, 30, inrush=1.05)).label == "Setrika Pemanas Uap"
        assert _heuristic_classify(_event(1050, 650, inrush=4.0)).label == "Kompresor Udara Sablon"
        assert _heuristic_classify(_event(1050, 420, inrush=2.2)).label == "Motor Drum Pengering Laundry"

    def test_confidence_depends_on_distance(self):
        exact = _heuristic_classify(_proto_event("Setrika Pemanas Uap"))
        off = _heuristic_classify(_proto_event("Setrika Pemanas Uap", scale=1.25))
        assert exact.label == off.label
        assert 0.0 < off.confidence < exact.confidence <= 1.0
        assert exact.confidence != 0.70

    def test_classifier_without_model_falls_back(self, tmp_path):
        clf = NILMClassifier(model_path=str(tmp_path / "missing.pkl"))
        assert not clf.uses_model
        r = clf.predict(_proto_event("Motor Jahit Induksi"))
        assert r.source == "heuristic" and r.appliance_class == 1


def _train_bundle(feature_names=None, fmt=MODEL_FORMAT_VERSION):
    lgbm = pytest.importorskip("lightgbm")
    rng = np.random.default_rng(0)
    X, y = [], []
    for prof in APPLIANCE_PROFILES:
        for _ in range(30):
            ev = _proto_event(prof.label, on=bool(rng.integers(0, 2)), scale=rng.uniform(0.9, 1.1))
            X.append(extract_features(ev))
            y.append(prof.appliance_class)
    model = lgbm.LGBMClassifier(n_estimators=30, num_leaves=7, min_child_samples=3, verbose=-1, random_state=0)
    model.fit(np.array(X), np.array(y))
    return {
        "format_version": fmt,
        "model": model,
        "feature_names": list(feature_names or FEATURE_NAMES),
        "label_map": {c: APPLIANCE_LABELS[c] for c in range(1, 6)},
        "data_source": "synthetic",
    }


class TestModelBundle:
    def test_valid_bundle_is_used(self, tmp_path):
        joblib = pytest.importorskip("joblib")
        path = tmp_path / "m.pkl"
        joblib.dump(_train_bundle(), path)
        clf = NILMClassifier(model_path=str(path))
        assert clf.uses_model, clf.fallback_reason
        r = clf.predict(_proto_event("Kompresor Udara Sablon"))
        assert r.source == "lgbm" and r.label == "Kompresor Udara Sablon"
        assert 0.0 <= r.confidence <= 1.0
        assert clf.model_info["data_source"] == "synthetic"

    def test_feature_mismatch_falls_back_to_heuristic(self, tmp_path):
        joblib = pytest.importorskip("joblib")
        path = tmp_path / "m.pkl"
        joblib.dump(_train_bundle(feature_names=["a", "b", "c", "d", "e", "f"]), path)
        clf = NILMClassifier(model_path=str(path))
        assert not clf.uses_model
        assert "feature_names" in clf.fallback_reason
        assert clf.predict(_proto_event("Motor Jahit Induksi")).source == "heuristic"

    def test_legacy_raw_model_rejected(self, tmp_path):
        joblib = pytest.importorskip("joblib")
        path = tmp_path / "m.pkl"
        joblib.dump(_train_bundle()["model"], path)
        clf = NILMClassifier(model_path=str(path))
        assert not clf.uses_model

    def test_corrupt_file_rejected(self, tmp_path):
        path = tmp_path / "m.pkl"
        path.write_bytes(b"bukan model")
        assert not NILMClassifier(model_path=str(path)).uses_model


# ── Ground truth smart plug & pelabelan ──────────────────────────────────────
def _plug_csv(tmp_path, with_status=True) -> Path:
    rows = []
    # Setrika ON 10:00:10–10:01:00, Jahit ON 10:00:30–10:02:00 (tumpang-tindih)
    for sec in range(0, 180, 10):
        ts = T0 + timedelta(seconds=sec)
        s_on = 10 <= sec < 60
        j_on = 30 <= sec < 120
        rows.append((ts, "Setrika Pemanas Uap", 1200.0 if s_on else 0.0, "ON" if s_on else "OFF"))
        rows.append((ts, "Motor Jahit Induksi", 300.0 if j_on else 0.0, "ON" if j_on else "OFF"))
    df = pd.DataFrame(rows, columns=["timestamp", "appliance_label", "p_active", "status"])
    df["timestamp"] = df["timestamp"].map(lambda t: t.strftime("%Y-%m-%dT%H:%M:%S"))
    if not with_status:
        df = df.drop(columns=["status"])
    path = tmp_path / "plugs.csv"
    df.to_csv(path, index=False)
    return path


class TestGroundTruth:
    @pytest.mark.parametrize("with_status", [True, False])
    def test_transitions(self, tmp_path, with_status):
        trs = extract_plug_transitions(load_plug_csv(str(_plug_csv(tmp_path, with_status))))
        kinds = [(t.appliance_label, t.event_type) for t in trs]
        assert kinds == [
            ("Setrika Pemanas Uap", "ON"),
            ("Motor Jahit Induksi", "ON"),
            ("Setrika Pemanas Uap", "OFF"),
            ("Motor Jahit Induksi", "OFF"),
        ]
        assert trs[0].step_w == pytest.approx(1200)

    def test_events_labelled_from_plugs_not_rules(self, tmp_path):
        trs = extract_plug_transitions(load_plug_csv(str(_plug_csv(tmp_path))))
        events = [
            _event(1190, 40, t=11),            # setrika ON (dalam toleransi)
            _event(310, 300, inrush=3, t=31),  # jahit ON
            _event(-1210, -40, t=61),          # setrika OFF
            _event(80, 10, t=90),              # beban tanpa plug
            _event(-295, -290, t=200),         # terlalu jauh dari transisi jahit OFF
        ]
        labels = label_events(events, trs, tolerance_s=5)
        assert labels == [
            "Setrika Pemanas Uap",
            "Motor Jahit Induksi",
            "Setrika Pemanas Uap",
            BASELOAD_LABEL,
            BASELOAD_LABEL,
        ]

    def test_each_transition_used_once(self, tmp_path):
        trs = extract_plug_transitions(load_plug_csv(str(_plug_csv(tmp_path))))
        events = [_event(1200, 40, t=10), _event(1200, 40, t=12)]
        assigned = match_events_to_transitions(events, trs, tolerance_s=5)
        assert sum(a is not None for a in assigned) == 1

    def test_plug_energy(self, tmp_path):
        e = plug_hourly_energy_kwh(load_plug_csv(str(_plug_csv(tmp_path))))
        assert e[(T0.date(), 10, "Setrika Pemanas Uap")] == pytest.approx(1200 * 50 / 3.6e6)
        assert e[(T0.date(), 10, "Motor Jahit Induksi")] == pytest.approx(300 * 90 / 3.6e6)


# ── Generator sintetis ───────────────────────────────────────────────────────
class TestSyntheticGenerator:
    def test_day_outputs_panel_and_plugs(self):
        gen = _load_script("generate_synthetic_data")
        rng = np.random.default_rng(0)
        profiles = gen.site_profiles(42, 0.2)
        panel, plugs = gen.generate_day(datetime(2026, 10, 5), rng, 10, profiles)
        assert list(panel.columns) == ["timestamp", "v_rms", "i_rms", "p_active", "q_reactive", "frequency"]
        assert len(panel) == 86_400
        assert list(plugs.columns) == ["timestamp", "appliance_label", "p_active", "status"]
        assert set(plugs["appliance_label"]) == {p.label for p in APPLIANCE_PROFILES}
        assert set(plugs["status"]) == {"ON", "OFF"}
        # Panel ≥ jumlah smart plug (ada baseload & beban tanpa plug)
        plug_kwh = sum(plug_hourly_energy_kwh(load_plug_from_df(plugs)).values())
        panel_kwh = panel["p_active"].sum() / 3.6e6
        assert panel_kwh > plug_kwh > 0

    def test_site_jitter_moves_profiles(self):
        gen = _load_script("generate_synthetic_data")
        jittered = gen.site_profiles(42, 0.2)
        assert any(a.power_w != b.power_w for a, b in zip(jittered, APPLIANCE_PROFILES))
        assert gen.site_profiles(42, 0.0) == list(APPLIANCE_PROFILES)


def load_plug_from_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out["is_on"] = out["status"] == "ON"
    return out.sort_values(["appliance_label", "timestamp"]).reset_index(drop=True)


class TestEvaluateMetric:
    def test_estimated_accuracy(self):
        ev = _load_script("evaluate_nilm")
        assert ev.estimated_accuracy([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
        assert ev.estimated_accuracy([0, 0], [1, 1]) == pytest.approx(0.5)
        assert ev.estimated_accuracy([2, 2], [1, 1]) == pytest.approx(0.5)
        assert ev.estimated_accuracy([1], [0]) is None
