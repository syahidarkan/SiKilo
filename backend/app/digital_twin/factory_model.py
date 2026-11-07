from dataclasses import dataclass, field
from typing import List, Dict
import numpy as np


@dataclass
class FlexibleMachine:
    machine_id: str
    appliance_class: int
    label: str
    power_w: float
    daily_runtime_slots: int  # Jumlah slot 15-menit yang harus dijalankan
    deadline_slot: int        # Harus selesai sebelum slot ini (default 68 = jam 17:00)
    min_continuous_slots: int = 1  # Minimal run berturut-turut sebelum OFF
    cooldown_slots: int = 2        # Minimal OFF setelah ON sebelum bisa ON lagi

    # State runtime
    remaining_slots: int = field(init=False)
    current_state: int = field(default=0, init=False)
    consecutive_on: int = field(default=0, init=False)
    consecutive_off: int = field(default=999, init=False)

    def __post_init__(self) -> None:
        self.remaining_slots = self.daily_runtime_slots

    def can_turn_on(self) -> bool:
        return (
            self.remaining_slots > 0
            and self.consecutive_off >= self.cooldown_slots
        )

    def step(self, action: int) -> None:
        """Update internal state setelah satu slot dieksekusi."""
        if action == 1 and self.can_turn_on():
            self.current_state = 1
            self.remaining_slots = max(0, self.remaining_slots - 1)
            self.consecutive_on += 1
            self.consecutive_off = 0
        else:
            self.current_state = 0
            self.consecutive_on = 0
            self.consecutive_off += 1

    @property
    def is_deadline_violated(self) -> bool:
        return self.remaining_slots > 0

    def reset(self) -> None:
        self.remaining_slots = self.daily_runtime_slots
        self.current_state = 0
        self.consecutive_on = 0
        self.consecutive_off = 999


class UMKMDigitalTwin:
    """
    Model digital twin UMKM: mengelola antrean pekerjaan mesin fleksibel
    untuk optimasi jadwal dalam satu hari kerja (00:00–23:45).
    """

    # Template mesin tipikal per tipe UMKM (class: FlexibleMachine default params)
    MACHINE_TEMPLATES: List[Dict] = [
        {
            "machine_id": "boiler-setrika-01",
            "appliance_class": 3,
            "label": "Setrika Pemanas Uap",
            "power_w": 1500.0,
            "daily_runtime_slots": 20,  # 5 jam
            "deadline_slot": 68,
        },
        {
            "machine_id": "drum-pengering-01",
            "appliance_class": 4,
            "label": "Drum Pengering Laundry",
            "power_w": 1200.0,
            "daily_runtime_slots": 16,  # 4 jam
            "deadline_slot": 68,
        },
        {
            "machine_id": "kompresor-sablon-01",
            "appliance_class": 2,
            "label": "Kompresor Sablon",
            "power_w": 1500.0,
            "daily_runtime_slots": 12,  # 3 jam
            "deadline_slot": 68,
        },
        {
            "machine_id": "oven-preheating-01",
            "appliance_class": 3,
            "label": "Oven Pre-heating Konveksi",
            "power_w": 2000.0,
            "daily_runtime_slots": 8,  # 2 jam
            "deadline_slot": 60,
        },
    ]

    def __init__(self, machines: List[FlexibleMachine] | None = None) -> None:
        if machines is not None:
            self.machines = machines
        else:
            self.machines = [FlexibleMachine(**t) for t in self.MACHINE_TEMPLATES]

    @property
    def n_machines(self) -> int:
        return len(self.machines)

    def reset(self) -> None:
        for m in self.machines:
            m.reset()

    def step(self, actions: np.ndarray) -> None:
        for i, machine in enumerate(self.machines):
            machine.step(int(actions[i]))

    def get_total_load_w(self) -> float:
        return sum(m.power_w * m.current_state for m in self.machines)

    def get_state_vector(self) -> np.ndarray:
        """Remaining slots untuk setiap mesin, dinormalisasi ke [0, 1]."""
        return np.array(
            [m.remaining_slots / max(m.daily_runtime_slots, 1) for m in self.machines],
            dtype=np.float32,
        )

    def get_action_mask(self) -> np.ndarray:
        """1 = boleh dinyalakan, 0 = tidak boleh (quota penuh atau cooldown aktif)."""
        return np.array([1 if m.can_turn_on() else 0 for m in self.machines], dtype=np.int8)
