"""
Script pelatihan model LightGBM untuk NILM classifier.
Menggunakan data sintetis atau data ground-truth dari smart plug.

Usage:
    python scripts/train_nilm.py --data data/synthetic_30d.csv --model models/nilm_lgbm.pkl
"""
import argparse
import os
import csv
import numpy as np
import joblib
from datetime import datetime
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from app.nilm.event_detector import EventDetector, TelemetrySample
from app.nilm.feature_extractor import extract_features

LABEL_RULES = [
    (0, 50, None),           # class 0: baseload
    (1, 250, 400),           # class 1: motor jahit
    (2, 1200, 1800),         # class 2: kompresor sablon
    (3, 1000, 2200),         # class 3: setrika uap
    (4, 800, 2000),          # class 4: drum pengering
    (5, 300, 600),           # class 5: freezer
]


def _auto_label(delta_p: float, delta_q: float) -> int:
    abs_dp = abs(delta_p)
    ratio = abs(delta_q) / max(abs_dp, 1.0)

    if abs_dp < 50:
        return 0
    elif 250 <= abs_dp <= 400 and ratio > 0.4:
        return 1
    elif 1200 <= abs_dp <= 1800:
        return 2
    elif 1000 <= abs_dp <= 2200 and ratio < 0.15:
        return 3
    elif 800 <= abs_dp <= 2000:
        return 4
    elif 300 <= abs_dp <= 600:
        return 5
    return 0


def extract_events_from_csv(csv_path: str) -> tuple[np.ndarray, np.ndarray]:
    detector = EventDetector()
    X, y = [], []

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sample = TelemetrySample(
                timestamp=datetime.fromisoformat(row["timestamp"].rstrip("Z")),
                p_active=float(row["p_active"]),
                q_reactive=float(row["q_reactive"]),
                v_rms=float(row["v_rms"]),
                i_rms=float(row["i_rms"]),
                frequency=float(row["frequency"]),
            )
            event = detector.push(sample)
            if event is not None:
                features = extract_features(event)
                label = _auto_label(event.delta_p, event.delta_q)
                X.append(features)
                y.append(label)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="data/synthetic_30d.csv")
    parser.add_argument("--model", type=str, default="models/nilm_lgbm.pkl")
    parser.add_argument("--test-size", type=float, default=0.2)
    args = parser.parse_args()

    print(f"Extracting events from {args.data}...")
    X, y = extract_events_from_csv(args.data)
    print(f"Extracted {len(X)} events, {len(np.unique(y))} unique classes.")

    if len(X) < 10:
        print("ERROR: Tidak cukup data untuk training. Jalankan generate_synthetic_data.py terlebih dahulu.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=args.test_size, stratify=y, random_state=42)

    model = LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=8,
        num_leaves=63,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    print("Training LightGBM classifier...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))

    os.makedirs(os.path.dirname(args.model) if os.path.dirname(args.model) else ".", exist_ok=True)
    joblib.dump(model, args.model)
    print(f"Model saved to {args.model}")


if __name__ == "__main__":
    main()
