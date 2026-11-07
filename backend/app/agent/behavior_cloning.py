"""
Behavior cloning (BC) untuk menghangatkan kebijakan MaskablePPO.

Demonstrasi per skenario:
- jadwal OR-Tools bila ia lebih murah daripada kebiasaan lama (selisih > Rp 1);
- selain itu jadwal **kebiasaan lama pemilik** (mis. hari tanpa PLTS dengan
  tarif flat: semua jadwal sama mahalnya, jadi agen meniru kebiasaan pemilik
  agar perubahan yang disarankan minimal).

Setiap demonstrasi diputar ulang di ``UMKMDispatchEnv`` sehingga pasangan
(observasi, aksi, mask) persis sama dengan yang dilihat kebijakan saat
inferensi. Pretraining meminimalkan −log π(a_demo | s, mask) + c·(V − G)².

torch hanya di-import di ``pretrain_policy`` (modul ini aman di-import tanpa torch).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from app.agent.baseline import habit_schedule
from app.agent.ortools_baseline import solve_milp_schedule
from app.agent.umkm_env import UMKMDispatchEnv
from app.core.tariff import N_SLOTS
from app.digital_twin.factory_model import DispatchProblem, simulate_schedule


@dataclass
class DemoDataset:
    obs: np.ndarray        # (N, obs_dim) float32
    actions: np.ndarray    # (N, n_max) int64
    masks: np.ndarray      # (N, 2·n_max) bool
    returns: np.ndarray    # (N,) float32, return terdiskon dari langkah itu
    sources: Counter = field(default_factory=Counter)

    def __len__(self) -> int:
        return int(self.obs.shape[0])


def demo_schedule(problem: DispatchProblem, time_limit_s: float = 2.0) -> tuple[np.ndarray, str]:
    """Pilih jadwal demonstrasi untuk satu skenario → (jadwal, sumber)."""
    habit = habit_schedule(problem.machines)
    if problem.n_machines == 0:
        return habit, "habit"
    res = solve_milp_schedule(problem, time_limit_s=time_limit_s)
    if res.schedule is None:
        return habit, "habit"
    c_h = simulate_schedule(problem, habit).cost_idr
    c_o = simulate_schedule(problem, res.schedule).cost_idr
    if c_o < c_h - 1.0:
        return res.schedule, "ortools"
    return habit, "habit"


def rollout_schedule(
    problem: DispatchProblem, schedule: np.ndarray, n_max: int, gamma: float = 0.99
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    """
    Putar ulang jadwal di env → (obs, actions, masks, returns, cocok). ``cocok``
    False bila env harus mengoreksi aksi (jadwal melanggar aturan mask).
    """
    env = UMKMDispatchEnv(problem=problem, n_max_machines=n_max)
    obs, _ = env.reset(options={"problem": problem})
    obs_l, act_l, mask_l, rew_l = [], [], [], []
    for t in range(N_SLOTS):
        a = np.zeros(n_max, dtype=np.int64)
        a[: problem.n_machines] = schedule[t]
        obs_l.append(obs)
        mask_l.append(env.action_masks())
        obs, r, _, _, info = env.step(a)
        eff = np.zeros(n_max, dtype=np.int64)
        eff[: problem.n_machines] = info["effective_action"]
        act_l.append(eff)
        rew_l.append(r)
    match = bool(np.array_equal(env.schedule, np.asarray(schedule, dtype=np.int8)))
    rets = np.zeros(N_SLOTS, dtype=np.float32)
    g = 0.0
    for t in range(N_SLOTS - 1, -1, -1):
        g = rew_l[t] + gamma * g
        rets[t] = g
    return np.asarray(obs_l, np.float32), np.asarray(act_l), np.asarray(mask_l, bool), rets, match


def collect_demonstrations(
    sampler: Callable[[np.random.Generator], DispatchProblem],
    n_episodes: int,
    n_max: int,
    seed: int = 0,
    time_limit_s: float = 2.0,
    gamma: float = 0.99,
    log: Optional[Callable[[str], None]] = None,
) -> DemoDataset:
    rng = np.random.default_rng(seed)
    obs, acts, masks, rets = [], [], [], []
    sources: Counter = Counter()
    for ep in range(n_episodes):
        problem = sampler(rng)
        sched, src = demo_schedule(problem, time_limit_s=time_limit_s)
        o, a, m, g, match = rollout_schedule(problem, sched, n_max, gamma)
        if not match:
            sources["dibuang_tidak_cocok"] += 1
            continue
        sources[src] += 1
        obs.append(o)
        acts.append(a)
        masks.append(m)
        rets.append(g)
        if log and (ep + 1) % 20 == 0:
            log(f"  demo {ep + 1}/{n_episodes}: {dict(sources)}")
    if not obs:
        raise RuntimeError("Tidak ada demonstrasi yang valid")
    return DemoDataset(
        obs=np.concatenate(obs),
        actions=np.concatenate(acts),
        masks=np.concatenate(masks),
        returns=np.concatenate(rets),
        sources=sources,
    )


def pretrain_policy(
    model,
    dataset: DemoDataset,
    epochs: int = 20,
    batch_size: int = 512,
    lr: float = 1e-3,
    value_coef: float = 0.05,
    seed: int = 0,
    log: Optional[Callable[[str], None]] = None,
) -> list[float]:
    """Latih ``model.policy`` (MaskableActorCriticPolicy) meniru demonstrasi."""
    import torch

    policy = model.policy
    device = policy.device
    policy.set_training_mode(True)
    optim = torch.optim.Adam(policy.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    n = len(dataset)
    losses: list[float] = []
    for ep in range(epochs):
        perm = rng.permutation(n)
        tot, cnt, correct = 0.0, 0, 0
        for s in range(0, n, batch_size):
            idx = perm[s:s + batch_size]
            obs_t = torch.as_tensor(dataset.obs[idx], device=device)
            act_t = torch.as_tensor(dataset.actions[idx], device=device)
            ret_t = torch.as_tensor(dataset.returns[idx], device=device)
            values, log_prob, _ = policy.evaluate_actions(obs_t, act_t, action_masks=dataset.masks[idx])
            loss = -log_prob.mean() + value_coef * torch.nn.functional.mse_loss(values.flatten(), ret_t)
            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optim.step()
            tot += float(loss.item()) * len(idx)
            cnt += len(idx)
            with torch.no_grad():
                dist = policy.get_distribution(obs_t, action_masks=dataset.masks[idx])
                pred = dist.get_actions(deterministic=True)
                correct += int((pred == act_t).all(dim=1).sum().item())
        losses.append(tot / max(cnt, 1))
        if log:
            log(f"  BC epoch {ep + 1}/{epochs}: loss {losses[-1]:.4f}, akurasi aksi-slot {correct / max(cnt, 1):.3f}")
    policy.set_training_mode(False)
    return losses
