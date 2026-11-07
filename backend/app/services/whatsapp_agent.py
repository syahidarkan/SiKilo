"""
Penyusun pesan WhatsApp WASKITA (Bahasa Indonesia, ringkas untuk WA).

- ``generate_daily_brief(plan, umkm_name, target_date)`` — jadwal mesin untuk
  satu hari dari ``PlanResult`` (planner) atau ``DispatchResponse`` (API):
  jam ON per mesin (blok berurutan), perkiraan hemat dibanding kebiasaan
  lama (boleh negatif → kalimat jujur), dan peringatan tenggat.
- ``generate_weekly_nota(...)`` — nota mingguan dari ``EnergyLedger``: kWh & Rp
  per mesin minggu ini vs minggu lalu, mesin paling boros, dan tips idle
  (pemakaian di luar jam kerja yang TERUKUR di buku energi).

Semua fungsi di sini murni (tanpa DB/jaringan) sehingga mudah dites.
Tanggal diformat manual (tanpa ``strftime("%-d")`` yang gagal di Windows dan
tanpa nama bulan berbahasa Inggris).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Optional, Sequence

import numpy as np

from app.core.config import settings

MAX_MESSAGE_CHARS = 1000
BRAND = "WASKITA"
BASELOAD_LABEL = "Baseload / Background"

HARI = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
BULAN = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)
BULAN_SINGKAT = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")

# Selisih biaya di bawah nilai ini dianggap "tidak ada selisih berarti".
_NEGLIGIBLE_IDR = 50.0


# ── Format angka & tanggal (Indonesia) ─────────────────────────────────────
def format_tanggal(d: date, with_day: bool = True) -> str:
    """'Sabtu, 8 November 2026' (atau tanpa nama hari)."""
    core = f"{d.day} {BULAN[d.month - 1]} {d.year}"
    return f"{HARI[d.weekday()]}, {core}" if with_day else core


def format_rentang(start: date, end: date) -> str:
    """'1–7 Nov 2026', '28 Okt – 3 Nov 2026', '29 Des 2025 – 4 Jan 2026'."""
    if start.year != end.year:
        return f"{start.day} {BULAN_SINGKAT[start.month - 1]} {start.year} – {end.day} {BULAN_SINGKAT[end.month - 1]} {end.year}"
    if start.month != end.month:
        return f"{start.day} {BULAN_SINGKAT[start.month - 1]} – {end.day} {BULAN_SINGKAT[end.month - 1]} {end.year}"
    return f"{start.day}–{end.day} {BULAN_SINGKAT[end.month - 1]} {end.year}"


def format_rupiah(value: float) -> str:
    """'Rp 12.345' (pemisah ribuan titik, dibulatkan ke rupiah); negatif → '-Rp 500'."""
    v = float(value)
    s = f"{abs(round(v)):,.0f}".replace(",", ".")
    return f"-Rp {s}" if round(v) < 0 else f"Rp {s}"


def format_angka(value: float, decimals: int = 1) -> str:
    """Desimal koma: 12.5 → '12,5'; ribuan titik."""
    s = f"{float(value):,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _slot_label(slot: int) -> str:
    slot = int(slot)
    return f"{slot // 4:02d}:{(slot % 4) * 15:02d}"


def _blocks(column: Iterable[int]) -> list[tuple[int, int]]:
    """Blok ON [start, end) dari kolom 0/1."""
    out: list[tuple[int, int]] = []
    start: Optional[int] = None
    t = -1
    for t, v in enumerate(column):
        if v and start is None:
            start = t
        elif not v and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, t + 1))
    return out


# ── Normalisasi rencana (PlanResult | DispatchResponse) ───────────────────
@dataclass
class MachineLine:
    machine_id: str
    label: str
    blocks: list[tuple[str, str]]  # [("09:00", "11:30"), ...]
    deadline_met: bool = True
    deadline: str = ""


@dataclass
class BriefData:
    machines: list[MachineLine]
    cost_idr: Optional[float]
    baseline_cost_idr: Optional[float]
    savings_idr: float
    savings_pct: float
    deadlines_met: bool
    pv_used_kwh: float
    pv_generated_kwh: float
    kwp: float
    violations: list[str]
    idle_savings_idr: float = 0.0


def _g(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _from_plan_result(plan: Any) -> BriefData:
    schedule = np.asarray(plan.schedule)
    ids = list(plan.machine_ids)
    machines_meta = {getattr(m, "machine_id", None): m for m in (getattr(plan, "machines", None) or [])}
    violations = [str(v) for v in (getattr(plan, "violations", None) or [])]
    bad = {v.split(":", 1)[0].strip() for v in violations}
    lines: list[MachineLine] = []
    for i, mid in enumerate(ids):
        meta = machines_meta.get(mid)
        col = schedule[:, i] if schedule.ndim == 2 and schedule.shape[1] > i else []
        deadline_slot = getattr(meta, "job_deadline_slot", None) if meta is not None else None
        lines.append(
            MachineLine(
                machine_id=str(mid),
                label=str(getattr(meta, "label", mid) if meta is not None else mid),
                blocks=[(_slot_label(s), _slot_label(e)) for s, e in _blocks(col)],
                deadline_met=str(mid) not in bad,
                deadline=_slot_label(deadline_slot) if deadline_slot is not None else "",
            )
        )
    pv_w = getattr(plan, "pv_w", None)
    pv_gen = float(np.sum(pv_w)) * 0.25 / 1000.0 if pv_w is not None else 0.0
    return BriefData(
        machines=lines,
        cost_idr=float(plan.cost_idr),
        baseline_cost_idr=float(plan.baseline_cost_idr),
        savings_idr=float(plan.savings_idr),
        savings_pct=float(plan.savings_pct),
        deadlines_met=bool(plan.deadlines_met),
        pv_used_kwh=float(getattr(plan, "pv_used_kwh", 0.0) or 0.0),
        pv_generated_kwh=pv_gen,
        kwp=float(getattr(plan, "kwp", 0.0) or 0.0),
        violations=violations,
        idle_savings_idr=float(getattr(plan, "idle_savings_idr", 0.0) or 0.0),
    )


def _from_dispatch_response(resp: Any) -> BriefData:
    lines: list[MachineLine] = []
    machines = _g(resp, "machines") or []
    if machines:
        for m in machines:
            window = str(_g(m, "window", "") or "")
            lines.append(
                MachineLine(
                    machine_id=str(_g(m, "machine_id")),
                    label=str(_g(m, "label") or _g(m, "machine_id")),
                    blocks=[(str(_g(b, "start")), str(_g(b, "end"))) for b in (_g(m, "blocks") or [])],
                    deadline_met=bool(_g(m, "deadline_met", True)),
                    deadline=window.split("–")[-1].strip() if "–" in window else "",
                )
            )
    else:
        # Respons lama: susun ulang dari slot (machines_on, atau machine_id usang).
        per_machine: dict[str, list[int]] = {}
        for slot in _g(resp, "schedule") or []:
            on = list(_g(slot, "machines_on") or [])
            if not on and int(_g(slot, "state", 0) or 0) == 1:
                mid = _g(slot, "machine_id")
                if mid and mid != "baseload":
                    on = [mid]
            for mid in on:
                per_machine.setdefault(str(mid), []).append(int(_g(slot, "slot_index")))
        for mid, slots in per_machine.items():
            col = np.zeros(96, dtype=np.int8)
            col[[s for s in slots if 0 <= s < 96]] = 1
            lines.append(
                MachineLine(
                    machine_id=mid,
                    label=mid,
                    blocks=[(_slot_label(s), _slot_label(e)) for s, e in _blocks(col)],
                )
            )
    return BriefData(
        machines=lines,
        cost_idr=_g(resp, "total_cost_idr"),
        baseline_cost_idr=_g(resp, "baseline_cost_idr"),
        savings_idr=float(_g(resp, "savings_idr", 0.0) or 0.0),
        savings_pct=float(_g(resp, "savings_pct", 0.0) or 0.0),
        deadlines_met=bool(_g(resp, "deadlines_met", True)),
        pv_used_kwh=float(_g(resp, "total_pv_kwh", 0.0) or 0.0),
        pv_generated_kwh=float(_g(resp, "pv_generated_kwh", 0.0) or 0.0),
        kwp=0.0,
        violations=[],
        idle_savings_idr=float(_g(_g(resp, "savings_breakdown"), "idle_idr", 0.0) or 0.0),
    )


def brief_data(plan: Any) -> BriefData:
    """Ekstrak data pesan dari ``PlanResult`` (punya ``machine_ids``) atau ``DispatchResponse``."""
    if hasattr(plan, "machine_ids") and hasattr(plan, "schedule") and not isinstance(plan, dict):
        return _from_plan_result(plan)
    return _from_dispatch_response(plan)


# ── Pesan harian ───────────────────────────────────────────────────────────
def _savings_sentence(d: BriefData) -> str:
    s = d.savings_idr
    if abs(s) < _NEGLIGIBLE_IDR:
        if d.pv_generated_kwh <= 0 and settings.tariff_scheme == "flat":
            return (
                "Perkiraan biaya sama dengan kebiasaan lama: tarif PLN flat dan belum ada PLTS, "
                "jadi menggeser jam tidak mengubah tagihan. Hemat hanya dari mematikan mesin yang menganggur."
            )
        return "Perkiraan biaya hampir sama dengan kebiasaan lama."
    if s > 0:
        text = (
            f"Perkiraan hemat: *{format_rupiah(s)}* ({format_angka(d.savings_pct)}%) "
            "dibanding kebiasaan lama."
        )
        if d.idle_savings_idr >= 0.5 * s:
            text += " Sebagian besar dari tidak membiarkan mesin menyala menganggur."
        return text
    return (
        f"Jujur saja: jadwal ini diperkirakan {format_rupiah(abs(s))} LEBIH MAHAL daripada kebiasaan lama. "
        "Boleh tetap pakai kebiasaan lama untuk hari itu."
    )


def _machine_line(m: MachineLine, max_blocks: int) -> str:
    if not m.blocks:
        return f"- {m.label}: tidak dijadwalkan"
    shown = [f"{a}–{b}" for a, b in m.blocks[:max_blocks]]
    extra = len(m.blocks) - len(shown)
    text = ", ".join(shown) + (f" (+{extra} blok)" if extra > 0 else "")
    return f"- {m.label}: {text}"


def _compose_brief(
    umkm_name: str, target_date: date, d: BriefData, max_machines: int, max_blocks: int, with_pv: bool
) -> str:
    parts: list[str] = [
        f"*{BRAND} – Jadwal Mesin*",
        format_tanggal(target_date),
        f"Halo, {umkm_name}! Jam nyala mesin yang disarankan:",
    ]
    machines = d.machines[:max_machines]
    if machines:
        parts.extend(_machine_line(m, max_blocks) for m in machines)
        rest = len(d.machines) - len(machines)
        if rest > 0:
            parts.append(f"- (+{rest} mesin lain, lihat dasbor)")
    else:
        parts.append("- Belum ada mesin yang terdaftar.")
    parts.append("")
    parts.append(_savings_sentence(d))
    if with_pv and d.pv_generated_kwh > 0:
        parts.append(
            f"PLTS diperkirakan menghasilkan {format_angka(d.pv_generated_kwh)} kWh; "
            f"{format_angka(d.pv_used_kwh)} kWh terpakai sendiri."
        )
    late = [m for m in d.machines if not m.deadline_met]
    if late:
        names = ", ".join(m.label for m in late[:3]) + (" dll." if len(late) > 3 else "")
        parts.append(f"PERHATIAN: {names} belum bisa selesai sebelum tenggat. Cek jam kerja/pesanan.")
    elif not d.deadlines_met:
        parts.append("PERHATIAN: ada pekerjaan yang belum bisa selesai sebelum tenggat. Cek dasbor.")
    parts.append("")
    parts.append(f"_Perkiraan tiruan digital {BRAND}, bukan tagihan PLN._")
    return "\n".join(parts)


def generate_daily_brief(
    plan: Any,
    umkm_name: str = "Usaha Anda",
    target_date: Optional[date] = None,
) -> str:
    """
    Pesan WhatsApp jadwal mesin (< 1000 karakter).

    ``plan`` boleh ``PlanResult`` (app.agent.planner) atau ``DispatchResponse``
    (app.schemas.dispatch). ``target_date`` default: tanggal pada rencana,
    lalu hari ini.
    """
    if target_date is None:
        target_date = _g(plan, "target_date") or date.today()
    d = brief_data(plan)
    name = (umkm_name or "Usaha Anda").strip()[:60]
    # Turunkan detail bertahap sampai muat batas karakter WA.
    for max_machines, max_blocks, with_pv in ((10, 4, True), (8, 3, True), (6, 2, True), (5, 2, False), (3, 1, False)):
        msg = _compose_brief(name, target_date, d, max_machines, max_blocks, with_pv)
        if len(msg) <= MAX_MESSAGE_CHARS:
            return msg
    return msg[: MAX_MESSAGE_CHARS - 1] + "…"


# ── Nota mingguan ──────────────────────────────────────────────────────────
@dataclass
class MachineWeekUsage:
    """Pemakaian satu label peralatan selama seminggu (dari EnergyLedger)."""

    label: str
    kwh: float = 0.0
    cost_idr: float = 0.0
    prev_kwh: float = 0.0
    prev_cost_idr: float = 0.0
    # Energi yang tercatat di luar jam kerja (indikasi mesin menganggur/lupa dimatikan).
    off_hours_kwh: float = 0.0
    off_hours_cost_idr: float = 0.0
    off_hours_hours: int = 0


def _change_text(now: float, prev: float) -> str:
    if prev <= 1e-9:
        return "baru" if now > 1e-9 else "tetap"
    pct = (now - prev) / prev * 100.0
    if abs(pct) < 1.0:
        return "tetap"
    return f"{'naik' if pct > 0 else 'turun'} {format_angka(abs(pct), 0)}%"


def _compose_weekly(
    umkm_name: str,
    week_start: date,
    week_end: date,
    usage: Sequence[MachineWeekUsage],
    max_lines: int,
    max_tips: int,
) -> str:
    total_kwh = sum(u.kwh for u in usage)
    total_cost = sum(u.cost_idr for u in usage)
    prev_kwh = sum(u.prev_kwh for u in usage)
    prev_cost = sum(u.prev_cost_idr for u in usage)

    parts = [
        f"*{BRAND} – Nota Mingguan*",
        format_rentang(week_start, week_end),
        f"Halo, {umkm_name}! Ringkasan listrik seminggu terakhir:",
        "",
    ]
    if total_kwh <= 1e-9 and prev_kwh <= 1e-9:
        parts.append("Belum ada data pemakaian dari perangkat WASKITA untuk periode ini.")
        parts.append("Pastikan perangkat menyala dan tersambung internet.")
        return "\n".join(parts)

    parts.append(
        f"Total: {format_angka(total_kwh)} kWh = *{format_rupiah(total_cost)}* "
        f"({_change_text(total_cost, prev_cost)} dari minggu lalu {format_rupiah(prev_cost)})"
    )
    machines = sorted(
        (u for u in usage if u.label != BASELOAD_LABEL and (u.kwh > 1e-9 or u.prev_kwh > 1e-9)),
        key=lambda u: u.cost_idr,
        reverse=True,
    )
    base = next((u for u in usage if u.label == BASELOAD_LABEL), None)
    shown = machines[:max_lines]
    for u in shown:
        parts.append(
            f"- {u.label}: {format_angka(u.kwh)} kWh, {format_rupiah(u.cost_idr)} ({_change_text(u.cost_idr, u.prev_cost_idr)})"
        )
    if len(machines) > len(shown):
        rest = machines[len(shown):]
        parts.append(f"- Lainnya ({len(rest)} mesin): {format_rupiah(sum(u.cost_idr for u in rest))}")
    if base is not None and base.kwh > 1e-9:
        parts.append(f"- Beban dasar/lainnya: {format_angka(base.kwh)} kWh, {format_rupiah(base.cost_idr)}")

    if machines and machines[0].cost_idr > 0:
        top = machines[0]
        share = top.cost_idr / total_cost * 100.0 if total_cost > 0 else 0.0
        parts.append("")
        parts.append(f"Paling boros: *{top.label}* ({format_angka(share, 0)}% biaya).")

    tips: list[str] = []
    idle = sorted((u for u in machines if u.off_hours_kwh > 0.05), key=lambda u: u.off_hours_cost_idr, reverse=True)
    for u in idle[:max_tips]:
        tips.append(
            f"- {u.label} tercatat menyala di luar jam kerja {u.off_hours_hours} jam "
            f"({format_rupiah(u.off_hours_cost_idr)}). Matikan bila tidak dipakai."
        )
    if not tips:
        tips.append("- Matikan mesin yang menganggur (tanpa beban) di sela pekerjaan; daya idle tetap terbayar.")
    parts.append("")
    parts.append("Tips:")
    parts.extend(tips)
    parts.append("")
    parts.append(f"_Data perangkat {BRAND} (estimasi NILM), bukan tagihan resmi PLN._")
    return "\n".join(parts)


def generate_weekly_nota(
    umkm_name: str,
    week_start: date,
    week_end: date,
    usage: Sequence[MachineWeekUsage | dict],
) -> str:
    """
    Nota mingguan (< 1000 karakter): kWh & Rp per mesin minggu ini vs minggu
    lalu, mesin paling boros, dan tips idle dari pemakaian di luar jam kerja.

    ``usage`` biasanya dibuat oleh ``app.services.jobs.weekly_usage``.
    """
    items = [u if isinstance(u, MachineWeekUsage) else MachineWeekUsage(**u) for u in usage]
    name = (umkm_name or "Usaha Anda").strip()[:60]
    for max_lines, max_tips in ((8, 2), (6, 2), (4, 1), (3, 1), (2, 1)):
        msg = _compose_weekly(name, week_start, week_end, items, max_lines, max_tips)
        if len(msg) <= MAX_MESSAGE_CHARS:
            return msg
    return msg[: MAX_MESSAGE_CHARS - 1] + "…"


__all__ = [
    "MAX_MESSAGE_CHARS",
    "MachineWeekUsage",
    "BriefData",
    "brief_data",
    "format_rupiah",
    "format_tanggal",
    "format_rentang",
    "generate_daily_brief",
    "generate_weekly_nota",
]
