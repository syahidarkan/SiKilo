# Kontrak antarmodul WASKITA backend

Dokumen ini adalah kontrak antarmodul. Setiap modul boleh mengubah isi
internalnya, tetapi **nama, signature, dan makna** di bawah ini harus dijaga
agar modul lain tetap jalan. Bila kontrak terpaksa berubah, perbarui dokumen
ini di commit yang sama.

Brand produk: **WASKITA** (bukan "NOTA LISTRIK" / "SiKilo" di backend).
Bahasa teks untuk pengguna: Bahasa Indonesia.

## 0. Fondasi bersama (sudah ada)

- `app/core/config.py` → `settings` (lihat field di file).
- `app/core/tariff.py`
  - `tariff_idr_per_kwh(hour) -> float`, `tariff_idr_per_wh(hour) -> float`
  - `tariff_curve_idr_per_wh(n_slots=96) -> np.ndarray` (Rp/Wh per slot)
  - `is_peak_hour(hour) -> bool`, `N_SLOTS = 96`, `SLOT_HOURS = 0.25`
  - **Semua** perhitungan biaya listrik wajib memakai modul ini (jangan
    hard-code tarif atau jam puncak).
- Satu hari = 96 slot × 15 menit, slot `t` ↔ jam `t // 4`.

## 1. Database & auth (`app/core/database.py`, `app/core/auth.py`, `app/models/`)

- `app/core/database.py`: `engine`, `AsyncSessionLocal`, `Base`,
  `get_db()` (dependency FastAPI), `async def init_db()` (create_all).
  SQLite (`aiosqlite`) dan Postgres (`asyncpg`) sama-sama didukung.
- `app/models/__init__.py` mengekspor model SQLAlchemy 2.0 (Mapped):
  - `User(id, username, hashed_password, full_name, email, role, umkm_id?, is_active, created_at)`
    role ∈ `umkm | disperinaker | installer | bank | admin`
  - `UMKM(id, name, umkm_type, address, kecamatan, phone_whatsapp?, connected_power_va?, tariff_group, pv_kwp, battery_kwh, consent_share_data, consent_share_gov, consent_updated_at?, phone_verified_at?, phone_otp_hash?, phone_otp_expires_at?, phone_otp_sent_at?, phone_otp_attempts, whatsapp_opt_out, created_at)`
    - `consent_share_data`: data rinci boleh dibaca **installer & bank** (bukan Disperinaker).
    - `consent_share_gov`: nama & ringkasan agregat boleh tampil di dashboard **Disperinaker**.
    - Nomor WA hanya dipakai mengirim bila `phone_verified_at` terisi (OTP) dan `whatsapp_opt_out` False.
  - `Device(id, device_id[unique], umkm_id, api_key_hash, firmware_version?, last_seen?, created_at)`
  - `TelemetryRecord(id, device_id, ts, v_rms, i_rms, p_active, q_reactive, frequency)`
  - `ApplianceEvent(id, umkm_id, device_id, ts, event_type, appliance_class, label, delta_p, confidence, source)`
  - `EnergyLedger(id, umkm_id, day[date], hour, appliance_label, kwh, cost_idr)` unik (umkm_id, day, hour, appliance_label)
  - `MachineProfile(id, umkm_id, machine_id, label, appliance_class, power_w, daily_runtime_minutes, earliest_hour, deadline_hour, habit_start_hour?, is_flexible, min_continuous_minutes, idle_minutes_habit, idle_power_w?, cooldown_minutes?)` — dipetakan 1:1 ke `MachineJob` oleh `jobs.profiles_to_jobs`.
  - `DailyPlan(id, umkm_id, day, solver, cost_idr, baseline_cost_idr, savings_idr, savings_pct, deadlines_met, payload_json, created_at)`
  - `MessageLog(id, umkm_id, kind[daily|weekly], provider, status[sent|failed|skipped], body, error?, created_at)`
  - `Lead(id, umkm_id, installer_user_id?, status[new|contacted|surveyed|installed|lost], recommended_kwp, notes?, requested_by_umkm, created_at, updated_at)`
- `init_db()` juga menjalankan migrasi ADITIF ringan (`ALTER TABLE … ADD COLUMN` untuk kolom baru); perubahan skema lain butuh alat migrasi.
- `app/core/auth.py`: `hash_password`, `verify_password`, `create_access_token(data)`,
  `get_current_user` (dependency → `User`), `require_roles(*roles)` (dependency factory),
  `get_current_device` (dependency dari header `X-Device-Key` → `Device`).

