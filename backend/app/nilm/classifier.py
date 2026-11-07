import os
import numpy as np
import joblib
from dataclasses import dataclass
from typing import Optional
from app.nilm.event_detector import TransientEvent
from app.nilm.feature_extractor import extract_features
from app.core.config import settings

APPLIANCE_LABELS: dict[int, str] = {
    0: "Baseload / Background",
    1: "Motor Jahit Induksi",
    2: "Kompresor Udara Sablon",
    3: "Setrika Pemanas Uap",
    4: "Motor Drum Pengering Laundry",
    5: "Kompresor Pendingin Freezer",
}


@dataclass
class ClassificationResult:
    appliance_class: int
    label: str
    confidence: float
    source: str  # "lgbm" | "heuristic"


def _heuristic_classify(event: TransientEvent) -> ClassificationResult:
    """
    Rule-based fallback jika model LightGBM belum tersedia.
    Berdasarkan range ΔP dan karakteristik ΔQ dari masing-masing perangkat.
    """
    dp = abs(event.delta_p)
    dq = abs(event.delta_q)
    ratio = dq / max(dp, 1.0)

    if dp < 50:
        cls = 0
    elif 250 <= dp <= 400 and ratio > 0.4:
        cls = 1  # Motor jahit: inrush dengan Q tinggi
    elif 1200 <= dp <= 1800 and event.inrush_peak_ratio > 1.5:
        cls = 2  # Kompresor sablon: spike inrush tajam
    elif 1000 <= dp <= 2200 and ratio < 0.15:
        cls = 3  # Setrika uap: purely resistive, Q mendekati 0
    elif 800 <= dp <= 2000 and 0.15 <= ratio <= 0.5:
        cls = 4  # Drum pengering: motor besar
    elif 300 <= dp <= 600:
        cls = 5  # Freezer: siklus kompressor kecil
    else:
        cls = 0

    return ClassificationResult(
        appliance_class=cls,
        label=APPLIANCE_LABELS[cls],
        confidence=0.70,
        source="heuristic",
    )


class NILMClassifier:
    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._load_model()

    def _load_model(self) -> None:
        path = settings.nilm_model_path
        if os.path.exists(path):
            try:
                self._model = joblib.load(path)
            except Exception:
                self._model = None

    def predict(self, event: TransientEvent) -> ClassificationResult:
        features = extract_features(event).reshape(1, -1)

        if self._model is not None:
            try:
                proba = self._model.predict_proba(features)[0]  # type: ignore[union-attr]
                cls = int(np.argmax(proba))
                conf = float(proba[cls])
                return ClassificationResult(
                    appliance_class=cls,
                    label=APPLIANCE_LABELS.get(cls, "Unknown"),
                    confidence=conf,
                    source="lgbm",
                )
            except Exception:
                pass

        return _heuristic_classify(event)
