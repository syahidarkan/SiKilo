"""
Latih classifier NILM (LightGBM) dari data panel + smart plug.

Label TIDAK berasal dari aturan/heuristik: setiap event yang dideteksi pada
data panel diberi label mesin yang transisi ON/OFF smart plug-nya paling dekat
(|Δt| ≤ toleransi, arah sama, ΔP mirip). Event tanpa pasangan → "Baseload /
Background" (beban kecil tanpa plug, noise).

Model disimpan sebagai bundle joblib berisi metadata (feature_names, label_map,
format_version, sumber data, metrik holdout) sehingga classifier bisa menolak
model yang tidak cocok dan jatuh ke heuristik.

Usage:
    python scripts/train_nilm.py --panel data/synthetic/train_panel.csv \
        --plugs data/synthetic/train_plugs.csv --data-source synthetic
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.nilm.classifier import APPLIANCE_LABELS, MODEL_FORMAT_VERSION  # noqa: E402
from app.nilm.feature_extractor import FEATURE_NAMES, extract_features  # noqa: E402
from app.nilm.ground_truth import (  # noqa: E402
    detect_events,
    extract_plug_transitions,
    iso_now,
    iter_panel_samples,
    label_events,
    load_panel_csv,
    load_plug_csv,
)


def build_label_map(labels: set[str]) -> dict[int, str]:
    """Pakai id dari APPLIANCE_LABELS bila namanya dikenal; label baru diberi id berikutnya."""
    known = {v: k for k, v in APPLIANCE_LABELS.items()}
    label_map: dict[int, str] = {}
    next_id = max(APPLIANCE_LABELS) + 1
    for lab in sorted(labels):
        if lab in known:
            label_map[known[lab]] = lab
        else:
            label_map[next_id] = lab
            next_id += 1
    return label_map


def build_dataset(panel_path: str, plug_path: str, tolerance_s: float):
    panel = load_panel_csv(panel_path)
    plugs = load_plug_csv(plug_path)
    events = detect_events(iter_panel_samples(panel))
    transitions = extract_plug_transitions(plugs)
    labels = label_events(events, transitions, tolerance_s)
    return events, labels, transitions


def main() -> None:
    from lightgbm import LGBMClassifier
    from sklearn.metrics import classification_report
    import joblib
    import lightgbm
    import sklearn

    parser = argparse.ArgumentParser(description="Latih classifier NILM WASKITA")
    parser.add_argument("--panel", default="data/synthetic/train_panel.csv")
    parser.add_argument("--plugs", default="data/synthetic/train_plugs.csv")
    parser.add_argument("--model", default=settings.nilm_model_path)
    parser.add_argument("--tolerance-s", type=float, default=settings.nilm_label_tolerance_s)
    parser.add_argument("--data-source", choices=["synthetic", "field"], default="synthetic")
    parser.add_argument("--holdout-frac", type=float, default=0.2, help="porsi event terakhir (urut waktu) untuk validasi")
    args = parser.parse_args()

    print(f"Mendeteksi event dari {args.panel} …")
    events, labels, transitions = build_dataset(args.panel, args.plugs, args.tolerance_s)
    n_matched = sum(1 for lab in labels if lab != APPLIANCE_LABELS[0])
    print(f"{len(events)} event terdeteksi, {n_matched} cocok dengan {len(transitions)} transisi smart plug.")
    print("Sebaran label:", dict(Counter(labels)))

    label_map = build_label_map(set(labels))
    inv = {v: k for k, v in label_map.items()}
    if len(events) < 20 or len(label_map) < 2:
        print("ERROR: data terlalu sedikit untuk melatih (butuh ≥20 event dan ≥2 kelas).")
        sys.exit(1)

    X = np.vstack([extract_features(e) for e in events]).astype(np.float32)
    y = np.array([inv[lab] for lab in labels], dtype=np.int32)

    def make_model():
        return LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )

    # Validasi holdout berdasarkan waktu (event terakhir), bukan acak, agar tidak bocor.
    holdout = {}
    n_hold = int(len(X) * args.holdout_frac)
    if n_hold >= 10 and len(np.unique(y[:-n_hold])) >= 2:
        m = make_model().fit(X[:-n_hold], y[:-n_hold])
        y_pred = m.predict(X[-n_hold:])
        present = sorted(set(y[-n_hold:].tolist()) | set(y_pred.tolist()))
        print("\nValidasi holdout (urut waktu):")
        print(classification_report(
            y[-n_hold:], y_pred, labels=present, target_names=[label_map[c] for c in present], zero_division=0
        ))
        holdout = {"n_events": int(n_hold), "accuracy": float(np.mean(y_pred == y[-n_hold:]))}

    model = make_model().fit(X, y)
    bundle = {
        "format_version": MODEL_FORMAT_VERSION,
        "model": model,
        "feature_names": list(FEATURE_NAMES),
        "label_map": label_map,
        "data_source": args.data_source,
        "trained_at": iso_now(),
        "n_events": int(len(X)),
        "class_counts": {label_map[int(c)]: int(n) for c, n in zip(*np.unique(y, return_counts=True))},
        "label_tolerance_s": args.tolerance_s,
        "holdout": holdout,
        "versions": {"lightgbm": lightgbm.__version__, "sklearn": sklearn.__version__, "numpy": np.__version__},
    }
    os.makedirs(os.path.dirname(args.model) or ".", exist_ok=True)
    joblib.dump(bundle, args.model)
    print(f"Model disimpan ke {args.model}")


if __name__ == "__main__":
    main()
