"""
Pola pesanan UMKM → skala runtime harian mesin.

Beban mesin UMKM tidak sama setiap hari: Sabtu biasanya lebih ramai, Minggu
sering libur, dan pesanan melonjak menjelang Lebaran atau tahun ajaran baru.
``OrderBook`` menghasilkan faktor skala per tanggal lalu mengubah
``daily_runtime_minutes`` setiap job.

Faktor = faktor_mingguan(hari) × faktor_musiman(tanggal), KECUALI bila riwayat
pemilik (CSV) memuat tanggal itu persis — maka dipakai pesanan tanggal itu
dibagi rata-rata pesanan hari buka.

PENTING: nilai default di bawah adalah ASUMSI umum UMKM konveksi/sablon/laundry
di Jawa Tengah, BELUM divalidasi dengan data pesanan nyata. Isi CSV riwayat
pemilik (lihat ``docs/DIGITAL_TWIN.md``) agar pola dipelajari dari data.

Kode generik: job cukup memiliki atribut ``daily_runtime_minutes``. Job
pydantic disalin dengan ``model_copy(update=...)``, dataclass dengan
``dataclasses.replace``; selain itu ``copy.copy`` + setattr.
"""
from __future__ import annotations

import copy
import csv
import dataclasses
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

# 0=Senin … 6=Minggu (date.weekday()).
DEFAULT_WEEKDAY_FACTORS: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0, 0.9, 1.2, 0.0)
WEEKDAY_NAMES = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")

# Perkiraan 1 Syawal (Idulfitri) versi pemerintah RI. Tahun mendatang adalah
# perkiraan hisab dan bisa bergeser ±1 hari — perbarui bila sidang isbat beda.
IDUL_FITRI_DATES: dict[int, date] = {
    2023: date(2023, 4, 22),
    2024: date(2024, 4, 10),
    2025: date(2025, 3, 31),
    2026: date(2026, 3, 20),
    2027: date(2027, 3, 10),
    2028: date(2028, 2, 27),
    2029: date(2029, 2, 14),
    2030: date(2030, 2, 4),
}

RUNTIME_ROUND_MINUTES = 15  # selaras slot 15 menit


@dataclass(frozen=True)
class SeasonalWindow:
    """Rentang tanggal [start, end] (inklusif) dengan faktor pengali."""

    name: str
    start: date
    end: date
    factor: float

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def default_seasonal_windows(year: int) -> list[SeasonalWindow]:
    """Jendela musiman default untuk satu tahun (asumsi, belum divalidasi)."""
    windows: list[SeasonalWindow] = []
    lebaran = IDUL_FITRI_DATES.get(year)
    if lebaran is not None:
        windows.append(SeasonalWindow("Menjelang Lebaran", lebaran - timedelta(days=30),
                                      lebaran - timedelta(days=4), 1.4))
        windows.append(SeasonalWindow("Libur Lebaran", lebaran - timedelta(days=3),
                                      lebaran + timedelta(days=5), 0.0))
    # Tahun ajaran baru (pertengahan Juli): seragam, sablon, perlengkapan sekolah.
    windows.append(SeasonalWindow("Menjelang tahun ajaran baru", date(year, 6, 10), date(year, 7, 15), 1.25))
    # Akhir tahun: pesanan seragam/kaos acara & cuti bersama Natal-Tahun Baru.
    windows.append(SeasonalWindow("Akhir tahun", date(year, 12, 1), date(year, 12, 23), 1.1))
    return windows


def _round_runtime(minutes: float) -> int:
    if minutes <= 0:
        return 0
    return int(max(RUNTIME_ROUND_MINUTES, round(minutes / RUNTIME_ROUND_MINUTES) * RUNTIME_ROUND_MINUTES))


def _copy_with_runtime(job: Any, minutes: int) -> Any:
    if hasattr(job, "model_copy"):
        return job.model_copy(update={"daily_runtime_minutes": minutes})
    if dataclasses.is_dataclass(job) and not isinstance(job, type):
        return dataclasses.replace(job, daily_runtime_minutes=minutes)
    if isinstance(job, dict):
        out = dict(job)
        out["daily_runtime_minutes"] = minutes
        return out
    out = copy.copy(job)
    setattr(out, "daily_runtime_minutes", minutes)
    return out


