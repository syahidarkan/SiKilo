"""
Generator data sintetis 30 hari untuk pengujian pipeline NOTA LISTRIK.
Mensimulasikan pembacaan sensor ESP32 pada frekuensi 1 Hz selama 1 bulan.

Usage:
    python scripts/generate_synthetic_data.py --days 30 --output data/synthetic_30d.csv
"""
import argparse
import csv
import math
import random
import numpy as np
from datetime import datetime, timedelta, date

MACHINES = [
    {"label": "Motor Jahit Induksi",        "class": 1, "power_w": 320, "q_factor": 0.45, "inrush": 2.1},
    {"label": "Kompresor Sablon",           "class": 2, "power_w": 1500, "q_factor": 0.30, "inrush": 2.8},
    {"label": "Setrika Pemanas Uap",        "class": 3, "power_w": 1600, "q_factor": 0.05, "inrush": 1.1},
    {"label": "Drum Pengering Laundry",     "class": 4, "power_w": 1200, "q_factor": 0.35, "inrush": 2.0},
    {"label": "Freezer Kelontong",          "class": 5, "power_w": 450,  "q_factor": 0.40, "inrush": 2.5},
]

BASELOAD_W = 300.0
V_NOMINAL = 220.0
FREQ_NOMINAL = 50.0
NOISE_SCALE = 0.005


def _machine_schedule(machine_class: int, day_of_week: int) -> list[tuple[int, int]]:
    """Kembalikan list (start_hour, end_hour) jadwal mesin berdasarkan tipe."""
    schedule = {
        1: [(8, 12), (13, 17)] if day_of_week < 6 else [(8, 12)],  # Motor jahit
        2: [(9, 12), (13, 15)],  # Kompresor sablon
        3: [(7, 9), (12, 14), (15, 17)],  # Setrika uap: beban puncak siang
        4: [(6, 8), (10, 12), (14, 16)],  # Drum pengering: 3 batch
        5: [(0, 24)],  # Freezer: selalu ON
    }
    return schedule.get(machine_class, [])


def generate_day(start_dt: datetime, v_nominal: float = V_NOMINAL) -> list[dict]:
    rows = []
    machine_states = {m["class"]: False for m in MACHINES}

    for second in range(86400):
        current_dt = start_dt + timedelta(seconds=second)
        hour = current_dt.hour

        p_total = BASELOAD_W + random.gauss(0, 5)
        q_total = 50.0

        for machine in MACHINES:
            cls = machine["class"]
            is_on = any(sh <= hour < eh for sh, eh in _machine_schedule(cls, current_dt.weekday()))

            # Add stochastic ON/OFF for realistic behavior
            if is_on and random.random() < 0.002:  # 0.2% chance to briefly toggle
                is_on = not is_on

            if is_on:
                p_total += machine["power_w"] * (1 + random.gauss(0, 0.02))
                q_total += machine["power_w"] * machine["q_factor"] * (1 + random.gauss(0, 0.03))

            # Inrush spike on first ON tick
            if is_on and not machine_states[cls]:
                p_total += machine["power_w"] * (machine["inrush"] - 1) * max(0, 1 - (second % 3) / 3.0)

            machine_states[cls] = is_on

        v_rms = v_nominal * (1 + random.gauss(0, NOISE_SCALE))
        p_total = max(p_total, BASELOAD_W)
        i_rms = p_total / max(v_rms, 1.0)
        freq = FREQ_NOMINAL + random.gauss(0, 0.015)

        rows.append({
            "device_id": "ESP32-SKH-042",
            "timestamp": current_dt.isoformat() + "Z",
            "v_rms": round(v_rms, 2),
            "i_rms": round(i_rms, 3),
            "p_active": round(p_total, 2),
            "q_reactive": round(q_total, 2),
            "frequency": round(freq, 3),
        })

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output", type=str, default="data/synthetic_30d.csv")
    parser.add_argument("--start", type=str, default="2026-10-01")
    args = parser.parse_args()

    import os
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    start_date = datetime.fromisoformat(args.start)
    fieldnames = ["device_id", "timestamp", "v_rms", "i_rms", "p_active", "q_reactive", "frequency"]

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for day_offset in range(args.days):
            day_start = start_date + timedelta(days=day_offset)
            print(f"Generating day {day_offset + 1}/{args.days}: {day_start.date()}")
            rows = generate_day(day_start)
            writer.writerows(rows)

    print(f"Done. {args.days * 86400:,} rows written to {args.output}")


if __name__ == "__main__":
    main()
