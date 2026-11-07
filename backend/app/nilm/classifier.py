"""
Classifier NILM: memetakan TransientEvent → mesin.

- Jalur utama: model LightGBM yang dilatih dari event panel yang diberi label
  dengan transisi ON/OFF smart plug (scripts/train_nilm.py). Model disimpan
  sebagai bundle {model, feature_names, label_map, format_version, ...}.
- Fallback: heuristik berbasis jarak ke prototipe (app/nilm/profiles.py)
  memakai ΔP, Q/P, dan inrush. Confidence dihitung dari jarak tersebut, bukan
  angka tetap.

Bila file model tidak ada, rusak, formatnya lama, atau daftar fiturnya tidak
cocok dengan FEATURE_NAMES saat ini, classifier memakai heuristik.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from app.core.config import settings
from app.nilm.event_detector import TransientEvent
from app.nilm.feature_extractor import FEATURE_NAMES, extract_features, q_p_ratio
from app.nilm.profiles import APPLIANCE_PROFILES, BASELOAD_LABEL

logger = logging.getLogger(__name__)

MODEL_FORMAT_VERSION = 2

APPLIANCE_LABELS: dict[int, str] = {0: BASELOAD_LABEL}
APPLIANCE_LABELS.update({p.appliance_class: p.label for p in APPLIANCE_PROFILES})

# Jarak (dalam satuan "toleransi") di atas ini dianggap bukan mesin yang dikenal.
_UNKNOWN_DISTANCE = 3.0
_W_UNKNOWN = math.exp(-0.5 * _UNKNOWN_DISTANCE ** 2)


@dataclass
class ClassificationResult:
    appliance_class: int
    label: str
    confidence: float
    source: str  # "lgbm" | "heuristic"


def prototype_distances(event: TransientEvent) -> dict[int, float]:
    """Jarak ternormalisasi event ke setiap prototipe mesin (0 = persis cocok)."""
    dp = max(abs(event.delta_p), 1.0)
    ratio = q_p_ratio(event)
    out: dict[int, float] = {}
    for prof in APPLIANCE_PROFILES:
        d_p = math.log(dp / prof.power_w) / math.log(1.0 + prof.power_tol)
        q_tol = max(prof.q_ratio_tol, 0.15 * prof.q_ratio)
        d_q = (ratio - prof.q_ratio) / q_tol
        d2 = d_p ** 2 + d_q ** 2
        if event.event_type == "ON":
            inr = max(event.inrush_peak_ratio, 1.0)
            d_i = math.log(inr / prof.inrush_ratio) / math.log(1.0 + prof.inrush_tol)
            d2 += d_i ** 2
        out[prof.appliance_class] = math.sqrt(d2)
    return out


def _heuristic_classify(event: TransientEvent) -> ClassificationResult:
    """
    Klasifikasi berbasis jarak ke prototipe. Confidence =
    w_terbaik / (Σw + w_unknown), w = exp(−d²/2). Event kecil (< threshold)
    atau yang jauh dari semua prototipe → "Baseload / Background".
    """
    if abs(event.delta_p) < settings.nilm_event_threshold_w:
        return ClassificationResult(0, APPLIANCE_LABELS[0], 1.0 - _W_UNKNOWN, "heuristic")

    dists = prototype_distances(event)
    weights = {c: math.exp(-0.5 * d ** 2) for c, d in dists.items()}
    total = sum(weights.values()) + _W_UNKNOWN
    best = min(dists, key=dists.get)
    if dists[best] > _UNKNOWN_DISTANCE:
        return ClassificationResult(0, APPLIANCE_LABELS[0], float(_W_UNKNOWN / total), "heuristic")
    return ClassificationResult(
        appliance_class=best,
        label=APPLIANCE_LABELS[best],
        confidence=float(weights[best] / total),
        source="heuristic",
    )


def _validate_bundle(bundle: Any) -> Optional[str]:
    """Kembalikan alasan penolakan, atau None bila bundle valid."""
    if not isinstance(bundle, dict):
        return "format lama (bukan bundle dict)"
    if bundle.get("format_version") != MODEL_FORMAT_VERSION:
        return f"format_version {bundle.get('format_version')} != {MODEL_FORMAT_VERSION}"
    if list(bundle.get("feature_names", [])) != FEATURE_NAMES:
        return "feature_names tidak cocok dengan FEATURE_NAMES saat ini"
    model = bundle.get("model")
    if model is None or not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
        return "objek model tidak valid"
    label_map = bundle.get("label_map")
    if not isinstance(label_map, dict) or not all(int(c) in label_map for c in model.classes_):
        return "label_map tidak mencakup semua kelas model"
    return None


class NILMClassifier:
    def __init__(self, model_path: str | None = None, use_model: bool = True) -> None:
        self.model_path = model_path or settings.nilm_model_path
        self._model: Optional[Any] = None
        self._label_map: dict[int, str] = dict(APPLIANCE_LABELS)
        self.model_info: dict[str, Any] = {}
        self.fallback_reason: Optional[str] = None
        if use_model:
            self._load_model()
        else:
            self.fallback_reason = "model dinonaktifkan"

    @property
    def uses_model(self) -> bool:
        return self._model is not None

    def _load_model(self) -> None:
        path = self.model_path
        if not os.path.exists(path):
            self.fallback_reason = f"model tidak ditemukan: {path}"
            return
        try:
            import joblib

            bundle = joblib.load(path)
        except Exception as exc:  # noqa: BLE001
            self.fallback_reason = f"gagal memuat model: {exc}"
            logger.warning("NILM: %s → heuristik", self.fallback_reason)
            return
        reason = _validate_bundle(bundle)
        if reason:
            self.fallback_reason = reason
            logger.warning("NILM: model %s ditolak (%s) → heuristik", path, reason)
            return
        self._model = bundle["model"]
        self._label_map = {int(k): str(v) for k, v in bundle["label_map"].items()}
        self.model_info = {k: v for k, v in bundle.items() if k != "model"}

    def label_for(self, appliance_class: int) -> str:
        return self._label_map.get(appliance_class, APPLIANCE_LABELS.get(appliance_class, "Tidak dikenal"))

    def predict(self, event: TransientEvent) -> ClassificationResult:
        if self._model is not None:
            try:
                features = extract_features(event).reshape(1, -1)
                proba = self._model.predict_proba(features)[0]
                idx = int(np.argmax(proba))
                cls = int(self._model.classes_[idx])
                return ClassificationResult(
                    appliance_class=cls,
                    label=self.label_for(cls),
                    confidence=float(proba[idx]),
                    source="lgbm",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("NILM: prediksi model gagal (%s) → heuristik", exc)
        return _heuristic_classify(event)
