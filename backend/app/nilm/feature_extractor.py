"""
Ekstraksi fitur dari satu TransientEvent.

Fitur sengaja hanya berupa tanda tangan listrik (ΔP, ΔQ, Q/P, inrush, arah,
lama transien). Jam/hari TIDAK dipakai agar model tidak menghafal jadwal
data latih (terutama jadwal sintetis) alih-alih mengenali mesin.

Urutan FEATURE_NAMES disimpan bersama model (metadata); bila berubah, model
lama otomatis ditolak dan classifier jatuh ke heuristik.
"""
import numpy as np

from app.nilm.event_detector import TransientEvent

FEATURE_NAMES: list[str] = [
    "abs_delta_p",
    "abs_delta_q",
    "ratio_q_p",
    "inrush_peak_ratio",
    "is_on",
    "transient_duration_s",
]


def q_p_ratio(event: TransientEvent) -> float:
    """|ΔQ| / |ΔP| dengan pengaman pembagian nol."""
    return abs(event.delta_q) / max(abs(event.delta_p), 1.0)


def extract_features(event: TransientEvent) -> np.ndarray:
    """Vektor fitur (len(FEATURE_NAMES),) float32, urutan sesuai FEATURE_NAMES."""
    return np.array(
        [
            abs(event.delta_p),
            abs(event.delta_q),
            q_p_ratio(event),
            event.inrush_peak_ratio,
            1.0 if event.event_type == "ON" else 0.0,
            getattr(event, "transient_duration_s", 0.0),
        ],
        dtype=np.float32,
    )
