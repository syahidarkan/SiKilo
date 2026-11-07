"""
Unduh & cache data cuaca per jam NASA POWER agar demo WASKITA bisa offline.

Default: lokasi pabrik di settings (Sukoharjo, -7.68, 110.83) dan dua tahun
lengkap terakhir. File ditulis ke settings.nasa_power_cache_dir
(default backend/data/nasa_power/nasa_power_<lat>_<lon>_<tahun>.json, ±150 KB/tahun).

Usage (dari folder backend):
    python scripts/fetch_nasa_power.py
    python scripts/fetch_nasa_power.py --years 2024 2025 --lat -7.68 --lon 110.83 --force
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.digital_twin.weather import WeatherProvider  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    last_complete = date.today().year - 1
    parser = argparse.ArgumentParser(description="Unduh cache NASA POWER untuk tiruan digital WASKITA")
    parser.add_argument("--lat", type=float, default=settings.site_latitude)
    parser.add_argument("--lon", type=float, default=settings.site_longitude)
    parser.add_argument("--years", type=int, nargs="+", default=[last_complete - 1, last_complete])
    parser.add_argument("--cache-dir", default=None, help="default: settings.nasa_power_cache_dir")
    parser.add_argument("--force", action="store_true", help="unduh ulang walau cache sudah ada")
    args = parser.parse_args(argv)

    provider = WeatherProvider(cache_dir=args.cache_dir, allow_network=True)
    failures = 0
    for year in args.years:
        if year > last_complete:
            print(f"[lewati] {year}: tahun belum lengkap; WASKITA memakai {last_complete} sebagai tahun tipikal")
            continue
        path = provider.cache_path(args.lat, args.lon, year)
        if path.exists() and not args.force:
            print(f"[ada]    {year}: {path}")
            continue
        try:
            data = provider.fetch_year(args.lat, args.lon, year)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[gagal]  {year}: {exc}")
            continue
        days = data["days"]
        complete = sum(1 for v in days.values() if all(x is not None for x in v["ghi"]))
        ghi_kwh = [sum(v["ghi"]) / 1000.0 for v in days.values() if all(x is not None for x in v["ghi"])]
        mean_ghi = sum(ghi_kwh) / len(ghi_kwh) if ghi_kwh else float("nan")
        size_kb = path.stat().st_size / 1024
        print(
            f"[ok]     {year}: {len(days)} hari ({complete} lengkap), rata-rata GHI {mean_ghi:.2f} kWh/m²/hari, "
            f"{size_kb:.0f} KB → {path}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
