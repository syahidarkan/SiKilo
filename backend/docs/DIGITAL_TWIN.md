# Tiruan digital WASKITA

Tiruan digital (digital twin) memodelkan satu hari operasional UMKM dalam
96 slot × 15 menit: produksi PLTS atap, beban mesin menurut pola pesanan,
baterai opsional, dan impor listrik PLN. Modul ini dipakai oleh agen
penjadwal (`app/agent/`), sizing PLTS (`app/sizing/`), dan skrip validasi.

> **Status jujur:** model surya, baterai, dan pola pesanan **belum divalidasi
> dengan data lapangan UMKM**. Pipeline validasi sudah ada
> (`scripts/validate_twin.py`) dan baru diuji dengan data **contoh sintetis**
> (`source: "example"`). Angka akurasi hanya boleh diklaim setelah pipeline
> dijalankan dengan tagihan/meteran nyata.

| File | Isi |
| --- | --- |
| `app/digital_twin/weather.py` | Cuaca per jam NASA POWER + cache JSON |
| `app/digital_twin/solar_engine.py` | Kurva daya AC PLTS 96 slot |
| `app/digital_twin/battery.py` | Model baterai (SoC, efisiensi, batas daya) |
| `app/digital_twin/orders.py` | Pola pesanan mingguan/musiman → runtime mesin |
| `scripts/fetch_nasa_power.py` | Unduh cache cuaca untuk demo offline |
| `scripts/validate_twin.py` | Replay data nyata vs simulasi → `twin_validation.json` |
| `docs/examples/` | Contoh input SINTETIS (profil, meteran, tagihan, pesanan) |

## 1. Cuaca (`weather.py`)

