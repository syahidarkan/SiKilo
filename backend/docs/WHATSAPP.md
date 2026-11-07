# Layanan "Hemat" WASKITA — WhatsApp, nota mingguan, penjadwal, rapor PDF

Modul: `app/services/` (`whatsapp_agent.py`, `whatsapp_sender.py`, `jobs.py`,
`scheduler.py`, `scorecard_generator.py`, `scorecard_data.py`) dan
`app/api/v1/endpoints_agent.py`. Tes: `tests/test_services.py`.

## 1. Pesan WhatsApp

### Brief harian (`generate_daily_brief(plan, umkm_name, target_date)`)
- Input `PlanResult` (`app.agent.planner.plan_day`) atau `DispatchResponse`
  (`POST /dispatch/optimize`; juga respons lama yang hanya berisi slot).
- Isi: tanggal Indonesia (dibuat manual, aman di Windows), jam nyala **per
  mesin** sebagai rentang berurutan (`09:00–11:00, 13:00–14:00`), perkiraan
  hemat vs kebiasaan lama, produksi PLTS (bila ada), dan peringatan bila ada
  mesin yang tidak selesai sebelum tenggat.
- Penghematan negatif ditulis jujur ("diperkirakan Rp X LEBIH MAHAL…").
  Bila tarif flat dan belum ada PLTS, pesan menjelaskan bahwa menggeser jam
  tidak mengubah tagihan.
- Selalu ≤ 1000 karakter: detail dikurangi bertahap (jumlah mesin, jumlah
  blok, baris PLTS) bila terlalu panjang.

### Nota mingguan (`generate_weekly_nota(umkm_name, week_start, week_end, usage)`)
- Data dari `EnergyLedger` (`jobs.weekly_usage`): kWh & Rp per label untuk 7
  hari terakhir yang sudah lengkap (default berakhir kemarin, WIB) vs 7 hari
  sebelumnya.
- Menampilkan total, per mesin (naik/turun %), mesin paling boros, dan tips.
- Tips idle hanya memakai data TERUKUR: energi label mesin (bukan baseload)
  yang tercatat di luar jam kerja (`work_start_hour`–`work_end_hour`). Bila
  tidak ada, tips umum ditampilkan.
- Angka adalah estimasi NILM perangkat, bukan tagihan resmi PLN (ditulis di pesan).

## 2. Pengiriman (`whatsapp_sender.send_whatsapp(phone, body)`)

| `WHATSAPP_PROVIDER` | Perilaku |
|---|---|
| `none` (default) | Tidak mengirim; `SendResult(status="skipped")`. Cocok untuk dev/tes/demo. |
| `fonnte` | `POST https://api.fonnte.com/send`, header `Authorization: <WHATSAPP_API_TOKEN>`, form `target`, `message`, `countryCode=62`. Sukses bila respons `{"status": true}`. |
| `meta` | WhatsApp Cloud API `POST https://graph.facebook.com/<WHATSAPP_META_API_VERSION>/<WHATSAPP_PHONE_NUMBER_ID>/messages`, `Authorization: Bearer <WHATSAPP_API_TOKEN>`, pesan `type: text`. |

- Nomor dinormalisasi: `0812…`, `+62 812-…`, `812…` → `62812…`; nomor yang
  bukan seluler Indonesia ditolak (`failed`).
- `httpx` dengan batas waktu `WHATSAPP_TIMEOUT_S` (default 15 detik). Fungsi
  **tidak pernah melempar exception**; galat dikembalikan sebagai
  `SendResult(status="failed", error=...)` dan dicatat di `MessageLog`.
- **Batasan Meta**: pesan teks bebas hanya boleh dalam 24 jam sejak pelanggan
  terakhir mengirim pesan ke nomor bisnis. Brief 17:30 adalah pesan inisiatif
  bisnis, jadi di produksi perlu *message template* yang disetujui Meta
  (kategori *utility*). Implementasi saat ini hanya mengirim teks; bila Meta
  menolak (mis. kode 131047) galatnya menyebut kebutuhan template. Menambah
  pengiriman template adalah pekerjaan lanjutan.
- Fonnte memakai nomor WhatsApp biasa (tidak resmi dari Meta); cocok untuk
  pilot, risikonya nomor dapat dibatasi WhatsApp bila mengirim massal.

## 3. Penjadwal (`scheduler.py`) dan job (`jobs.py`)

- `start_scheduler()` dipanggil di lifespan `app/main.py`; **no-op** bila
  `SCHEDULER_ENABLED=false` (default).
- `AsyncIOScheduler` zona `settings.site_timezone` (Asia/Jakarta):
  - harian `WHATSAPP_SEND_HOUR:WHATSAPP_SEND_MINUTE` (default 17:30) →
    `jobs.run_daily_briefs()`;
  - mingguan hari `WEEKLY_REPORT_WEEKDAY` (0 = Senin … 6 = Minggu; default 5 =
    Sabtu) jam yang sama → `jobs.run_weekly_notas()`.
- Job harian, untuk tiap UMKM dengan `phone_whatsapp` **dan** minimal satu
  `MachineProfile`: `plan_day` untuk **besok** dengan `pv_kwp` &
  `battery_kwh` UMKM (solver `SCHEDULER_SOLVER`, default `auto`) → simpan
  `DailyPlan` (payload ringkas: blok per mesin, kWh, catatan) → kirim brief →
  simpan `MessageLog(kind="daily")`.
- Job mingguan: semua UMKM dengan nomor WA → nota mingguan →
  `MessageLog(kind="weekly")`.
- Tiap UMKM diproses dengan sesi DB sendiri; satu kegagalan tidak menghentikan
  yang lain. Ringkasan dikembalikan (`processed`, `counts`, `results`).
