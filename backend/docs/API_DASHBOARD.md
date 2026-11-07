# API data lapangan & dashboard WASKITA

Dokumen ini menjelaskan endpoint telemetri tersimpan, buku energi per mesin,
kanal live WebSocket, dashboard multi-peran, rujukan (lead) PLTS, dan papan KPI.
Semua path di bawah berawalan `/api/v1` kecuali WebSocket (`/ws/...`).

> **Status validasi.** Energi per mesin adalah *estimasi* disagregasi NILM
> (bukan meter per mesin). Angka akurasi NILM dan selisih tagihan simulator di
> papan KPI saat ini berasal dari data **sintetis/contoh** → **belum divalidasi**
> di lapangan. Lihat `docs/NILM.md` dan `docs/DIGITAL_TWIN.md` untuk cara
> menjalankan evaluasi dengan data nyata.

Kode: `app/api/v1/endpoints_telemetry.py`, `endpoints_ws.py`,
`endpoints_dashboard.py`, `app/services_data/*`, skema di
`app/schemas/telemetry.py` dan `app/schemas/dashboard.py`.

## 1. Hak akses ringkas

| Data | umkm | disperinaker | installer | bank | admin |
|---|---|---|---|---|---|
| Ledger / status mesin / sampel mentah | miliknya | UMKM consent | UMKM consent | UMKM consent | semua |
| `GET /dashboard/umkm` | miliknya | – | – | – | `umkm_id` |
| `GET /dashboard/disperinaker` | – | ✔ (agregat consent) | – | – | ✔ |
| Lead (rujukan PLTS) | ajukan, lihat, batalkan miliknya | – | lihat terbuka + miliknya, ubah status | – | semua |
| `GET /dashboard/bank` | – | – | – | ✔ (consent, read-only) | ✔ |
| `GET /dashboard/kpi` | cakupan UMKM-nya | cakupan UMKM consent | cakupan UMKM consent | cakupan UMKM consent | semua |
| WebSocket live | UMKM-nya | – | – | – | 1 UMKM / semua |

"UMKM consent" = `UMKM.consent_share_data = true`. UMKM yang tidak consent hanya
masuk ke hitungan `n_umkm_total` (tanpa nama, tanpa energi). Pengecualian: lead
yang **diajukan sendiri** oleh UMKM membagikan nama, alamat, dan nomor WhatsApp
ke installer agar bisa dihubungi.

## 2. Firmware → telemetri

### `POST /telemetry/ingest`
Header `X-Device-Key: <api key>`. Body:
```json
{"device_id":"WSK-A1B2C3","timestamp":"2026-11-07T12:00:00+07:00",
 "v_rms":228.1,"i_rms":1.2,"p_active":250.0,"q_reactive":30.0,"frequency":50.0}
```
- `device_id` wajib sama dengan perangkat pemilik key (403 bila beda).
- `p_active ≥ 0`, `v_rms 0–300`, `i_rms 0–200`, `frequency 48–52`.
- `timestamp` tanpa zona waktu dianggap WIB (`settings.site_timezone`). Lebih
  dari `telemetry_max_future_skew_s` (300 s) di depan jam server → 422.
- Timestamp ≤ sampel terakhir yang sudah diproses perangkat itu → dianggap
  kiriman ulang, dilewati (`duplicate: true`). Jadi firmware **wajib mengirim
  buffer lama lebih dulu** (sesuai firmware README §11).

Respons (`TelemetryResponse`): `detected_event`, `event_type`, `delta_p`,
`appliance_label`, `confidence`, `source`, `active_appliances` (label → W),
`baseload_w`, `stored`, `ledger_rows_written`, `message`.

### `POST /telemetry/ingest-batch`
Body `{"device_id": "...", "samples": [ {timestamp, v_rms, i_rms, p_active, q_reactive, frequency}, ... ]}`,
1–500 sampel. Server mengurutkan sampel menurut waktu. Respons:
`received, processed, skipped_duplicates, stored_records, events, ledger_rows_written`.

### Apa yang terjadi di server
1. `LoadDisaggregator` per perangkat (cache memori) → event ON/OFF + daya per mesin.
2. `TelemetryRecord` disimpan bila ≥ `telemetry_raw_keep_every_s` (10 s) sejak
   sampel tersimpan terakhir, saat jam lokal berganti, atau saat ada event.
3. `ApplianceEvent` untuk event mesin (kelas ≠ 0).
4. Jam yang sudah selesai (`pop_hourly_energy`) ditambahkan ke `EnergyLedger`
   (`INSERT … ON CONFLICT DO UPDATE`, aman untuk beberapa perangkat per UMKM).
   Biaya = kWh × `app.core.tariff.tariff_idr_per_kwh(jam)`.