## 2. NILM (`app/nilm/`)

- `event_detector.TelemetrySample`, `event_detector.TransientEvent`, `EventDetector.push(sample) -> TransientEvent | None` (dipertahankan).
- `classifier.NILMClassifier().predict(event) -> ClassificationResult(appliance_class, label, confidence, source)`; `APPLIANCE_LABELS: dict[int,str]`.
- `disaggregator.LoadDisaggregator(classifier: NILMClassifier | None = None)`:
  - `push(sample: TelemetrySample) -> DisaggregationUpdate`
    - `DisaggregationUpdate(event: TransientEvent | None, classification: ClassificationResult | None, active: dict[str, float]  # label → watt estimasi)`
  - `pop_hourly_energy() -> list[HourlyEnergy]` → bucket jam yang SUDAH selesai, lalu dihapus dari buffer.
    `HourlyEnergy(day: date, hour: int, appliance_label: str, kwh: float)`; residu yang tak terjelaskan dilabeli `"Baseload / Background"`.
  - Energi per jam semua label dijumlah = energi terukur total (konservasi energi).

## 3. Tiruan digital (`app/digital_twin/`)

- `solar_engine.get_solar_engine() -> SolarEngine`
  - `SolarEngine.simulate_day(target_date, kwp, lat=None, lon=None) -> np.ndarray(96,) [W AC]`
  - `SolarEngine.last_source: str` ∈ `"nasa_power" | "clearsky_scaled"`
  - `SolarEngine.INVERTER_EFF`
- `battery.Battery(capacity_wh, max_charge_w, max_discharge_w, efficiency_rt=0.90, soc_min_frac=0.20, soc_init_frac=0.50)`
  - `reset()`, `soc_wh` (property), `step(net_w: float, dt_h: float = 0.25) -> tuple[float, float]`
    `net_w = pv - load` (positif = surplus). Return `(grid_import_wh, curtail_wh)` setelah baterai menyerap/menutup sebisanya. SoC tidak pernah < soc_min.
- `orders.OrderBook` → `jobs_for(day: date, base_jobs) -> list` (skala runtime harian menurut pola pesanan mingguan/musiman).
- `scripts/validate_twin.py` membandingkan simulasi vs data nyata dan menulis `settings.twin_validation_path`
  (JSON: `{"bill_error_pct": float, "energy_error_pct": float, "n_days": int, "source": str, "generated_at": iso}`).

## 4. Agen penjadwal (`app/agent/`, `app/digital_twin/factory_model.py`)

- `app/agent/planner.py`:
  ```python
  @dataclass
  class PlanResult:
      schedule: np.ndarray          # (96, n_machines) int8
      machine_ids: list[str]
      load_w: np.ndarray            # (96,) total beban termasuk baseload, W
      pv_w: np.ndarray              # (96,) W
      grid_w: np.ndarray            # (96,) W impor PLN
      curtail_w: np.ndarray         # (96,) W PV tak terpakai (tidak dikreditkan, Permen ESDM 2/2024)
      cost_idr: float
      baseline_load_w: np.ndarray   # (96,) kebiasaan lama
      baseline_cost_idr: float
      savings_idr: float
      savings_pct: float
      solver_used: str
      deadlines_met: bool
      battery_soc_wh: np.ndarray | None

  def plan_day(jobs: list[MachineJob], target_date: date, kwp: float = 0.0,
               baseload_w: float | None = None, battery: Battery | None = None,
               solver: str = "auto",            # auto | ortools | ppo | greedy
               lat: float | None = None, lon: float | None = None) -> PlanResult

  def habit_schedule(jobs, ...) -> np.ndarray   # kebiasaan lama: mesin mulai di habit_start_hour lalu jalan terus sampai runtime terpenuhi
  ```
- `MachineJob` di `app/schemas/dispatch.py` memiliki: `machine_id, appliance_class, label, power_w, daily_runtime_minutes, earliest_hour=settings.work_start_hour, deadline_hour=settings.work_end_hour, habit_start_hour: int | None, min_continuous_minutes=15, is_flexible=True`.
- Baseline = **kebiasaan lama pemilik**, BUKAN "semua mesin nyala 24 jam".
- `MachineJob` juga punya `idle_minutes_habit`, `idle_power_w?`, `cooldown_minutes?`.
- `factory_model.simulate_schedule` menilai **defisit SoC baterai akhir hari** (SoC awal − SoC akhir)
  sebagai biaya isi ulang (`÷ η_charge × tarif rata-rata`) dan menambahkannya ke `cost_idr`
  (`SimResult.soc_deficit_cost_idr`); OR-Tools & env RL memakai penilaian yang sama.
