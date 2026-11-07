import numpy as np
from app.nilm.event_detector import TransientEvent


FEATURE_NAMES = [
    "delta_p",
    "delta_q",
    "ratio_q_p",
    "v_rms",
    "inrush_peak_ratio",
    "hour_of_day",
    "day_of_week",
]


def extract_features(event: TransientEvent) -> np.ndarray:
    """
    Ekstraksi vektor fitur 7 dimensi dari satu transient event.
    Urutan fitur harus konsisten dengan urutan saat training model NILM.
    """
    delta_p = event.delta_p
    delta_q = event.delta_q

    # Hindari pembagian nol: gunakan nilai absolut delta_p
    abs_dp = abs(delta_p) if abs(delta_p) > 1.0 else 1.0
    ratio_q_p = delta_q / abs_dp

    hour_of_day = event.timestamp.hour + event.timestamp.minute / 60.0
    day_of_week = float(event.timestamp.weekday())

    features = np.array(
        [
            delta_p,
            delta_q,
            ratio_q_p,
            event.v_rms,
            event.inrush_peak_ratio,
            hour_of_day,
            day_of_week,
        ],
        dtype=np.float32,
    )
    return features
