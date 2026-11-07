"""
Data cuaca per jam untuk tiruan digital WASKITA.

Sumber utama: NASA POWER hourly API (komunitas RE, waktu LST) dengan
parameter ``ALLSKY_SFC_SW_DWN`` (GHI semua-langit, Wh/m² per jam = rata-rata
W/m² selama jam tersebut) dan ``T2M`` (suhu udara 2 m, °C).

- Data diambil per (lat, lon, tahun) satu kali lalu disimpan sebagai JSON di
  ``settings.nasa_power_cache_dir`` sehingga demo bisa berjalan offline.
- Untuk tanggal di masa depan atau tahun berjalan (belum lengkap), dipakai
  tanggal & bulan yang sama dari tahun lengkap terakhir sebagai "hari tipikal".
- Tidak ada panggilan jaringan saat modul di-import. Saat pytest berjalan
  (variabel ``PYTEST_CURRENT_TEST`` ada), unduhan dimatikan kecuali provider
  dibuat dengan ``allow_network=True`` secara eksplisit (dan fungsi HTTP-nya
  di-mock oleh tes).

Bila data tidak tersedia, fungsi di sini mengembalikan ``None`` dan
``solar_engine`` memakai fallback clear-sky × indeks kecerahan.

Perlindungan sumber daya (koordinat datang dari input pengguna):
- unduhan hanya untuk koordinat di kotak wilayah Indonesia
  (``settings.weather_lat_*``/``weather_lon_*``); di luar itu → fallback;
- kunci per (lokasi, tahun): unduhan satu lokasi tidak memblokir lokasi lain
  (tidak ada lock global selama I/O jaringan), dan permintaan bersamaan untuk
  lokasi yang sama hanya mengunduh sekali;
- cache memori LRU (``settings.weather_memory_cache_max`` entri);
- unduhan lokasi BARU dibatasi ``settings.weather_max_new_fetches_per_hour``
  per proses.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

NASA_POWER_HOURLY_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
NASA_PARAMETERS = ("ALLSKY_SFC_SW_DWN", "T2M")
NASA_FILL_VALUE = -999.0
# Setelah unduhan gagal, jangan coba lagi untuk kunci yang sama selama ini (detik).
FAILURE_BACKOFF_S = 600.0

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_backend_path(p: str | os.PathLike) -> Path:
    """Path relatif di settings dianggap relatif terhadap folder backend."""
    path = Path(p)
    return path if path.is_absolute() else BACKEND_ROOT / path


@dataclass
class DailyWeather:
    """Cuaca satu hari, 24 nilai per jam (indeks h = rata-rata selang [h, h+1))."""

    requested_date: date
    source_date: date          # tanggal yang benar-benar dipakai (bisa tahun tipikal)
    ghi_hourly: np.ndarray     # (24,) W/m²
    t2m_hourly: np.ndarray     # (24,) °C
    source: str = "nasa_power"

    @property
    def is_typical_year(self) -> bool:
        return self.source_date != self.requested_date


def _same_day_in_year(d: date, year: int) -> date:
    """Tanggal & bulan sama di tahun lain; 29 Feb → 28 Feb bila bukan kabisat."""
    try:
        return d.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def resolve_source_date(target_date: date, today: Optional[date] = None) -> date:
    """
    Tanggal data cuaca yang dipakai untuk ``target_date``.

    Tahun yang sudah lewat dipakai apa adanya. Tahun berjalan atau masa depan
    (data NASA belum lengkap) dipetakan ke tahun lengkap terakhir.
    """
    today = today or date.today()
    last_complete_year = today.year - 1
    if target_date.year <= last_complete_year:
        return target_date
    return _same_day_in_year(target_date, last_complete_year)


def _key(lat: float, lon: float, year: int) -> str:
    return f"{lat:.2f}_{lon:.2f}_{year}"


def _default_http_get_json(url: str, timeout_s: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "WASKITA-digital-twin/0.2"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (URL tetap, https)
        return json.loads(resp.read().decode("utf-8"))


def build_request_url(lat: float, lon: float, year: int) -> str:
    query = {
        "parameters": ",".join(NASA_PARAMETERS),
        "community": "RE",
        "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}",
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON",
        "time-standard": "LST",
    }
    return f"{NASA_POWER_HOURLY_URL}?{urllib.parse.urlencode(query)}"


def parse_power_response(payload: dict, lat: float, lon: float, year: int) -> dict:
    """
    Ubah respons NASA POWER (kunci ``YYYYMMDDHH``) menjadi format cache ringkas:
    ``{"days": {"YYYY-MM-DD": {"ghi": [24], "t2m": [24]}}, ...}``.
    Nilai isian (-999) disimpan sebagai ``null``.
    """
    params = payload.get("properties", {}).get("parameter", {})
    ghi_raw = params.get("ALLSKY_SFC_SW_DWN")
    t2m_raw = params.get("T2M")
    if not ghi_raw or not t2m_raw:
        raise ValueError("Respons NASA POWER tidak berisi ALLSKY_SFC_SW_DWN/T2M")

    fill = payload.get("header", {}).get("fill_value", NASA_FILL_VALUE)
    days: dict[str, dict[str, list]] = {}
    for stamp, ghi in ghi_raw.items():
        if len(stamp) != 10:
            continue
        day_key = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        hour = int(stamp[8:10])
        if not 0 <= hour <= 23:
            continue
        entry = days.setdefault(day_key, {"ghi": [None] * 24, "t2m": [None] * 24})
        t = t2m_raw.get(stamp)
        entry["ghi"][hour] = None if ghi is None or ghi <= fill else round(float(ghi), 2)
        entry["t2m"][hour] = None if t is None or t <= fill else round(float(t), 2)

    if not days:
        raise ValueError("Respons NASA POWER kosong")
    return {
        "source": "NASA POWER hourly API v2 (community=RE, time-standard=LST)",
        "parameters": {"ghi": "ALLSKY_SFC_SW_DWN [Wh/m² per jam ≈ W/m² rata-rata]",
                       "t2m": "T2M [°C]"},
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "year": year,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": dict(sorted(days.items())),
    }


class WeatherProvider:
    """Pembaca cuaca per jam NASA POWER dengan cache JSON per tahun."""

    def __init__(
        self,
        cache_dir: str | os.PathLike | None = None,
        allow_network: Optional[bool] = None,
        timeout_s: Optional[float] = None,
        http_get_json: Optional[Callable[[str, float], dict]] = None,
    ) -> None:
        self.cache_dir = resolve_backend_path(cache_dir or settings.nasa_power_cache_dir)
        self._allow_network_override = allow_network
        self.timeout_s = timeout_s if timeout_s is not None else settings.nasa_power_timeout_s
        self._http_get_json = http_get_json or _default_http_get_json
        self._years: "OrderedDict[str, dict]" = OrderedDict()
        self._failed_at: dict[str, float] = {}
        self._lock = threading.Lock()              # hanya melindungi struktur data (tanpa I/O)
        self._key_locks: dict[str, threading.Lock] = {}
        self._fetch_times: deque[float] = deque()

    @staticmethod
    def in_service_area(lat: float, lon: float) -> bool:
        return (
            settings.weather_lat_min <= float(lat) <= settings.weather_lat_max
            and settings.weather_lon_min <= float(lon) <= settings.weather_lon_max
        )

    def _remember(self, key: str, data: dict) -> None:
        with self._lock:
            self._years[key] = data
            self._years.move_to_end(key)
            while len(self._years) > max(int(settings.weather_memory_cache_max), 1):
                self._years.popitem(last=False)

    def _take_fetch_slot(self) -> bool:
        """Kuota unduhan lokasi baru per jam (per proses)."""
        now = time.monotonic()
        with self._lock:
            while self._fetch_times and now - self._fetch_times[0] > 3600.0:
                self._fetch_times.popleft()
            if len(self._fetch_times) >= max(int(settings.weather_max_new_fetches_per_hour), 0):
                return False
            self._fetch_times.append(now)
            return True

    # ── kebijakan jaringan ─────────────────────────────────────────────────
    @property
    def network_allowed(self) -> bool:
        if self._allow_network_override is not None:
            return self._allow_network_override
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        return bool(settings.use_nasa_power and settings.nasa_power_allow_network)

    # ── cache ──────────────────────────────────────────────────────────────
    def cache_path(self, lat: float, lon: float, year: int) -> Path:
        return self.cache_dir / f"nasa_power_{_key(lat, lon, year)}.json"

    def _read_cache(self, lat: float, lon: float, year: int) -> Optional[dict]:
        path = self.cache_path(lat, lon, year)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if "days" not in data:
                raise ValueError("format cache tidak dikenal")
            return data
        except (OSError, ValueError) as exc:
            logger.warning("Cache NASA POWER rusak (%s): %s", path, exc)
            return None

    def _write_cache(self, data: dict, lat: float, lon: float, year: int) -> Path:
        path = self.cache_path(lat, lon, year)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, separators=(",", ":"))
        os.replace(tmp, path)
        return path

    # ── unduhan ────────────────────────────────────────────────────────────
    def fetch_year(self, lat: float, lon: float, year: int, save: bool = True) -> dict:
        """Unduh satu tahun penuh dari NASA POWER (selalu ke jaringan). Bisa raise."""
        url = build_request_url(lat, lon, year)
        logger.info("Mengunduh NASA POWER %s", url)
        payload = self._http_get_json(url, self.timeout_s)
        data = parse_power_response(payload, lat, lon, year)
        if save:
            self._write_cache(data, lat, lon, year)
        return data

    def load_year(self, lat: float, lon: float, year: int) -> Optional[dict]:
        """Data satu tahun dari memori → cache disk → jaringan (bila diizinkan)."""
        key = _key(lat, lon, year)
        with self._lock:
            hit = self._years.get(key)
            if hit is not None:
                self._years.move_to_end(key)
                return hit
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        # I/O (baca file / unduh) di luar lock global; lock per kunci mencegah unduhan ganda.
        with key_lock:
            with self._lock:
                hit = self._years.get(key)
            if hit is not None:
                return hit
            data = self._read_cache(lat, lon, year)
            if data is None and self.network_allowed and self.in_service_area(lat, lon):
                failed = self._failed_at.get(key)
                if failed is None or time.monotonic() - failed > FAILURE_BACKOFF_S:
                    if not self._take_fetch_slot():
                        logger.warning("Kuota unduhan NASA POWER per jam habis; %s memakai fallback.", key)
                    else:
                        try:
                            data = self.fetch_year(lat, lon, year)
                        except Exception as exc:  # jaringan/format: jatuh ke fallback
                            with self._lock:
                                self._failed_at[key] = time.monotonic()
                            logger.warning("NASA POWER tidak tersedia (%s): %s", key, exc)
                            data = None
            if data is not None:
                self._remember(key, data)
        with self._lock:
            if not key_lock.locked():
                self._key_locks.pop(key, None)
        return data

    # ── API utama ──────────────────────────────────────────────────────────
    def get_day(
        self,
        target_date: date,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        today: Optional[date] = None,
    ) -> Optional[DailyWeather]:
        """
        Cuaca per jam untuk ``target_date`` atau ``None`` bila tidak tersedia.
        Jika data tahun yang diminta tidak lengkap untuk hari itu, dicoba satu
        tahun sebelumnya (tanggal sama) sebagai hari tipikal.
        """
        lat = settings.site_latitude if lat is None else float(lat)
        lon = settings.site_longitude if lon is None else float(lon)
        primary = resolve_source_date(target_date, today)
        for candidate in (primary, _same_day_in_year(primary, primary.year - 1)):
            data = self.load_year(lat, lon, candidate.year)
            if data is None:
                continue
            entry = data["days"].get(candidate.isoformat())
            if not entry:
                continue
            ghi, t2m = entry.get("ghi"), entry.get("t2m")
            if not ghi or not t2m or any(v is None for v in ghi) or len(ghi) != 24:
                continue
            t_arr = np.array([np.nan if v is None else v for v in t2m], dtype=np.float64)
            if np.all(np.isnan(t_arr)):
                continue
            if np.any(np.isnan(t_arr)):
                idx = np.arange(24)
                ok = ~np.isnan(t_arr)
                t_arr = np.interp(idx, idx[ok], t_arr[ok])
            return DailyWeather(
                requested_date=target_date,
                source_date=candidate,
                ghi_hourly=np.clip(np.array(ghi, dtype=np.float64), 0.0, None),
                t2m_hourly=t_arr,
                source="nasa_power",
            )
        return None


_provider: Optional[WeatherProvider] = None


def get_weather_provider() -> WeatherProvider:
    global _provider
    if _provider is None:
        _provider = WeatherProvider()
    return _provider