5. Hasil disiarkan ke WebSocket live UMKM tersebut.
6. Bila commit DB gagal, status disaggregator dikembalikan ke kondisi sebelum
   request → firmware boleh mengirim ulang tanpa energi ganda.

**Restart server.** Saat perangkat pertama kali terlihat, sampel tersimpan pada
jam lokal yang sedang berjalan diputar ulang ke disaggregator baru. Jam itu
belum pernah masuk ledger (sampel pertama tiap jam selalu disimpan), jadi tidak
ada hitungan ganda. Energi jam tersebut menjadi perkiraan (resolusi ~10 s) dan
status ON/OFF mesin bisa meleset sampai event berikutnya.

**Batasan deploy.** Cache disaggregator & hub live ada di memori satu proses.
Jalankan API dengan **satu worker** (mis. `uvicorn app.main:app --workers 1`)
atau pindahkan state ke Redis bila perlu skala horizontal.

## 3. Buku energi & status mesin (JWT)

### `GET /telemetry/ledger?umkm_id=&start=&end=&granularity=hour|day`
- `umkm_id` opsional untuk role umkm (default miliknya), wajib untuk role lain.
- `start`/`end` tanggal lokal inklusif (default 7 hari terakhir), maks. 366 hari.
- Respons: `rows` (`day`, `hour` atau `null` bila per hari, `appliance_label`,
  `kwh`, `cost_idr`), `per_appliance` (total & `share_pct`), `total_kwh`,
  `total_cost_idr`, `tariff_scheme`, `tariff_group`, `note`.
- Hanya jam yang sudah selesai yang tercatat; jam berjalan muncul setelah
  sampel jam berikutnya masuk.

### `GET /telemetry/appliances/status?umkm_id=`
Status ON/OFF per mesin. `source: "live"` bila ada perangkat UMKM yang
mengirim data dalam `device_online_window_s` (status dari disaggregator di
memori); selain itu `source: "event"` dari `ApplianceEvent` terakhir per label.

### `GET /telemetry/records?umkm_id=&device_id=&minutes=60&limit=1000`
Sampel mentah tersimpan (sudah di-downsample) untuk grafik daya.

## 4. WebSocket `/ws/telemetry`

```
ws://<host>/ws/telemetry?token=<JWT>&mode=live|simulator[&umkm_id=N]
```
- Token wajib (query param, karena browser tidak bisa mengirim header di WebSocket).
  Gagal → pesan `{"type":"error"}` lalu ditutup dengan kode 4401/4403.
- Pesan pertama: `{"type":"hello","mode":..., "umkm_id":..., "role":...}`.
- `mode=live` (default; role umkm/admin): menerima siaran
  `{"type":"telemetry","simulated":false,"device_id","umkm_id","timestamp","p_active",
  "q_reactive","v_rms","i_rms","frequency","active_appliances","baseload_w","detected_event",
  ["event_type","delta_p","delta_q","appliance_class","appliance_label","confidence","source"], ["batch"]}`.
  Untuk ingest-batch dikirim satu pesan (sampel terakhir) dengan ringkasan `batch.events`.
- `mode=simulator` (semua role): tidak menerima siaran.
- Di kedua mode klien boleh mengirim sampel JSON (field seperti ingest;
  `device_id` opsional). Diproses NILM di disaggregator milik koneksi itu,
  dibalas dengan `simulated: true`, **tidak disimpan**, tidak masuk ledger.
- `{"type":"ping"}` → `{"type":"pong"}`. Pesan > 8 KB → tutup 1009.

Contoh JavaScript:
```js
const ws = new WebSocket(`${WS_BASE}/ws/telemetry?token=${token}`);
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.type === 'telemetry') render(m); };
```

## 5. Dashboard

### `GET /dashboard/umkm?umkm_id=&include_rapor=false`
Profil UMKM, energi hari ini / 7 hari / 30 hari (dari ledger), mesin terboros,
perangkat (+ online), rencana agen terakhir & ringkasan 30 hari, lead, dan bila
`include_rapor=true` ringkasan kelayakan PLTS (lihat §6).

### `GET /dashboard/disperinaker?days=30`
Agregat UMKM consent: `n_umkm_total`, `n_umkm_consent`, `n_umkm_with_data`,
`total_kwh`, `total_cost_idr`, `recorded_plan_savings_idr` (Σ penghematan
rencana agen), `potential_savings_idr_per_month` (rata-rata penghematan harian
rencana × 30 per UMKM, dijumlah), `kecamatan[]`, `plts` (`n_with_pv`,
`n_ready_for_pv`, definisi siap-PLTS, `leads_by_status`, `total_pv_kwp`), dan
daftar `umkm[]` (tanpa kontak).