- `PlanResult` tambahan: `baseline_pv_used_kwh` (Σ pv − curtail baseline), `soc_deficit_cost_idr`,
  `baseline_soc_deficit_cost_idr`. Selisih biaya < Rp 0,5 dianggap 0 (`savings_idr` tidak pernah −0.0).

## 5. Sizing (`app/sizing/`)

- `calculate_optimal_sizing(SizingRequest) -> SizingResult`
- `compare_sizing_with_agent(CompareRequest) -> CompareResult` (ukuran PLTS dengan jadwal kebiasaan lama vs jadwal agen).

## 6. Layanan (`app/services/`)

- `whatsapp_agent.generate_daily_brief(plan: PlanResult | DispatchResponse, umkm_name, target_date) -> str`
- `whatsapp_agent.generate_weekly_nota(umkm_name, week_start, week_end, usage, *, days_this_week=None, days_prev_week=None) -> str`
  (bila jumlah hari data berbeda → bandingkan rata-rata per hari; minggu lalu kosong → tanpa perbandingan).
- `whatsapp_agent.safe_name(name) -> str` (nama untuk salam: tanpa tautan/format).
- `whatsapp_sender.send_whatsapp(phone, body, *, scheduled=False) -> SendResult(status, provider, error)`
  (`scheduled=True` + Meta + `whatsapp_meta_template_name` → pesan template).
- `jobs.measured_baseload_w(db, umkm_id, end=None, days=14) -> float | None` (median label baseload ledger × 1000).
- `jobs.send_block_reason(db, umkm) -> str | None`, `jobs.sends_today(db, umkm_id, kind) -> int`.
- `scorecard_generator.generate_bankability_scorecard(...) -> dict` dan `render_scorecard_pdf(scorecard: dict) -> bytes`
- `scheduler.start_scheduler()` / `scheduler.shutdown_scheduler()` (APScheduler, no-op bila `settings.scheduler_enabled` False).

## 7. Firmware → API

- `POST /api/v1/telemetry/ingest`, header `X-Device-Key: <key>`, body `TelemetryPayload` (lihat `app/schemas/telemetry.py`).
- `POST /api/v1/telemetry/ingest-batch`, header sama, body `{"device_id": str, "samples": [TelemetryPayload tanpa device_id …]}` untuk mengirim buffer offline (maks. 500 sampel).
  Sampel bertimestamp > `telemetry_max_future_skew_s` di masa depan dibuang per sampel (respons 200,
  `rejected_future`), bukan 422 untuk seluruh batch.
- Device diregistrasi via `POST /api/v1/devices` (admin, atau installer yang **ditugaskan** ke UMKM itu lewat
  Lead berstatus ≠ lost) yang mengembalikan API key sekali saja; aturan sama untuk `rotate-key` & daftar perangkat.

## 8. Profil UMKM & mesin (`/api/v1/umkm`, `app/api/v1/endpoints_umkm.py`)

- `GET/PATCH /umkm/{id|me}` — pemilik & admin (semua field); installer yang ditugaskan hanya
  `pv_kwp`, `battery_kwh`, `connected_power_va`. Mengganti nomor WA membatalkan verifikasi.
  Mencabut consent menghapus cache rapor UMKM itu.
- `POST /umkm/me/phone/request-otp`, `POST /umkm/me/phone/verify`, `POST /umkm/{id}/phone/mark-verified` (admin).
- `GET/POST /umkm/{id|me}/machines`, `PATCH/DELETE /umkm/{id|me}/machines/{machine_id}`,
  `GET /umkm/{id|me}/machines/suggestions` (usulan dari ledger NILM, tidak disimpan otomatis).
- `PATCH /dashboard/leads/{id}` dengan `status="installed"` wajib `installed_kwp` → disalin ke `UMKM.pv_kwp`.

## 9. WebSocket (`/ws/telemetry`)

- Token JWT dikirim sebagai pesan pertama `{"type":"auth","token":...}`; `?token=` di query ditolak (4401).
- Masa berlaku token & status akun dicek ulang tiap `settings.ws_auth_recheck_s` detik (4401/4403).
