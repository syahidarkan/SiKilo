# Sizing PLTS WASKITA (tahap "Punya PLTS")

Modul: `app/sizing/` · Skema: `app/schemas/sizing.py` · Endpoint: `app/api/v1/endpoints_sizing.py`
Tes: `tests/test_sizing.py`

Semua angka di bawah adalah **estimasi model yang belum divalidasi** terhadap
produksi PLTS dan tagihan nyata UMKM. Survei lokasi oleh penyedia PLTS dan
persetujuan PLN tetap diperlukan.

## 1. Endpoint (semua butuh login `Authorization: Bearer …`)

| Metode | Path | Isi |
|---|---|---|
| POST | `/api/v1/sizing/calculate` | Rekomendasi kWp (+ baterai opsional) dari histori beban per jam |
| POST | `/api/v1/sizing/compare` | kWp minimum untuk target hemat tagihan: kebiasaan lama vs jadwal agen |

Kesalahan input yang lolos validasi skema tetapi tidak bisa dihitung (mis.
beban nol) → `422` dengan pesan Bahasa Indonesia.

## 2. `calculate_optimal_sizing(SizingRequest) -> SizingResult`

### Input penting
- `load_profiles`: daftar `{date, hourly_kwh[24]}` (1–400 hari). Bila data
  mencakup beberapa bulan, tiap bulan memakai hari-hari bulan itu; bulan
  tanpa data memakai semua hari yang ada.
- `location_lat`, `location_lon`: lokasi PLTS (kosong = `settings.site_*`).
- `target_self_consumption_pct` (0,5–1,0; default 0,90).
- `connected_power_va`: daya tersambung PLN; bila diisi, kWp ≤ VA/1000.
- `include_battery` + `battery_options_kwh` (default
  `settings.sizing_battery_options_kwh` = 0; 2,5; 5; 10 kWh).
- `reference_year`: tahun cuaca acuan (default tahun lengkap terakhir).

### Metode
1. **Tahun representatif** (`app/sizing/annual.py`): 12 hari, satu per bulan,
   dipilih sebagai hari dengan energi PV harian paling dekat ke median bulan
   itu pada tahun acuan, dan diberi bobot jumlah hari sebenarnya
   (`calendar.monthrange`, termasuk 29 Februari pada tahun kabisat). Kurva PV
   dari `SolarEngine.simulate_day(..., lat, lon)` (NASA POWER bila tersedia,
   jika tidak clear-sky × indeks kecerahan; sumber dilaporkan di `pv_source`).
2. **Neraca tanpa ekspor** (Permen ESDM No. 2/2024: energi ekspor tidak
   mengurangi tagihan): per slot 15 menit, PV terpakai = `min(PV, beban)`
   untuk SETIAP hari beban yang diamati (bukan rata-rata, supaya hari libur
   yang bebannya kecil ikut menurunkan self-consumption), lalu dirata-rata.
   Surplus = curtailment, bernilai nol.
3. **Baterai** (bila diminta): `Battery.from_kwh(kWh, c_rate=settings.battery_c_rate)`
   dijalankan berurutan atas hari-hari beban (≤ 14 hari terbaru per bulan)
   dengan PV hari representatif; SoC berlanjut antarhari, hari pertama
   dijalankan dua kali sebagai pemanasan. Manfaat = beban yang tidak lagi
   diimpor × tarif slot itu.
4. **Manfaat** = energi yang tidak dibeli dari PLN × tarif dari
   `app.core.tariff.tariff_curve_idr_per_wh()` (flat B-1/B-2 atau WBP/LWBP).
5. **Finansial** (`app/sizing/finance.py`, harga riil tanpa eskalasi tarif):
   CAPEX = kWp × `capex_per_kwp_idr` + kWh × `battery_capex_per_kwh_idr`;
   OPEX = `opex_pct_of_capex` × CAPEX per tahun; manfaat tahun y dikali
   `(1 − panel_degradation_per_year)^(y−1)`; baterai diganti dengan harga
   sama tiap `battery_lifetime_years` (selama < umur panel). NPV pada
   `discount_rate`, PBP sederhana dan PBP terdiskonto (interpolasi di dalam
   tahun; `None`/99,9 bila tidak balik modal), LCOE terdiskonto per kWh
   produksi.
6. **Pilihan ukuran**: grid kWp (≤ 80 titik, langkah 0,05–25 kWp) dari kecil
   sampai batas atas (titik di mana PV puncak ≈ 1,5× beban puncak, atau PV
   harian ≈ konsumsi harian; dipotong daya tersambung). Rekomendasi = **NPV
   maksimum** di antara kandidat dengan self-consumption ≥ target dan
   kWp ≤ daya tersambung. Dengan baterai, ±13 titik kWp (dari optimum tanpa
   baterai ke atas, plus beberapa di bawahnya) × tiap kapasitas baterai.
