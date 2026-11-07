"""
Latih agen penjadwal WASKITA: behavior cloning → MaskablePPO (sb3-contrib).

Alur:
1. Skenario latih = hari acak sepanjang ``--train-year`` (default 2025) dengan
   variasi mesin, pola pesanan (OrderBook), kWp, dan baterai
   (``app/agent/scenarios.py``).
2. Behavior cloning dari demonstrasi (OR-Tools bila lebih murah, selain itu
   kebiasaan lama pemilik) — ``app/agent/behavior_cloning.py``.
3. Fine-tuning MaskablePPO selama ``--timesteps`` langkah (action mask menjaga
   jam kerja, deadline, blok minimum, cooldown).
4. Pemilihan model (BC saja vs BC+PPO) pada set validasi (tahun latih, seed lain).
5. Evaluasi akhir pada set uji ``--eval-year`` (default 2024, cuaca berbeda)
   vs OR-Tools, greedy, dan kebiasaan lama → ``settings.agent_eval_path``.

Model disimpan ke ``settings.rl_model_path`` (+ metadata ``settings.rl_meta_path``).
File .zip TIDAK untuk di-commit (lihat .gitignore).

Usage (dari folder backend):
    pip install -r requirements.txt -r requirements-rl.txt
    python scripts/train_agent.py --timesteps 30000
    python scripts/train_agent.py --timesteps 0 --bc-episodes 200   # BC saja
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.baseline import greedy_schedule, habit_idle_load_w, habit_schedule  # noqa: E402
from app.agent.behavior_cloning import collect_demonstrations, pretrain_policy  # noqa: E402
from app.agent.ortools_baseline import solve_milp_schedule  # noqa: E402
from app.agent.ppo_scheduler import resolve_path, run_policy  # noqa: E402
from app.agent.scenarios import ScenarioSampler, dates_of_year  # noqa: E402
from app.agent.umkm_env import OBS_VERSION, UMKMDispatchEnv, obs_size  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.digital_twin.factory_model import simulate_schedule, validate_schedule  # noqa: E402


def log(msg: str) -> None:
    print(msg, flush=True)


def _problems(sampler: ScenarioSampler, n: int, seed: int) -> list:
    rng = np.random.default_rng(seed)
    return [sampler(rng) for _ in range(n)]


def _reference(problems: list, time_limit_s: float) -> list[dict]:
    """Biaya pembanding per skenario (dihitung sekali)."""
    out = []
    for p in problems:
        habit = habit_schedule(p.machines)
        idle = habit_idle_load_w(p.machines)
        res = solve_milp_schedule(p, time_limit_s=time_limit_s)
        ort = res.schedule if res.schedule is not None else greedy_schedule(p)
        out.append(
            {
                "date": p.target_date.isoformat() if p.target_date else None,
                "n_machines": p.n_machines,
                "kwp": p.kwp,
                "battery_kwh": round(p.battery.capacity_wh / 1000.0, 2) if p.has_battery else 0.0,
                "habit_cost": simulate_schedule(p, habit, extra_load_w=idle).cost_idr,
                "habit_no_idle_cost": simulate_schedule(p, habit).cost_idr,
                "greedy_cost": simulate_schedule(p, greedy_schedule(p)).cost_idr,
                "ortools_cost": simulate_schedule(p, ort).cost_idr,
                "ortools_status": res.status,
                "ortools_time_s": res.solve_time_s,
            }
        )
    return out


def _evaluate(model, problems: list, refs: list[dict], n_max: int) -> dict:
    rows = []
    for p, ref in zip(problems, refs):
        env = UMKMDispatchEnv(problem=p, n_max_machines=n_max)
        t0 = time.perf_counter()
        sched = run_policy(model, env)
        dt = time.perf_counter() - t0
        errs = validate_schedule(p.machines, sched)
        cost = simulate_schedule(p, sched).cost_idr
        rows.append({**ref, "ppo_cost": cost, "ppo_time_s": dt, "ppo_deadlines_met": not errs})
    return {"rows": rows, "summary": _summary(rows)}


def _summary(rows: list[dict]) -> dict:
    def tot(k: str) -> float:
        return float(sum(r[k] for r in rows))

    habit, habit_ni, ort, ppo, greedy = (
        tot("habit_cost"), tot("habit_no_idle_cost"), tot("ortools_cost"), tot("ppo_cost"), tot("greedy_cost")
    )
    pv_rows = [r for r in rows if r["kwp"] > 0 or r["battery_kwh"] > 0]
    # Perilaku planner solver="auto": PPO bila sah & tidak lebih mahal dari kebiasaan
    # lama tanpa idle, selain itu OR-Tools.
    auto = float(sum(
        r["ppo_cost"] if (r["ppo_deadlines_met"] and r["ppo_cost"] <= r["habit_no_idle_cost"] + 0.5)
        else r["ortools_cost"]
        for r in rows
    ))
    gaps = [(r["ppo_cost"] - r["ortools_cost"]) / r["ortools_cost"] * 100 for r in rows if r["ortools_cost"] > 0]
    return {
        "n_scenarios": len(rows),
        "n_with_pv_or_battery": len(pv_rows),
        "mean_cost_idr": {
            "kebiasaan_lama": habit / len(rows),
            "kebiasaan_lama_tanpa_idle": habit_ni / len(rows),
            "greedy": greedy / len(rows),
            "ortools": ort / len(rows),
            "ppo": ppo / len(rows),
            "auto_planner": auto / len(rows),
        },
        "savings_vs_habit_pct": {
            "greedy": (habit - greedy) / habit * 100 if habit else 0.0,
            "ortools": (habit - ort) / habit * 100 if habit else 0.0,
            "ppo": (habit - ppo) / habit * 100 if habit else 0.0,
            "auto_planner": (habit - auto) / habit * 100 if habit else 0.0,
        },
        # Bagian yang benar-benar dikendalikan penjadwal (tanpa efek idle).
        "shift_savings_vs_habit_no_idle_idr_per_day": {
            "greedy": (habit_ni - greedy) / len(rows),
            "ortools": (habit_ni - ort) / len(rows),
            "ppo": (habit_ni - ppo) / len(rows),
        },
        "ppo_gap_vs_ortools_pct_total": (ppo - ort) / ort * 100 if ort else 0.0,
        "ppo_gap_vs_ortools_pct_mean": float(np.mean(gaps)) if gaps else 0.0,
        "ppo_gap_vs_ortools_pct_max": float(np.max(gaps)) if gaps else 0.0,
        "ppo_le_ortools_frac": float(np.mean([r["ppo_cost"] <= r["ortools_cost"] + 0.5 for r in rows])),
        "ppo_worse_than_habit_no_idle_frac": float(
            np.mean([r["ppo_cost"] > r["habit_no_idle_cost"] + 0.5 for r in rows])
        ),
        "ppo_deadlines_met_rate": float(np.mean([r["ppo_deadlines_met"] for r in rows])),
        "ppo_mean_time_s": float(np.mean([r["ppo_time_s"] for r in rows])),
        "ortools_mean_time_s": float(np.mean([r["ortools_time_s"] for r in rows])),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timesteps", type=int, default=30_000, help="Langkah PPO setelah BC (0 = BC saja)")
    ap.add_argument("--bc-episodes", type=int, default=150, help="Jumlah hari demonstrasi")
    ap.add_argument("--bc-epochs", type=int, default=30)
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--n-steps", type=int, default=384, help="Langkah rollout per env per update PPO")
    ap.add_argument("--lr", type=float, default=1e-4, help="Learning rate PPO (kecil agar BC tidak rusak)")
    ap.add_argument("--n-max", type=int, default=settings.rl_max_machines)
    ap.add_argument("--train-year", type=int, default=2025)
    ap.add_argument("--eval-year", type=int, default=2024)
    ap.add_argument("--val-days", type=int, default=15)
    ap.add_argument("--eval-days", type=int, default=30)
    ap.add_argument("--demo-time-limit", type=float, default=2.0, help="Batas waktu OR-Tools per demonstrasi (detik)")
    ap.add_argument("--eval-time-limit", type=float, default=5.0, help="Batas waktu OR-Tools saat evaluasi (detik)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--output", default=settings.rl_model_path)
    ap.add_argument("--meta-output", default=settings.rl_meta_path)
    ap.add_argument("--eval-output", default=settings.agent_eval_path)
    args = ap.parse_args()

    try:
        import torch
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.vec_env import DummyVecEnv
    except ImportError:
        log("Paket RL belum terpasang. Jalankan: pip install -r requirements-rl.txt")
        return 1
    torch.manual_seed(args.seed)
    t_start = time.perf_counter()
    n_max = int(args.n_max)

    train_sampler = ScenarioSampler(n_max, year=args.train_year)
    val_sampler = ScenarioSampler(n_max, year=args.train_year)
    test_sampler = ScenarioSampler(n_max, dates=dates_of_year(args.eval_year))

    def make_env(rank: int):
        def _init():
            env = UMKMDispatchEnv(problem_sampler=train_sampler, n_max_machines=n_max)
            env.reset(seed=args.seed * 1000 + rank)
            return env

        return _init

    vec_env = DummyVecEnv([make_env(i) for i in range(args.n_envs)])
    model = MaskablePPO(
        "MlpPolicy",
        vec_env,
        learning_rate=args.lr,
        n_steps=args.n_steps,
        batch_size=256,
        n_epochs=5,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.1,
        ent_coef=0.0,
        policy_kwargs={"net_arch": {"pi": [128, 128], "vf": [128, 128]}},
        seed=args.seed,
        device="cpu",
        verbose=0,
    )

    log(f"[1/5] Mengumpulkan {args.bc_episodes} demonstrasi (tahun {args.train_year}) ...")
    demos = collect_demonstrations(
        train_sampler, args.bc_episodes, n_max, seed=args.seed + 1,
        time_limit_s=args.demo_time_limit, gamma=model.gamma, log=log,
    )
    log(f"      {len(demos)} pasangan (obs, aksi); sumber: {dict(demos.sources)}")

    log("[2/5] Behavior cloning ...")
    bc_losses = pretrain_policy(model, demos, epochs=args.bc_epochs, seed=args.seed, log=log)

    log(f"[3/5] Menyiapkan set validasi ({args.val_days} hari) & uji ({args.eval_days} hari, tahun {args.eval_year}) ...")
    val_problems = _problems(val_sampler, args.val_days, args.seed + 500)
    test_problems = _problems(test_sampler, args.eval_days, args.seed + 900)
    val_refs = _reference(val_problems, args.eval_time_limit)
    test_refs = _reference(test_problems, args.eval_time_limit)

    bc_val = _evaluate(model, val_problems, val_refs, n_max)["summary"]
    log(f"      BC  validasi: biaya rata-rata PPO Rp {bc_val['mean_cost_idr']['ppo']:,.0f} "
        f"vs OR-Tools Rp {bc_val['mean_cost_idr']['ortools']:,.0f}")
    bc_state = copy.deepcopy(model.policy.state_dict())

    ppo_val = None
    chosen = "bc"
    if args.timesteps > 0:
        log(f"[4/5] Fine-tuning MaskablePPO {args.timesteps} langkah ...")
        t0 = time.perf_counter()
        model.learn(total_timesteps=args.timesteps)
        log(f"      selesai dalam {time.perf_counter() - t0:.0f} s")
        ppo_val = _evaluate(model, val_problems, val_refs, n_max)["summary"]
        log(f"      PPO validasi: biaya rata-rata Rp {ppo_val['mean_cost_idr']['ppo']:,.0f}")
        if ppo_val["mean_cost_idr"]["ppo"] <= bc_val["mean_cost_idr"]["ppo"]:
            chosen = "bc+ppo"
        else:
            model.policy.load_state_dict(bc_state)
            log("      PPO tidak lebih baik dari BC pada validasi → bobot BC dipakai.")
    else:
        log("[4/5] --timesteps 0: lewati PPO.")

    log("[5/5] Evaluasi akhir pada set uji ...")
    test = _evaluate(model, test_problems, test_refs, n_max)
    s = test["summary"]
    log(json.dumps(s, indent=2, ensure_ascii=False))

    out = resolve_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(out))
    meta = {
        "obs_version": OBS_VERSION,
        "obs_dim": obs_size(n_max),
        "n_max_machines": n_max,
        "algorithm": "MaskablePPO (sb3-contrib)",
        "chosen": chosen,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timesteps": args.timesteps,
        "bc_episodes": args.bc_episodes,
        "seed": args.seed,
    }
    meta_path = resolve_path(args.meta_output)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    report = {
        "generated_at": meta["trained_at"],
        "status": "belum divalidasi dengan data UMKM nyata",
        "keterangan": (
            "Skenario uji SINTETIS (mesin, pesanan, kWp, baterai acak berdasar asumsi) dengan cuaca "
            f"tahun {args.eval_year}; biaya dari simulasi tiruan digital dengan tarif "
            f"{settings.tariff_group} ({settings.tariff_scheme}). Kebiasaan lama termasuk mesin idle."
        ),
        "model": meta,
        "training": {
            "train_year": args.train_year,
            "demo_sources": dict(demos.sources),
            "demo_pairs": len(demos),
            "bc_epochs": args.bc_epochs,
            "bc_final_loss": bc_losses[-1] if bc_losses else None,
            "ppo_timesteps": args.timesteps,
            "validation_bc": bc_val,
            "validation_bc_ppo": ppo_val,
            "wall_time_s": round(time.perf_counter() - t_start, 1),
        },
        "test": {"eval_year": args.eval_year, "summary": s, "rows": test["rows"]},
    }
    eval_path = resolve_path(args.eval_output)
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Model → {out}\nMetadata → {meta_path}\nEvaluasi → {eval_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
