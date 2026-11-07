from datetime import date, datetime
from typing import List
from app.schemas.dispatch import DispatchResponse, SlotSchedule


def _slot_to_time(slot_index: int) -> str:
    hour = slot_index // 4
    minute = (slot_index % 4) * 15
    return f"{hour:02d}:{minute:02d}"


def generate_daily_brief(
    dispatch: DispatchResponse,
    umkm_name: str = "Usaha Anda",
    target_date: date | None = None,
) -> str:
    """
    Generate draf pesan WhatsApp harian dalam Bahasa Indonesia.
    Siap kirim ke pemilik UMKM pukul 17:30 WIB.
    """
    if target_date is None:
        target_date = date.today()

    day_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    day_name = day_names[target_date.weekday()]
    date_str = target_date.strftime("%-d %B %Y")

    # Temukan jam operasi puncak (slot dengan P_pv tertinggi yang aktif)
    active_slots = [s for s in dispatch.schedule if s.state == 1]
    if active_slots:
        peak_slot = max(active_slots, key=lambda s: s.p_pv_w)
        peak_window = _slot_to_time(peak_slot.slot_index)
    else:
        peak_window = "10:00"

    # Ringkasan mesin yang dijadwalkan
    machines_on: dict[str, list[str]] = {}
    for slot in dispatch.schedule:
        if slot.state == 1:
            if slot.machine_id not in machines_on:
                machines_on[slot.machine_id] = []
            machines_on[slot.machine_id].append(_slot_to_time(slot.slot_index))

    machine_lines = []
    for mid, times in machines_on.items():
        if times:
            start = times[0]
            end = times[-1]
            machine_lines.append(f"  • {mid}: {start} – {end}")

    machine_text = "\n".join(machine_lines) if machine_lines else "  • (tidak ada mesin fleksibel aktif hari ini)"

    savings_pct = dispatch.savings_pct
    savings_idr = dispatch.savings_idr

    message = f"""🌞 *NOTA LISTRIK – Jadwal Harian*
📅 {day_name}, {date_str}
━━━━━━━━━━━━━━━━━━━━━
Halo *{umkm_name}*! Ini jadwal mesin hari ini:

⚡ *Jam Surya Puncak:* ~{peak_window} – {int(int(peak_window.split(':')[0])) + 4:02d}:00
🔧 *Mesin Dijadwalkan ke Jendela Surya:*
{machine_text}

💰 *Estimasi Penghematan Hari Ini:*
  Rp {savings_idr:,.0f} ({savings_pct:.1f}% lebih hemat)

📊 *Ringkasan Energi:*
  ☀️ PLTS dipakai: {dispatch.total_pv_kwh:.2f} kWh
  🏭 Tarik grid PLN: {dispatch.total_grid_kwh:.2f} kWh
  📉 Curtailment: {dispatch.curtailment_kwh:.2f} kWh

✅ Semua mesin wajib selesai sebelum 17:00.
━━━━━━━━━━━━━━━━━━━━━
_Pesan ini dikirim otomatis oleh NOTA LISTRIK AI._
_© {target_date.year} UNS Innovation Hackathon_"""

    return message