def _get_runtime(job: Any) -> float:
    if isinstance(job, dict):
        return float(job["daily_runtime_minutes"])
    return float(getattr(job, "daily_runtime_minutes"))


def _window_cap_minutes(job: Any) -> Optional[int]:
    """Batas runtime dari jendela kerja job (earliest_hour..deadline_hour) bila ada."""
    get = job.get if isinstance(job, dict) else lambda k, d=None: getattr(job, k, d)
    earliest, deadline = get("earliest_hour", None), get("deadline_hour", None)
    if earliest is None or deadline is None:
        return None
    span = (int(deadline) - int(earliest)) * 60
    return span if span > 0 else None


@dataclass
class OrderBook:
    """
    Pola pesanan mingguan + musiman.

    Args:
        weekday_factors: 7 faktor (Senin..Minggu).
        seasonal_windows: daftar SeasonalWindow tambahan/pengganti. ``None``
            → jendela default dibuat per tahun secara otomatis.
        daily_overrides: faktor per tanggal (biasanya dari CSV riwayat atau
            pesanan yang sudah dikonfirmasi).
        max_factor: batas atas faktor gabungan.
        source: "default" | "csv" (untuk ditampilkan/diaudit).
    """

    weekday_factors: Sequence[float] = DEFAULT_WEEKDAY_FACTORS
    seasonal_windows: Optional[list[SeasonalWindow]] = None
    daily_overrides: dict[date, float] = field(default_factory=dict)
    max_factor: float = 2.0
    source: str = "default"

    def __post_init__(self) -> None:
        if len(self.weekday_factors) != 7:
            raise ValueError("weekday_factors harus berisi 7 nilai (Senin..Minggu)")
        self.weekday_factors = tuple(max(0.0, float(f)) for f in self.weekday_factors)

    # ── faktor ─────────────────────────────────────────────────────────────
    def _windows_for(self, day: date) -> list[SeasonalWindow]:
        if self.seasonal_windows is not None:
            return self.seasonal_windows
        # Jendela tahun sebelumnya/berikutnya bisa menyeberang tahun.
        return default_seasonal_windows(day.year) + default_seasonal_windows(day.year + 1)

    def seasonal_factor(self, day: date) -> tuple[float, list[str]]:
        factor, names = 1.0, []
        for w in self._windows_for(day):
            if w.contains(day):
                factor *= w.factor
                names.append(w.name)
        return factor, names

    def factor_for(self, day: date) -> float:
        if day in self.daily_overrides:
            return min(max(self.daily_overrides[day], 0.0), self.max_factor)
        seasonal, _ = self.seasonal_factor(day)
        return min(self.weekday_factors[day.weekday()] * seasonal, self.max_factor)

    def explain(self, day: date) -> str:
        """Alasan faktor untuk ditampilkan ke pemilik (Bahasa Indonesia)."""
        f = self.factor_for(day)
        if day in self.daily_overrides:
            return f"{WEEKDAY_NAMES[day.weekday()]}: dari catatan pesanan pemilik, beban ×{f:.2f}"
        wd = self.weekday_factors[day.weekday()]
        _, names = self.seasonal_factor(day)
        parts = [f"{WEEKDAY_NAMES[day.weekday()]} ×{wd:.2f}"]
        parts += names
        if f == 0:
            return f"{', '.join(parts)} → libur (mesin tidak dijadwalkan)"
        return f"{', '.join(parts)} → beban ×{f:.2f}"

    # ── kontrak ────────────────────────────────────────────────────────────
    def jobs_for(self, day: date, base_jobs: Iterable[Any]) -> list:
        """
        Salinan ``base_jobs`` dengan ``daily_runtime_minutes`` diskalakan.

        Runtime dibulatkan ke kelipatan 15 menit, minimal 15 menit bila
        faktor > 0, 0 bila libur, dan tidak melebihi jendela kerja job
        (deadline_hour − earliest_hour) bila atribut itu ada. Jumlah dan urutan
        job selalu sama dengan input (penting untuk agen RL berdimensi tetap).
        """
        f = self.factor_for(day)
        out = []
        for job in base_jobs:
            minutes = _round_runtime(_get_runtime(job) * f)
            cap = _window_cap_minutes(job)
            if cap is not None:
                minutes = min(minutes, cap)
            out.append(_copy_with_runtime(job, minutes))
        return out

    # ── dari riwayat pesanan ───────────────────────────────────────────────
    @classmethod
    def from_history(
        cls,
        rows: Iterable[tuple[date, float]],
        min_samples_per_weekday: int = 2,
        **kwargs,
    ) -> "OrderBook":
        """
        Pelajari pola dari riwayat ``(tanggal, jumlah_pesanan)``.

        - Rata-rata hari buka (pesanan > 0) menjadi acuan faktor 1,0.
        - Faktor mingguan dipelajari bila tiap hari punya ≥
          ``min_samples_per_weekday`` sampel; selain itu default dipakai.
        - Setiap tanggal di riwayat menjadi override persis (berguna untuk
          pesanan yang sudah dikonfirmasi di masa depan).
        - Jendela musiman default tetap dipakai untuk tanggal di luar riwayat
          (riwayat pendek belum cukup untuk mempelajari musim).
        """
        data: dict[date, float] = {}
        for d, n in rows:
            data[d] = data.get(d, 0.0) + max(float(n), 0.0)
        if not data:
            return cls(**kwargs)
        open_vals = [v for v in data.values() if v > 0]
        mean_open = sum(open_vals) / len(open_vals) if open_vals else 0.0
        if mean_open <= 0:
            return cls(daily_overrides={d: 0.0 for d in data}, source="csv", **kwargs)

        by_wd: dict[int, list[float]] = {i: [] for i in range(7)}
        for d, v in data.items():
            by_wd[d.weekday()].append(v / mean_open)
        weekday = list(kwargs.pop("weekday_factors", DEFAULT_WEEKDAY_FACTORS))
        for wd, vals in by_wd.items():
            if len(vals) >= min_samples_per_weekday:
                weekday[wd] = sum(vals) / len(vals)

        overrides = {d: v / mean_open for d, v in data.items()}
        return cls(weekday_factors=weekday, daily_overrides=overrides, source="csv", **kwargs)

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs) -> "OrderBook":
        """
        Baca CSV riwayat pesanan. Kolom (header tidak peka huruf besar):
        tanggal|date (YYYY-MM-DD) dan pesanan|orders|jumlah|jumlah_pesanan.
        Baris dengan tanggal yang sama dijumlahkan.
        """
        date_keys = ("tanggal", "date", "tgl")
        qty_keys = ("pesanan", "orders", "jumlah", "jumlah_pesanan", "qty")
        rows: list[tuple[date, float]] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ValueError("CSV pesanan kosong")
            cols = {c.strip().lower(): c for c in reader.fieldnames}
            dcol = next((cols[k] for k in date_keys if k in cols), None)
            qcol = next((cols[k] for k in qty_keys if k in cols), None)
            if dcol is None or qcol is None:
                raise ValueError(
                    "CSV pesanan butuh kolom 'tanggal' dan 'pesanan' "
                    f"(ditemukan: {', '.join(reader.fieldnames)})"
                )
            for i, row in enumerate(reader, start=2):
                raw_d, raw_q = (row.get(dcol) or "").strip(), (row.get(qcol) or "").strip()
                if not raw_d:
                    continue
                try:
                    d = date.fromisoformat(raw_d[:10])
                    q = float(raw_q.replace(",", ".")) if raw_q else 0.0
                except ValueError as exc:
                    raise ValueError(f"Baris {i} CSV pesanan tidak valid: {exc}") from exc
                if math.isnan(q):
                    continue
                rows.append((d, q))
        return cls.from_history(rows, **kwargs)