7. **kWp untuk target SC** (`kwp_for_target_sc`): kWp TERBESAR (tanpa baterai,
   tanpa batas daya tersambung) yang masih memenuhi target. Dicari dengan
   `_binary_search_kwp`. Self-consumption turun monoton terhadap kWp
   (Σmin(k·p, L)/k tidak naik), jadi saat target tercapai batas bawah
   dinaikkan. (Bug lama: arah terbalik → selalu ~0,5 kWp, dan simulasi
   dipanggil dua kali per iterasi. Tes regresi: beban siang 3 kW → > 2 kWp.)

### Output tambahan (selain field lama yang dipakai rapor/scorecard)
`recommended_battery_kwh`, `kwp_for_target_sc`, `target_sc_feasible`,
`max_kwp_limit`, `annual_load_kwh`, `solar_fraction_pct`,
`annual_bill_before_idr`/`after`, `pv_capex_idr`, `battery_capex_idr`,
`annual_opex_idr`, `discounted_payback_years`, `financially_viable`,
`regulatory_checks`, `reference_year`, `pv_source`, `candidates` (kurva
semua kandidat untuk grafik), `assumptions`, `notes`.

### Regulasi — yang diperiksa dan yang TIDAK
`regulatory_checks` (`app/sizing/regulatory.py`) hanya berisi hal yang bisa
dipertanggungjawabkan:
- `kwp_within_connected_power`: kWp ≤ daya tersambung (kVA) bila diketahui;
  `None` bila daya tersambung belum diisi. Ini batas praktis yang dipakai
  WASKITA; aturan kapasitas/kuota yang berlaku dikonfirmasi ke PLN.
- `export_not_credited_modeled = True`: surplus dimodelkan terbuang.
- `application_window_note`: Pasal 14 — permohonan diajukan pada periode
  pendaftaran Januari/Juli sesuai kuota sistem setempat.
- `disclaimer`: kepatuhan final ditentukan PLN.

`permen_esdm_compliant` **usang**, dipertahankan agar scorecard lama tetap
jalan: bernilai `True` hanya bila daya tersambung diisi dan kWp tidak
melebihinya. Ini BUKAN klaim kepatuhan. Konsumen baru sebaiknya membaca
`regulatory_checks`. (Catatan integrasi: `services_data/rapor.py` belum
mengirim `connected_power_va`, sehingga field ini `False` di rapor.)

## 3. `compare_sizing_with_agent(CompareRequest) -> CompareResult` (fitur pembeda)

Pertanyaan: *"Untuk hemat Rp X/bulan (atau X %), berapa kWp minimum bila mesin
tetap dinyalakan menurut kebiasaan lama, dan berapa bila jadwalnya diatur
agen?"* Karena ekspor tidak dikreditkan, menggeser mesin ke jam surya membuat
lebih banyak PV terpakai — panel yang lebih kecil bisa cukup.

### Input
`jobs` (MachineJob; kosong = contoh default), `baseload_w`,
`connected_power_va`, tepat satu dari `target_savings_idr_per_month` /
`target_savings_pct` (persen dari tagihan energi kebiasaan lama tanpa PLTS),
`location_lat/lon`, `battery_kwh`, `kwp_candidates` (≤ 16; kosong = otomatis),
`operating_days_per_week` (default `settings.sizing_operating_days_per_week` = 6),
`solver` (`greedy` default | `ortools`), `reference_year`.

### Metode
- 12 hari representatif yang sama dengan §2. Hari operasional =
  `hari_bulan × hari_operasi/7` (mesin jalan), sisanya hari tutup (beban
  dasar saja).
- Untuk tiap (bulan, kWp): `plan_day(jobs, hari, kwp, baseload, battery,
  solver="greedy", lat, lon)` memberi tiga biaya: **kebiasaan lama** (dengan
  idle), **kebiasaan lama tanpa idle**, dan **jadwal agen**. Mode `ortools`
  menambah OR-Tools dengan batas waktu `settings.sizing_compare_ortools_time_limit_s`
  (0,3 s) per hari dan mengambil jadwal valid termurah. Jadwal agen tidak
  pernah dianggap lebih mahal dari "jam lama tanpa idle" bila jadwal itu valid.
