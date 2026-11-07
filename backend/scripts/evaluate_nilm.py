"""
Evaluasi NILM WASKITA terhadap ground truth smart plug.

Mengukur:
1. Klasifikasi event: akurasi, precision/recall/F1 per mesin. Label benar tiap
   event = mesin yang transisi smart plug-nya cocok (|Δt| ≤ toleransi);
   event tanpa pasangan = "Baseload / Background".
2. Recall deteksi: porsi transisi ON/OFF smart plug yang tertangkap detektor.
3. Akurasi energi per mesin (LoadDisaggregator, per jam) dengan metrik
   "estimated accuracy" Kolter & Johnson (2011):
       Acc = 1 − Σ_t |ê_t − e_t| / (2 Σ_t e_t)
   Overall memakai jumlah atas semua mesin ber-smart-plug.

Hasil ditulis sebagai JSON ke settings.nilm_metrics_path. Gunakan data UJI yang
berbeda dari data latih (mis. seed/tanggal lain, atau hari lapangan lain).

Usage:
    python scripts/evaluate_nilm.py --panel data/synthetic/test_panel.csv \
        --plugs data/synthetic/test_plugs.csv --data-source synthetic
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.nilm.classifier import NILMClassifier  # noqa: E402
from app.nilm.disaggregator import LoadDisaggregator  # noqa: E402
from app.nilm.event_detector import EventDetector  # noqa: E402
from app.nilm.ground_truth import (  # noqa: E402
    extract_plug_transitions,
    iso_now,
    iter_panel_samples,
    load_panel_csv,
    load_plug_csv,
    match_events_to_transitions,
    panel_hourly_energy_kwh,
    plug_hourly_energy_kwh,
)
from app.nilm.profiles import BASELOAD_LABEL  # noqa: E402

TARGET = 0.80


def estimated_accuracy(est: list[float], true: list[float]) -> float | None:
    """Kolter & Johnson: 1 − Σ|ê−e| / (2Σe). None bila energi sebenarnya nol."""
    e = np.asarray(true, dtype=float)
    ê = np.asarray(est, dtype=float)
    denom = 2.0 * e.sum()
    if denom <= 0:
        return None
    return float(1.0 - np.abs(ê - e).sum() / denom)


def _prf(y_true: list[str], y_pred: list[str], label: str) -> dict:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": tp + fn}


def run_mode(
    panel, transitions, plug_kwh, panel_kwh, classifier: NILMClassifier, tolerance_s: float, units_per_label: int = 0
) -> dict:
    disagg = LoadDisaggregator(
        classifier=classifier,
        detector=EventDetector(),
        max_instances_per_label=units_per_label if units_per_label > 0 else None,
    )
    events = []
    for s in iter_panel_samples(panel):
        upd = disagg.push(s)
        if upd.event is not None:
            events.append(upd.event)
    est_kwh: dict[tuple, float] = defaultdict(float)
    for h in disagg.flush_hourly_energy():
        est_kwh[(h.day, h.hour, h.appliance_label)] += h.kwh

    # ── klasifikasi event ──
    assigned = match_events_to_transitions(events, transitions, tolerance_s)
    y_true = [transitions[a].appliance_label if a is not None else BASELOAD_LABEL for a in assigned]
    y_pred = [classifier.predict(e).label for e in events]

    plug_labels = sorted({t.appliance_label for t in transitions} | {k[2] for k in plug_kwh})
    matched_by_label: dict[str, int] = defaultdict(int)
    total_by_label: dict[str, int] = defaultdict(int)
    for t in transitions:
        total_by_label[t.appliance_label] += 1
    for a in assigned:
        if a is not None:
            matched_by_label[transitions[a].appliance_label] += 1

    # ── energi per jam ──
    hours = sorted(panel_kwh)
    per_app: dict[str, dict] = {}
    all_est, all_true = [], []
    for lab in plug_labels:
        true = [plug_kwh.get((d, h, lab), 0.0) for d, h in hours]
        est = [est_kwh.get((d, h, lab), 0.0) for d, h in hours]
        all_est += est
        all_true += true
        acc = estimated_accuracy(est, true)
        ev = _prf(y_true, y_pred, lab)
        n_tr = total_by_label.get(lab, 0)
        per_app[lab] = {
            **ev,
            "detection_recall": round(matched_by_label.get(lab, 0) / n_tr, 4) if n_tr else None,
            "n_plug_transitions": n_tr,
            "energy_true_kwh": round(sum(true), 4),
            "energy_est_kwh": round(sum(est), 4),
            "energy_estimated_accuracy": None if acc is None else round(acc, 4),
            "meets_80pct_f1": ev["f1"] >= TARGET,
            "meets_80pct_energy": acc is not None and acc >= TARGET,
        }

    # Baseload: ground truth diturunkan = total panel − Σ smart plug (bukan pengukuran langsung).
    base_true = [max(panel_kwh[(d, h)] - sum(plug_kwh.get((d, h, lab), 0.0) for lab in plug_labels), 0.0) for d, h in hours]
    base_est = [est_kwh.get((d, h, BASELOAD_LABEL), 0.0) for d, h in hours]
    base_acc = estimated_accuracy(base_est, base_true)
    per_app[BASELOAD_LABEL] = {
        **_prf(y_true, y_pred, BASELOAD_LABEL),
        "ground_truth": "derived (total panel − Σ smart plug)",
        "energy_true_kwh": round(sum(base_true), 4),
        "energy_est_kwh": round(sum(base_est), 4),
        "energy_estimated_accuracy": None if base_acc is None else round(base_acc, 4),
    }

    acc_overall = estimated_accuracy(all_est, all_true)
    f1s = [per_app[lab]["f1"] for lab in plug_labels]
    total_est = sum(est_kwh.values())
    total_meas = sum(panel_kwh.values())
    overall = {
        "n_events": len(events),
        "n_plug_transitions": len(transitions),
        "event_accuracy": round(float(np.mean([t == p for t, p in zip(y_true, y_pred)])), 4) if events else None,
        "macro_f1_appliances": round(float(np.mean(f1s)), 4) if f1s else None,
        "detection_recall": round(sum(matched_by_label.values()) / len(transitions), 4) if transitions else None,
        "energy_estimated_accuracy": None if acc_overall is None else round(acc_overall, 4),
        "energy_conservation_error_pct": round(100 * abs(total_est - total_meas) / total_meas, 6) if total_meas else None,
        "n_appliances_meeting_80pct_f1": sum(1 for lab in plug_labels if per_app[lab]["meets_80pct_f1"]),
        "n_appliances_meeting_80pct_energy": sum(1 for lab in plug_labels if per_app[lab]["meets_80pct_energy"]),
        "n_appliances": len(plug_labels),
    }
    return {"per_appliance": per_app, "overall": overall}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluasi NILM WASKITA vs smart plug")
    parser.add_argument("--panel", default="data/synthetic/test_panel.csv")
    parser.add_argument("--plugs", default="data/synthetic/test_plugs.csv")
    parser.add_argument("--model", default=settings.nilm_model_path)
    parser.add_argument("--output", default=settings.nilm_metrics_path)
    parser.add_argument("--data-source", choices=["synthetic", "field"], default="synthetic")
    parser.add_argument("--tolerance-s", type=float, default=settings.nilm_label_tolerance_s)
    parser.add_argument(
        "--units-per-label", type=int, default=0,
        help="batas unit mesin per label (inventaris). 0 = tak dibatasi (sama dengan default API)",
    )
    parser.add_argument("--skip-heuristic", action="store_true", help="jangan hitung pembanding heuristik")
    args = parser.parse_args()

    panel = load_panel_csv(args.panel)
    plugs = load_plug_csv(args.plugs)
    transitions = extract_plug_transitions(plugs)
    plug_kwh = plug_hourly_energy_kwh(plugs)
    panel_kwh = panel_hourly_energy_kwh(panel)

    clf = NILMClassifier(model_path=args.model)
    print(f"Classifier: {'lgbm' if clf.uses_model else 'heuristic'}"
          + ("" if clf.uses_model else f" ({clf.fallback_reason})"))
    main_res = run_mode(panel, transitions, plug_kwh, panel_kwh, clf, args.tolerance_s, args.units_per_label)

    baselines = {}
    if clf.uses_model and not args.skip_heuristic:
        h = run_mode(panel, transitions, plug_kwh, panel_kwh, NILMClassifier(use_model=False), args.tolerance_s,
                     args.units_per_label)
        baselines["heuristic"] = {
            "overall": h["overall"],
            "per_appliance": {
                k: {"f1": v["f1"], "energy_estimated_accuracy": v["energy_estimated_accuracy"]}
                for k, v in h["per_appliance"].items()
            },
        }

    days = sorted({d for d, _ in panel_kwh})
    synthetic = args.data_source == "synthetic"
    report = {
        "data_source": args.data_source,
        "validation_status": (
            "belum divalidasi — data sintetis, bukan bukti akurasi di lapangan"
            if synthetic
            else "data lapangan — periksa jumlah hari & mesin sebelum mengklaim akurasi"
        ),
        "generated_at": iso_now(),
        "target": {"metric": "F1 & estimated accuracy energi per mesin", "threshold": TARGET},
        "inputs": {
            "panel": os.path.basename(args.panel),
            "plugs": os.path.basename(args.plugs),
            "n_samples": int(len(panel)),
            "n_days": len(days),
            "first_day": days[0].isoformat() if days else None,
            "last_day": days[-1].isoformat() if days else None,
            "label_tolerance_s": args.tolerance_s,
            "units_per_label": args.units_per_label,
        },
        "classifier": {
            "source": "lgbm" if clf.uses_model else "heuristic",
            "fallback_reason": clf.fallback_reason,
            "model_data_source": clf.model_info.get("data_source"),
            "model_trained_at": clf.model_info.get("trained_at"),
            "model_n_events": clf.model_info.get("n_events"),
        },
        "metric_definitions": {
            "energy_estimated_accuracy": "1 - sum_t|e_hat-e| / (2 sum_t e), per jam (Kolter & Johnson 2011)",
            "event_accuracy": "porsi event terdeteksi yang labelnya benar (termasuk kelas latar)",
            "detection_recall": "porsi transisi smart plug yang punya event panel pasangan",
        },
        "per_appliance": main_res["per_appliance"],
        "overall": main_res["overall"],
        "baselines": baselines,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    o = report["overall"]
    print(f"\nData: {args.data_source}, {len(days)} hari, {o['n_events']} event, {o['n_plug_transitions']} transisi plug")
    print(f"Akurasi event {o['event_accuracy']}, macro-F1 mesin {o['macro_f1_appliances']}, "
          f"recall deteksi {o['detection_recall']}, akurasi energi {o['energy_estimated_accuracy']}")
    for lab, m in report["per_appliance"].items():
        print(f"  {lab:32s} F1={m['f1']:.3f}  energi_acc={m['energy_estimated_accuracy']}  "
              f"({m['energy_est_kwh']:.2f} vs {m['energy_true_kwh']:.2f} kWh)")
    if baselines:
        hb = baselines["heuristic"]["overall"]
        print(f"Pembanding heuristik: akurasi event {hb['event_accuracy']}, macro-F1 {hb['macro_f1_appliances']}, "
              f"akurasi energi {hb['energy_estimated_accuracy']}")
    print(f"Metrik ditulis ke {args.output}")


if __name__ == "__main__":
    main()
