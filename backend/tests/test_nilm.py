import pytest
from datetime import datetime
from app.nilm.event_detector import EventDetector, TelemetrySample, TransientEvent
from app.nilm.feature_extractor import extract_features, FEATURE_NAMES
from app.nilm.classifier import NILMClassifier, _heuristic_classify


def _make_sample(p: float, q: float = 100.0, v: float = 220.0, ts: datetime | None = None) -> TelemetrySample:
    return TelemetrySample(
        timestamp=ts or datetime(2026, 11, 7, 10, 0, 0),
        p_active=p,
        q_reactive=q,
        v_rms=v,
        i_rms=p / max(v, 1.0),
        frequency=50.0,
    )


class TestEventDetector:
    def test_no_event_below_threshold(self):
        detector = EventDetector(threshold_w=50.0)
        for p in [300.0, 302.0, 301.5, 299.0]:
            event = detector.push(_make_sample(p))
        assert event is None

    def test_detects_large_step_on(self):
        detector = EventDetector(threshold_w=50.0)
        # Warm up baseline
        for _ in range(5):
            detector.push(_make_sample(300.0))
        # Step up
        event = None
        for _ in range(4):
            event = detector.push(_make_sample(1600.0))
        assert event is not None
        assert event.event_type == "ON"
        assert event.delta_p > 50.0

    def test_detects_step_off(self):
        detector = EventDetector(threshold_w=50.0)
        for _ in range(10):
            detector.push(_make_sample(1600.0))
        event = None
        for _ in range(4):
            event = detector.push(_make_sample(300.0))
        assert event is not None
        assert event.event_type == "OFF"

    def test_cooldown_suppresses_duplicate_events(self):
        detector = EventDetector(threshold_w=50.0)
        for _ in range(5):
            detector.push(_make_sample(300.0))
        events = []
        for _ in range(10):
            e = detector.push(_make_sample(1600.0))
            if e is not None:
                events.append(e)
        # Hanya 1 event yang boleh lolos (cooldown aktif)
        assert len(events) <= 2


class TestFeatureExtractor:
    def _make_event(self, dp: float = 1200.0, dq: float = 100.0) -> TransientEvent:
        return TransientEvent(
            timestamp=datetime(2026, 11, 7, 11, 30, 0),
            delta_p=dp,
            delta_q=dq,
            p_before=300.0,
            q_before=50.0,
            p_after=300.0 + dp,
            q_after=50.0 + dq,
            v_rms=220.0,
            i_rms=(300.0 + dp) / 220.0,
            inrush_peak_ratio=1.8,
            event_type="ON",
        )

    def test_feature_vector_shape(self):
        event = self._make_event()
        features = extract_features(event)
        assert features.shape == (7,)
        assert len(FEATURE_NAMES) == 7

    def test_ratio_q_p_correct(self):
        event = self._make_event(dp=1000.0, dq=100.0)
        features = extract_features(event)
        assert abs(features[2] - 0.1) < 1e-5  # ratio_q_p = 100/1000

    def test_hour_of_day_range(self):
        event = self._make_event()
        features = extract_features(event)
        assert 0.0 <= features[5] < 24.0


class TestClassifier:
    def _make_event_for_class(self, cls: int) -> TransientEvent:
        params = {
            0: (30.0, 5.0, 1.0),
            1: (320.0, 150.0, 1.5),   # Motor jahit
            2: (1500.0, 400.0, 2.8),  # Kompresor sablon: inrush tinggi
            3: (1600.0, 20.0, 1.1),   # Setrika uap: Q rendah
            4: (1200.0, 350.0, 2.0),  # Drum pengering
            5: (450.0, 180.0, 2.5),   # Freezer
        }
        dp, dq, inrush = params[cls]
        return TransientEvent(
            timestamp=datetime(2026, 11, 7, 10, 0, 0),
            delta_p=dp, delta_q=dq,
            p_before=300.0, q_before=50.0,
            p_after=300.0 + dp, q_after=50.0 + dq,
            v_rms=220.0, i_rms=(300.0 + dp) / 220.0,
            inrush_peak_ratio=inrush,
            event_type="ON",
        )

    def test_heuristic_baseload(self):
        event = self._make_event_for_class(0)
        result = _heuristic_classify(event)
        assert result.appliance_class == 0

    def test_heuristic_setrika_uap(self):
        event = self._make_event_for_class(3)
        result = _heuristic_classify(event)
        assert result.appliance_class == 3  # purely resistive

    def test_classifier_returns_valid_class(self):
        classifier = NILMClassifier()
        for cls in range(6):
            event = self._make_event_for_class(cls)
            result = classifier.predict(event)
            assert 0 <= result.appliance_class <= 5
            assert 0.0 <= result.confidence <= 1.0
            assert result.source in ("lgbm", "heuristic")