- Sumber: [NASA POWER hourly API](https://power.larc.nasa.gov/api/temporal/hourly/point),
  `community=RE`, `time-standard=LST`, parameter `ALLSKY_SFC_SW_DWN`
  (GHI semua-langit, Wh/m² per jam = rata-rata W/m² selama jam itu) dan `T2M`
  (suhu udara 2 m, °C). Nilai jam `h` dianggap rata-rata selang `[h, h+1)`.
- Satu permintaan per (lat, lon, tahun); disimpan di
  `settings.nasa_power_cache_dir` (default `backend/data/nasa_power/`) sebagai
  `nasa_power_<lat>_<lon>_<tahun>.json` (~110 KB/tahun). Nilai isian `-999`
  disimpan sebagai `null`; hari dengan GHI tidak lengkap dilewati.
- **Hari tipikal:** tanggal di tahun berjalan atau masa depan memakai tanggal &
  bulan yang sama dari tahun lengkap terakhir (`today.year − 1`; 29 Feb → 28 Feb).
  Bila hari itu tidak ada/lengkap, dicoba satu tahun sebelumnya.
- **Jaringan:** tidak pernah dipanggil saat import. Saat runtime hanya bila
  `use_nasa_power` dan `nasa_power_allow_network` bernilai True. Gagal unduh →
  tidak dicoba lagi untuk kunci yang sama selama 10 menit (agar sizing 365 hari
  tidak menunggu timeout berulang). Di bawah pytest unduhan selalu mati kecuali
  provider dibuat dengan `allow_network=True` dan HTTP-nya di-mock.

### Cache offline untuk demo

```bash
cd backend
python scripts/fetch_nasa_power.py                 # default: Sukoharjo, 2 tahun lengkap terakhir
python scripts/fetch_nasa_power.py --years 2023 2024 2025 --lat -7.68 --lon 110.83 --force
```

Cache Sukoharjo 2024 dan 2025 sudah diunduh pada 7 Nov 2026 ke
`backend/data/nasa_power/` (2 × ~108 KB) dan aman di-commit.
Rata-rata GHI hasil unduhan: 5,04 kWh/m²/hari (2024) dan 4,76 kWh/m²/hari (2025).

## 2. Mesin surya (`solar_engine.py`)

Kontrak: `get_solar_engine().simulate_day(target_date, kwp, lat=None, lon=None)`
→ `np.ndarray(96,)` Watt AC, dan `SolarEngine.last_source ∈ {"nasa_power",
"clearsky_scaled"}` (+ `last_source_date`). `simulate_day_detailed()` memberi
GHI, POA, suhu udara, suhu sel per slot untuk 1 kWp.

Langkah per hari:

1. **Irradiansi.** Data NASA → per slot: `GHI_slot = GHI_clear-sky,slot × kt_jam`,
   dengan `kt_jam = GHI_NASA,jam / rata-rata clear-sky jam itu` (dibatasi ≤ 1,3).
   Energi per jam sama dengan data NASA (diuji pada data 2025: selisih total
   0,003 %) sementara bentuk di dalam jam tetap halus. Clear-sky: pvlib Ineichen
   (turbiditas Linke bawaan pvlib).
   **Fallback** (tanpa data): `GHI = clear-sky × settings.clearness_index_fallback`
   (default 0,75) dan suhu sinusoidal 24–33 °C; `last_source = "clearsky_scaled"`.
2. **GHI → POA (bidang panel).** Penyederhanaan yang disengaja: dekomposisi Erbs
   (GHI → DNI + DHI) lalu transposisi isotropik untuk kemiringan
   `pv_tilt_deg` (default 10°) menghadap `pv_azimuth_deg` (default 0° = utara),
   albedo 0,2. Di 7,7° LS sinar matahari hampir tegak sehingga POA atap miring
   kecil hanya berbeda beberapa persen dari GHI; `pv_tilt_deg = 0` membuat
   POA = GHI. Bayangan, orientasi atap lain, dan model anisotropik tidak dimodelkan.
3. **Suhu sel.** `pvlib.temperature.faiman` (u0 = 25, u1 = 6,84) dengan angin
   asumsi `pv_wind_speed_ms` (default 1 m/s; NASA `T2M` sebagai suhu udara).
4. **Daya.**
   `P_ac = kWp × POA/1000 × (1 + γ·(T_sel − 25)) × (1 − rugi_sistem) × η_inverter`,
   γ = `pv_temp_coeff_per_c` (−0,4 %/°C), rugi sistem `pv_system_losses_frac`
   (14 %: kabel, debu, mismatch, toleransi), `INVERTER_EFF` = 0,96, dibatasi
   1 kW AC per kWp.

Kinerja: hasil per 1 kWp di-cache per (tanggal, lat, lon); pada cache miss
dihitung satu bulan sekaligus secara tervektorisasi (simulasi setahun ±2 detik).

Keluaran model (bukan pengukuran): dengan cuaca NASA 2025 di Sukoharjo,
yield ≈ 1.327 kWh/kWp/tahun (simulasi 365 hari; GHI 1.737 kWh/m² →
performance ratio ≈ 0,76 terhadap GHI horizontal).
Angka ini perlu dicek dengan data produksi inverter PLTS atap nyata di
Solo Raya sebelum dipakai sebagai klaim.

### Konfigurasi (`app/core/config.py`)

| Field | Default | Arti |
| --- | --- | --- |
| `use_nasa_power` | True | pakai data NASA (False → selalu clear-sky) |
| `nasa_power_allow_network` | True | boleh unduh saat runtime (False → hanya cache) |
| `nasa_power_cache_dir` | `data/nasa_power` | relatif ke folder backend |
| `nasa_power_timeout_s` | 20 | timeout HTTP |
| `clearness_index_fallback` | 0,75 | GHI aktual/clear-sky untuk fallback |
| `pv_tilt_deg`, `pv_azimuth_deg` | 10, 0 | geometri panel |
| `pv_system_losses_frac` | 0,14 | rugi sistem selain inverter |
| `pv_temp_coeff_per_c` | −0,004 | koefisien suhu modul |
| `pv_wind_speed_ms` | 1,0 | angin untuk model suhu sel |

## 3. Baterai (`battery.py`)

`Battery(capacity_wh, max_charge_w, max_discharge_w, efficiency_rt=0.90,
soc_min_frac=0.20, soc_init_frac=0.50)`:

- `step(net_w, dt_h=0.25) -> (grid_import_wh, curtail_wh)`, `net_w = PV − beban`.
  Surplus mengisi baterai (dibatasi `max_charge_w` dan ruang kosong), sisanya
  curtailment (tidak dikreditkan, Permen ESDM 2/2024). Defisit ditutup baterai
  (dibatasi `max_discharge_w` dan SoC minimum), sisanya impor PLN.
- Efisiensi round-trip dibagi rata: η_charge = η_discharge = √η_rt.
  Batas daya diukur di sisi AC.
- SoC tidak pernah di bawah `soc_min_frac × kapasitas` (SoC awal di bawahnya
  dinaikkan ke batas).
- Tambahan: `reset()`, `soc_wh`, `run(net_series)` → deret impor/curtail/SoC,
  `Battery.from_kwh(kwh, c_rate=0.5)`.
- Tidak memodelkan degradasi, suhu, maupun kurva tegangan.

## 4. Pola pesanan (`orders.py`)

`OrderBook().jobs_for(day, base_jobs)` mengembalikan salinan job dengan
`daily_runtime_minutes` dikali faktor hari itu (dibulatkan ke 15 menit,
minimal 15 bila faktor > 0, 0 bila libur, dibatasi jendela
`deadline_hour − earliest_hour` bila ada). Jumlah & urutan job tetap.
Job boleh pydantic (`model_copy`), dataclass (`dataclasses.replace`), dict,
atau objek biasa yang punya `daily_runtime_minutes`.

Faktor = mingguan × musiman (maks. 2,0). **Default (asumsi, belum divalidasi):**

| Pola | Faktor |
| --- | --- |
| Senin–Kamis | 1,0 |
| Jumat (Jumatan) | 0,9 |
| Sabtu | 1,2 |
| Minggu | 0 (libur) |
| H−30 s.d. H−4 Idulfitri | ×1,4 |
| H−3 s.d. H+5 Idulfitri | ×0 (libur Lebaran) |
| 10 Jun – 15 Jul (tahun ajaran baru) | ×1,25 |
| 1 – 23 Des | ×1,1 |

Tanggal Idulfitri 2023–2030 ada di `IDUL_FITRI_DATES` (tahun mendatang =
perkiraan, perbarui setelah sidang isbat). `explain(day)` memberi alasan dalam
Bahasa Indonesia untuk pesan WhatsApp/dasbor.

**Riwayat pemilik (CSV)** — `OrderBook.from_csv(path)`:

```csv
tanggal,pesanan
2025-08-04,36
2025-08-05,40
```

Rata-rata hari buka menjadi faktor 1,0; faktor mingguan dipelajari bila tiap
hari punya ≥ 2 sampel; setiap tanggal di CSV menjadi faktor persis (bisa diisi
pesanan terkonfirmasi untuk tanggal mendatang). Contoh:
`docs/examples/orders_history_example.csv` (sintetis).

## 5. Validasi (`scripts/validate_twin.py`)

Replay: untuk setiap hari pada data nyata, tiruan digital mensimulasikan beban
"kebiasaan lama" (mesin mulai di `habit_start_hour` lalu jalan terus), baseload,
pola pesanan, PLTS (cuaca NASA tanggal itu), dan baterai, lalu menghitung
impor PLN dan biaya dengan `app/core/tariff.py`.

### Input

1. **Profil UMKM (JSON)** — contoh `docs/examples/twin_profile_example.json`:
   `pv_kwp, battery_kwh, baseload_w` (24 jam), `work_hours_load_w` (lampu/kipas
   jam kerja), `work_start_hour, work_end_hour, ppj_pct` (Pajak Penerangan Jalan
   daerah, %), `connected_power_va` (rekening minimum 40 jam nyala),
   `orders_csv`, dan `machines[]` (`machine_id, label, power_w,
   daily_runtime_minutes, habit_start_hour, duty_cycle`).
2. **Meteran/telemetri (CSV)** — impor PLN di titik sambung:
   `timestamp,kwh` (per jam atau lebih halus, dijumlah per jam) **atau**
   `timestamp,p_active` (W, dirata-rata per jam). Timestamp ber-zona waktu
   dikonversi ke WIB. Hanya hari dengan 24 jam data yang dipakai.
   Contoh: `docs/examples/meter_example.csv`.
3. **Tagihan PLN (CSV)** — `bulan,kwh,rp` (`bulan` = `YYYY-MM`). Periode baca
   meter PLN didekati bulan kalender. Contoh: `docs/examples/pln_bills_example.csv`.

### Menjalankan

```bash
cd backend
python scripts/validate_twin.py --example                       # data contoh, source="example"
python scripts/validate_twin.py --profile profil.json --bills tagihan.csv
python scripts/validate_twin.py --profile profil.json --meter meter.csv --bills tagihan.csv --orders pesanan.csv
python scripts/validate_twin.py --write-example-inputs docs/examples   # bangkitkan ulang contoh sintetis
```

### Output (`settings.twin_validation_path`, default `models/twin_validation.json`)

```json
{"bill_error_pct": 3.95, "energy_error_pct": 3.96, "n_days": 197,
 "source": "example", "generated_at": "2026-11-07T10:43:15+00:00",
 "target_met": true, "meter": {...}, "pln_bill": {...}, "catatan": "Data CONTOH SINTETIS ..."}
```

- `bill_error_pct` = |Σ tagihan simulasi − Σ tagihan nyata| / Σ tagihan nyata × 100
  (dari tagihan PLN bila ada, selain itu dari biaya meteran × tarif).
- `energy_error_pct` = sama untuk kWh (dari meteran bila ada, selain itu dari tagihan).
- Rincian per bulan/per hari, `daily_mape_pct`, `max_monthly_bill_error_pct`,
  `months_within_target`. Target proposal: **selisih tagihan ≤ 10 %**.
- `source`: `meter`, `pln_bill`, `meter+pln_bill`, label `--source`, atau
  `example`.

Hasil saat ini (`source: "example"`, 7 Nov 2026): selisih tagihan 3,95 %,
energi 3,96 %. Data contoh dibangkitkan dengan variasi acak, jam mulai bergeser,
dan baseload berbeda dari profil supaya tidak sirkular — **tetapi tetap sintetis
dan tidak membuktikan akurasi di lapangan.**

### Cara mendapatkan validasi nyata

1. Minta pemilik UMKM 3–6 lembar tagihan/riwayat pemakaian PLN (aplikasi PLN
   Mobile menampilkan kWh & Rp per bulan) → `tagihan.csv`.
2. Isi profil: daftar mesin, daya (pelat nama atau ukur dengan WASKITA), jam mulai
   kebiasaan, menit kerja per hari, PPJ daerah (Sukoharjo: cek di tagihan).
3. Opsional: pasang perangkat WASKITA ≥ 2 minggu, ekspor telemetri
   `timestamp,p_active` → `meter.csv`; catat pesanan harian → `pesanan.csv`.
4. Jalankan validasi **tanpa** menyetel profil memakai bulan yang sama
   (atau: kalibrasi dengan bulan 1–3, uji pada bulan 4–6) agar tidak overfit.
5. Laporkan `bill_error_pct` beserta `source` dan jumlah bulan/hari.

## 6. Keterbatasan yang diketahui

- PV: tanpa bayangan, tanpa degradasi tahunan (ditangani modul finansial),
  POA dengan model isotropik sederhana, angin konstan, satu orientasi atap.
- NASA POWER beresolusi ~0,5° × 0,625°; awan lokal per jam bisa berbeda.
- Hari tipikal (tahun lalu) untuk tanggal masa depan bukan prakiraan cuaca.
- Lokasi di luar WIB tetap memakai `site_timezone` (data LST NASA mengikuti
  bujur, jadi untuk WITA/WIT ubah `site_timezone`).
- Pola pesanan default adalah asumsi; tanggal Idulfitri mendatang perkiraan.
- Tagihan PLN memakai bulan kalender, belum periode baca meter sebenarnya;
  biaya beban/abonemen tidak dimodelkan (golongan B-1/B-2 pascabayar hanya
  rekening minimum).