- Jalankan penjadwal di **satu** proses saja (mis. satu worker uvicorn), kalau
  tidak pesan terkirim ganda.
- Fungsi job bisa dipanggil langsung (tes/skrip), mis.:
  ```python
  import asyncio
  from app.services import jobs
  asyncio.run(jobs.run_daily_briefs(solver="greedy", send=False))
  ```

## 4. Endpoint (`/api/v1/agent`, semua butuh login)

| Metode & path | Peran | Keterangan |
|---|---|---|
| `GET /whatsapp/daily-brief?umkm_id&target_date&solver&save_plan` | umkm (miliknya), admin | Rencana nyata dari profil mesin → pesan (tidak dikirim). Default tanggal besok. 409 bila belum ada profil mesin. |
| `POST /whatsapp/send-now` body `{umkm_id?, kind: daily|weekly, target_date?, solver}` | umkm (miliknya), admin | Kirim sekarang + `MessageLog`. 409 bila nomor WA kosong. |
| `GET /reports/weekly-nota?umkm_id&week_end` | umkm (miliknya), admin | Nota mingguan + angka per label. |
| `POST /reports/bankability-scorecard` | semua peran login | Rapor JSON dari angka yang dikirim (`sizing`, opsional `sizing_after_agent`, `agent_compare`, `machine_usage`). |
| `POST /reports/bankability-scorecard.pdf` | semua peran login | Sama, keluaran `application/pdf`. |
| `GET /reports/bankability-scorecard?umkm_id` | umkm (miliknya), admin, bank/installer bila UMKM setuju berbagi data | Rapor JSON dari data DB. 409 bila data < `SIZING_MIN_DATA_DAYS` hari. |
| `GET /reports/bankability-scorecard.pdf?umkm_id` | sama | Versi PDF. |

## 5. Rapor kelayakan (`scorecard_generator.py`, `scorecard_data.py`)

Isi rapor: profil UMKM, **periode audit** (jumlah hari & tanggal), **profil
pemakaian per mesin** (dari `EnergyLedger` bila ada), rekomendasi PLTS pola
pakai saat ini (kWp, CAPEX, produksi, konsumsi sendiri, hemat, **PBP**,
**NPV**, LCOE, cek kWp vs daya tersambung), **kWp setelah jadwal agen**
(`compare_sizing_with_agent`: kWp minimum untuk target hemat yang sama dengan
kebiasaan lama vs jadwal agen), skor indikatif, dampak CO₂, **sumber data**
(terukur vs simulasi, asumsi finansial dari `config.py` dan tarif dari
`app/core/tariff.py`), catatan, dan disclaimer.

Rapor dari DB (`build_scorecard_for_umkm`):
1. Profil kWh per jam 30 hari terakhir (hari dengan ≥ 20 jam tercatat).
2. Biaya bulanan = rata-rata harian (kWh × tarif) × 30 — **bukan** tagihan PLN.
3. `calculate_optimal_sizing` atas profil terukur.
4. `compare_sizing_with_agent` dengan profil mesin UMKM dan target hemat
   (persen) = hemat sizing / tagihan sebelum PLTS. Ini simulasi tiruan digital,
   bukan hasil ukur setelah jadwal diterapkan (ditulis di catatan rapor).
   Bila profil mesin/modul belum tersedia, bagian ini kosong beserta alasannya.

### Skor kelayakan — heuristik draf, BELUM dikalibrasi

| Komponen | Bobot | Skor 0–100 |
|---|---|---|
| Payback period sederhana | 30% | ≤ 3 th → 100, ≥ 13 th → 0, linier |
| NPV / CAPEX (indeks profitabilitas) | 25% | ≥ 1,0 → 100, ≤ 0 → 0, linier |
| Rasio konsumsi sendiri PV | 25% | nilai persen langsung |
| kWp vs daya tersambung PLN | 20% | di bawah batas → 100, belum diketahui → 50, melebihi → 0 |

Kategori netral: ≥ 80 "Indikasi kelayakan kuat", 60–79 "Indikasi kelayakan
sedang", < 60 "Perlu kajian lanjut" (`risk_category` berisi label ini,
`category_code` berisi kodenya).

Bobot, ambang, dan kategori ini **dipilih tim tanpa data kredit** dan harus
dikalibrasi bersama bank/koperasi mitra (mis. memakai data pinjaman PLTS
historis: gagal bayar vs PBP/NPV/rasio konsumsi sendiri). Rapor tidak
menjanjikan produk, tier, atau bunga dari lembaga keuangan mana pun, dan
`bankability_score.calibrated` selalu `false` sampai kalibrasi dilakukan.

## 6. Konfigurasi terkait (`.env`)

```
WHATSAPP_PROVIDER=none|fonnte|meta
WHATSAPP_API_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...        # khusus meta
WHATSAPP_META_API_VERSION=v20.0
WHATSAPP_TIMEOUT_S=15
WHATSAPP_SEND_HOUR=17
WHATSAPP_SEND_MINUTE=30
WEEKLY_REPORT_WEEKDAY=5
SCHEDULER_ENABLED=true
SCHEDULER_SOLVER=auto
```

## 7. Belum divalidasi / pekerjaan lanjutan
- Pengiriman nyata ke Fonnte/Meta belum diuji dengan akun sungguhan (tes
  memakai `httpx.MockTransport`).
- Template pesan Meta untuk pesan inisiatif bisnis belum dibuat.
- Perkiraan hemat di brief adalah hasil tiruan digital; belum dibandingkan
  dengan tagihan PLN nyata setelah jadwal diterapkan.
- Bobot skor rapor belum dikalibrasi (lihat §5).