"Siap PLTS" = belum punya PLTS (`pv_kwp = 0`) dan punya ≥ `sizing_min_data_days`
hari data dalam periode.

### Lead (rujukan PLTS)
- `POST /dashboard/leads` — umkm: body `{"notes": "..."}` ("saya tertarik
  PLTS"); admin: `{"umkm_id", "installer_user_id"?, "recommended_kwp"?, "notes"?}`.
  Bila `recommended_kwp` kosong, dihitung dari data 30 hari terakhir (§6); bila
  data belum cukup → `0` dan alasannya ditulis di `notes`. Satu UMKM hanya boleh
  punya satu lead aktif (`new|contacted|surveyed`) → selain itu 409.
- `GET /dashboard/leads?status=` — installer: lead miliknya + lead `new` yang
  belum ditugaskan; umkm: miliknya; admin: semua.
- `PATCH /dashboard/leads/{id}` body `{"status"?, "notes"?, "claim"?, "recompute_kwp"?,
  "installer_user_id"? (admin), "unassign"? (admin)}`.
  Installer yang mengubah lead belum ditugaskan otomatis mengambilnya; lead
  milik installer lain → 403. Pemilik UMKM hanya boleh mengubah status ke
  `lost` (batal) dan catatan.

### `GET /dashboard/bank?limit=50&offset=0`
Read-only. Daftar UMKM consent + `rapor` (§6).

## 6. Ringkasan rapor (kWp, PBP, skor)

`app/services_data/rapor.py`:
- Butuh ≥ `sizing_min_data_days` (default 7) hari **lengkap** (≥ 20 jam
  tercatat) dalam 30 hari terakhir. Kurang → `status: "belum_ada_data"`.
- kWp & PBP dari kontrak `app.sizing.calculate_optimal_sizing`, skor dari
  `app.services.scorecard_generator.generate_bankability_scorecard`.
  Bila modul itu error → `status: "gagal"` dengan alasan; angka TIDAK dikarang.
- Perhitungan berjalan di thread (timeout 90 s) dan di-cache per UMKM selama
  data ledger tidak berubah. Hitungan pertama bisa belasan detik.
- Selalu disertai `validation`: perkiraan otomatis, belum divalidasi auditor energi.

## 7. Papan KPI — `GET /dashboard/kpi?days=30`

Setiap metrik: `key, name, value, unit, target, target_direction (min|max),
status (ok|di_bawah_target|info|belum_ada_data), source, validation, detail, updated_at`.

| key | Sumber | Target |
|---|---|---|
| `nilm_accuracy` | `settings.nilm_metrics_path` → `overall.energy_estimated_accuracy` (%) | `target.threshold` di file (0,8 → 80 %) |
| `twin_bill_error` | `settings.twin_validation_path` → `bill_error_pct` | `target_bill_error_pct` atau 10 % (maks.) |
| `avg_savings_pct` | `DailyPlan.savings_pct` (rencana terakhir per UMKM per hari) | – (estimasi tiruan digital) |
| `orders_on_time_pct` | `DailyPlan.deadlines_met` | 95 % |
| `devices_online` | `Device.last_seen` ≤ `device_online_window_s` | – |

File tidak ada / kosong / rusak, atau belum ada baris DB → `status: "belum_ada_data"`
dan `detail.cara` menjelaskan skrip yang harus dijalankan. Untuk data lapangan:
1. Pasang perangkat + smart plug referensi, kumpulkan CSV (lihat `docs/NILM.md`).
2. `python scripts/evaluate_nilm.py ... --data-source field` → menulis `nilm_metrics_path`.
3. `python scripts/validate_twin.py ...` dengan tagihan PLN/meter nyata → `twin_validation_path`.

## 8. Konfigurasi terkait (`app/core/config.py`)

| Field | Default | Arti |
|---|---|---|
| `telemetry_raw_keep_every_s` | 10 | jarak minimal sampel mentah yang disimpan |
| `device_last_seen_update_interval_s` | 30 | frekuensi tulis `Device.last_seen` |
| `device_online_window_s` | 300 | batas "online" untuk KPI & status live |
| `telemetry_max_future_skew_s` | 300 | toleransi timestamp di masa depan |
| `sizing_min_data_days` | 7 | minimal hari data lengkap untuk rekomendasi kWp |
| `site_timezone` | Asia/Jakarta | zona waktu ledger & timestamp naive |