- Hasil per (bulan, kWp, input) di-cache di memori proses (LRU 4096).
- Kandidat otomatis: `settings.sizing_compare_n_candidates` (8) titik dari
  0 sampai kWp yang PV puncaknya ≈ beban puncak (dipotong daya tersambung),
  plus kWp 0 sebagai acuan. Setelah itu tiap kurva diperhalus dengan
  bisection (≤ 4 langkah, berhenti di < 0,05 kWp) di antara dua kandidat yang
  mengapit target; kWp minimum diinterpolasi linear di antara dua titik
  terdekat.

### Output
`reference_annual_bill_idr`, `target_*`, `min_kwp_habit`,
`min_kwp_habit_no_idle`, `min_kwp_agent` (`None` = tidak tercapai di rentang
kandidat), `kwp_reduction`, `kwp_reduction_pct`, `capex_reduction_idr`,
`agent_reduces_panel`, `headline` ("panel X % lebih kecil" atau kalimat jujur
bila tidak), `curve` (tagihan & penghematan per kWp untuk tiga jadwal, PV
terpakai, produksi PV), `notes` (asal penghematan idle vs geser jam, asumsi
hari operasi, tarif flat, keterbatasan solver, batas waktu).

### Waktu komputasi
- Default (`greedy`, 8 kandidat + perhalusan): ±1,5 detik setelah tiruan
  digital hangat (≈ 480 panggilan `plan_day` × ±3 ms); panggilan pertama
  dalam proses bisa +5–10 detik untuk simulasi PV setahun.
- `ortools`: ±0,35 detik per hari operasional → ±30 detik untuk 8 kandidat.
- Batas keras `settings.sizing_compare_time_budget_s` (45 detik): setelah 60 %
  anggaran OR-Tools dimatikan (sisa memakai greedy); setelah 100 % kandidat
  sisanya dilewati dan `timed_out=True`. Satu titik kWp terakhir bisa sedikit
  melewati anggaran (≤ 12 hari × batas OR-Tools), sehingga total tetap < 60 detik.

### Keterbatasan (jujur)
- Tagihan = biaya energi (kWh × tarif) saja; biaya beban/abonemen, PPN/PPJ
  tidak dihitung.
- Penjadwal cepat (greedy / OR-Tools 0,3 s) adalah batas bawah kemampuan agen
  penuh (PPO/OR-Tools 10 s).
- Sebagian penghematan agen berasal dari mematikan mesin idle (asumsi daya
  idle `default_idle_power_frac`, belum diukur); kurva "tanpa idle"
  memisahkan efek ini dari efek geser jam.
- Runtime mesin dianggap sama setiap hari operasional (pola pesanan musiman
  dari `OrderBook` belum dipakai di compare).

## 4. Asumsi & keterbatasan umum
- Tiruan digital PV belum divalidasi terhadap PLTS nyata di Sukoharjo
  (lihat `docs/DIGITAL_TWIN.md`, `scripts/validate_twin.py`).
- Degradasi diterapkan proporsional pada manfaat (konservatif); penggantian
  inverter tidak dimodelkan terpisah (dianggap masuk OPEX 1 %).
- Tidak ada eskalasi tarif PLN (analisis harga riil).
- Beban per jam dibagi rata ke 4 slot; puncak di dalam jam tidak terlihat.
- Satu hari representatif per bulan meredam variasi cuaca harian; untuk
  validasi, bandingkan dengan simulasi 365 hari bila data lapangan tersedia.

### Cara memvalidasi dengan data lapangan (belum dilakukan)
1. Kumpulkan ≥ 30 hari ledger per jam (`EnergyLedger`) dari perangkat WASKITA.
2. Jalankan `/sizing/calculate` dengan `connected_power_va` UMKM.
3. Setelah PLTS terpasang, bandingkan produksi & tagihan nyata dengan
   `annual_generation_kwh`/12 dan `annual_bill_after_idr`/12 per bulan;
   catat galat di laporan validasi (`settings.twin_validation_path`).
4. Sampai langkah 3 dilakukan, tampilkan semua angka sebagai estimasi.

## 5. Konfigurasi (`app/core/config.py`)
`capex_per_kwp_idr`, `battery_capex_per_kwh_idr`, `opex_pct_of_capex`,
`discount_rate`, `panel_lifetime_years`, `panel_degradation_per_year`,
`grid_emission_kg_per_kwh`, dan field baru: `battery_lifetime_years` (10),
`battery_c_rate` (0,5), `sizing_battery_options_kwh`,
`sizing_operating_days_per_week` (6), `sizing_compare_n_candidates` (8),
`sizing_compare_time_budget_s` (45), `sizing_compare_ortools_time_limit_s` (0,3).
