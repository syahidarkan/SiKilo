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
  - `UMKM(id, name, umkm_type, address, kecamatan, phone_whatsapp?, connected_power_va?, tariff_group, pv_kwp, battery_kwh, consent_share_data, created_at)`
  - `Device(id, device_id[unique], umkm_id, api_key_hash, firmware_version?, last_seen?, created_at)`
  - `TelemetryRecord(id, device_id, ts, v_rms, i_rms, p_active, q_reactive, frequency)`
  - `ApplianceEvent(id, umkm_id, device_id, ts, event_type, appliance_class, label, delta_p, confidence, source)`
  - `EnergyLedger(id, umkm_id, day[date], hour, appliance_label, kwh, cost_idr)` unik (umkm_id, day, hour, appliance_label)
  - `MachineProfile(id, umkm_id, machine_id, label, appliance_class, power_w, daily_runtime_minutes, earliest_hour, deadline_hour, habit_start_hour?, is_flexible, min_continuous_minutes)`
  - `DailyPlan(id, umkm_id, day, solver, cost_idr, baseline_cost_idr, savings_idr, savings_pct, deadlines_met, payload_json, created_at)`
  - `MessageLog(id, umkm_id, kind[daily|weekly], provider, status[sent|failed|skipped], body, error?, created_at)`
  - `Lead(id, umkm_id, installer_user_id?, status[new|contacted|surveyed|installed|lost], recommended_kwp, notes?, created_at, updated_at)`
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

## 5. Sizing (`app/sizing/`)

- `calculate_optimal_sizing(SizingRequest) -> SizingResult`
- `compare_sizing_with_agent(CompareRequest) -> CompareResult` (ukuran PLTS dengan jadwal kebiasaan lama vs jadwal agen).

## 6. Layanan (`app/services/`)

- `whatsapp_agent.generate_daily_brief(plan: PlanResult | DispatchResponse, umkm_name, target_date) -> str`
- `whatsapp_agent.generate_weekly_nota(...) -> str`
- `whatsapp_sender.send_whatsapp(phone, body) -> SendResult(status, provider, error)`
- `scorecard_generator.generate_bankability_scorecard(...) -> dict` dan `render_scorecard_pdf(scorecard: dict) -> bytes`
- `scheduler.start_scheduler()` / `scheduler.shutdown_scheduler()` (APScheduler, no-op bila `settings.scheduler_enabled` False).

## 7. Firmware → API

- `POST /api/v1/telemetry/ingest`, header `X-Device-Key: <key>`, body `TelemetryPayload` (lihat `app/schemas/telemetry.py`).
- `POST /api/v1/telemetry/ingest-batch`, header sama, body `{"device_id": str, "samples": [TelemetryPayload tanpa device_id …]}` untuk mengirim buffer offline (maks. 500 sampel).
- Device diregistrasi via `POST /api/v1/devices` (role admin/installer) yang mengembalikan API key sekali saja.
