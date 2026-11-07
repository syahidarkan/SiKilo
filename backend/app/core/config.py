from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Konfigurasi terpusat WASKITA. Semua nilai bisa ditimpa lewat environment
    variable (nama field dalam huruf besar) atau file `.env` di folder backend.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Aplikasi ────────────────────────────────────────────────────────────
    app_name: str = "WASKITA API"
    app_version: str = "0.2.0"
    debug: bool = False
    environment: Literal["development", "production", "test"] = "development"
    # Muat solar engine / agen PPO saat startup (matikan di tes agar cepat).
    preload_models: bool = True

    # ── Keamanan ────────────────────────────────────────────────────────────
    # WAJIB diisi di production. Bila kosong di development, auth.py membuat
    # kunci acak per proses (token tidak bertahan setelah restart).
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    # Akun admin awal hanya dibuat bila kedua nilai ini diisi lewat env.
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    # Cost factor bcrypt (12 untuk production; tes memakai 4 agar cepat).
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]
    )

    # ── Database ────────────────────────────────────────────────────────────
    # Default SQLite agar bisa jalan tanpa Postgres; production pakai
    # postgresql+asyncpg://user:pass@host:5432/waskita
    database_url: str = "sqlite+aiosqlite:///./data/waskita.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    # Simpan sampel mentah telemetri hanya tiap N detik (hemat storage).
    telemetry_raw_keep_every_s: int = 10
    # Device.last_seen hanya ditulis ulang bila lebih lama dari N detik
    # (mengurangi tulis DB pada telemetri 1 Hz).
    device_last_seen_update_interval_s: int = 30
    # Perangkat dianggap "online" bila last_seen ≤ N detik yang lalu (papan KPI).
    device_online_window_s: int = 300
    # Timestamp telemetri boleh lebih maju dari jam server paling banyak N detik.
    telemetry_max_future_skew_s: int = 300
    # Minimal hari data lengkap (≥ 20 jam tercatat) sebelum rekomendasi kWp dihitung.
    sizing_min_data_days: int = 7

    # ── NILM ────────────────────────────────────────────────────────────────
    nilm_model_path: str = "models/nilm_lgbm.pkl"
    nilm_metrics_path: str = "models/nilm_metrics.json"
    nilm_event_threshold_w: float = 50.0
    nilm_event_window_s: int = 3
    # Transien yang tak kunjung stabil dipaksa selesai setelah N detik.
    nilm_event_max_transient_s: int = 20
    # Toleransi waktu (detik) saat mencocokkan event panel ke transisi smart plug.
    nilm_label_tolerance_s: float = 5.0

    # ── Lokasi & cuaca ──────────────────────────────────────────────────────
    site_latitude: float = -7.68
    site_longitude: float = 110.83
    site_altitude_m: float = 103.0
    site_timezone: str = "Asia/Jakarta"
    use_nasa_power: bool = True
    nasa_power_cache_dir: str = "data/nasa_power"
    nasa_power_timeout_s: float = 20.0
    # Rasio GHI aktual/clear-sky bila data NASA POWER tidak tersedia
    # (rata-rata tahunan Jawa Tengah kira-kira 0,70–0,80).
    clearness_index_fallback: float = 0.75
    twin_validation_path: str = "models/twin_validation.json"
    # Boleh mengunduh dari NASA POWER saat runtime (False = hanya cache lokal).
    # Saat pytest berjalan, unduhan selalu dimatikan oleh weather.py.
    nasa_power_allow_network: bool = True
    # Parameter sistem PLTS atap (tiruan digital).
    pv_tilt_deg: float = 10.0          # kemiringan panel; 0 = datar
    pv_azimuth_deg: float = 0.0        # 0 = menghadap utara (belahan bumi selatan)
    pv_system_losses_frac: float = 0.14  # kabel, debu, mismatch, toleransi modul (selain inverter)
    pv_temp_coeff_per_c: float = -0.004  # koefisien daya modul per °C (c-Si)
    pv_wind_speed_ms: float = 1.0      # angin asumsi untuk model suhu sel Faiman

    # ── Tarif PLN ───────────────────────────────────────────────────────────
    # UMKM golongan B-1/B-2 bertarif FLAT (tanpa WBP/LWBP). Skema "tou" hanya
    # untuk B-3/I-3 (>200 kVA) dengan WBP 17:00–22:00.
    tariff_scheme: Literal["flat", "tou"] = "flat"
    tariff_group: str = "B-2"
    tariff_flat_idr_per_kwh: float = 1_444.70
    tariff_lwbp_idr_per_kwh: float = 1_114.74
    tariff_wbp_multiplier: float = 1.5
    tariff_wbp_start_hour: int = 17
    tariff_wbp_end_hour: int = 22

    # ── Operasional UMKM (default) ─────────────────────────────────────────
    work_start_hour: int = 7
    work_end_hour: int = 17
    default_baseload_w: float = 800.0
    # Jam mulai "kebiasaan lama" pemilik bila tidak diisi per mesin.
    default_habit_start_hour: int = 8
    # Daya mesin saat menyala tanpa beban (idle) sebagai fraksi daya nominal.
    # ASUMSI (belum diukur); dipakai bila MachineJob.idle_power_w kosong.
    default_idle_power_frac: float = 0.4
    # Jeda minimal (menit) setelah mesin dimatikan sebelum boleh dinyalakan lagi.
    default_cooldown_minutes: int = 30

    # ── Finansial PLTS ─────────────────────────────────────────────────────
    capex_per_kwp_idr: float = 10_500_000.0
    battery_capex_per_kwh_idr: float = 6_000_000.0
    opex_pct_of_capex: float = 0.01
    discount_rate: float = 0.07
    panel_lifetime_years: int = 25
    panel_degradation_per_year: float = 0.005
    grid_emission_kg_per_kwh: float = 0.785
    # Baterai: umur pakai (diganti dengan harga yang sama tiap N tahun) & C-rate.
    battery_lifetime_years: int = 10
    battery_c_rate: float = 0.5
    # Opsi kapasitas baterai (kWh) yang dicoba sizing bila include_battery=True.
    sizing_battery_options_kwh: List[float] = Field(default_factory=lambda: [0.0, 2.5, 5.0, 10.0])
    # Hari operasional per minggu (default) untuk /sizing/compare; hari tutup = beban dasar saja.
    sizing_operating_days_per_week: int = 6
    # /sizing/compare: jumlah kandidat kWp otomatis, batas waktu total, dan batas waktu OR-Tools per hari.
    sizing_compare_n_candidates: int = 8
    sizing_compare_time_budget_s: float = 45.0
    sizing_compare_ortools_time_limit_s: float = 0.3

    # ── Agen RL ────────────────────────────────────────────────────────────
    rl_model_path: str = "models/ppo_dispatcher.zip"
    ortools_time_limit_s: float = 10.0
    n_flexible_machines: int = 4
    # Jumlah slot mesin pada kebijakan PPO (job lebih sedikit → di-padding,
    # lebih banyak → planner memakai OR-Tools).
    rl_max_machines: int = 6
    # Metadata model PPO (versi observasi, jumlah slot mesin) & hasil evaluasi.
    rl_meta_path: str = "models/ppo_dispatcher.meta.json"
    agent_eval_path: str = "models/agent_eval.json"

    # ── WhatsApp & penjadwal ───────────────────────────────────────────────
    whatsapp_provider: Literal["none", "fonnte", "meta"] = "none"
    whatsapp_api_token: str = ""
    whatsapp_phone_number_id: str = ""  # khusus Meta Cloud API
    whatsapp_send_hour: int = 17
    whatsapp_send_minute: int = 30
    weekly_report_weekday: int = 5  # 0=Senin … 5=Sabtu
    scheduler_enabled: bool = False
    # Batas waktu permintaan HTTP ke penyedia WhatsApp (detik).
    whatsapp_timeout_s: float = 15.0
    # Versi Graph API untuk WhatsApp Cloud API (Meta).
    whatsapp_meta_api_version: str = "v20.0"
    # Solver yang dipakai job harian penjadwal (auto | ortools | ppo | greedy).
    scheduler_solver: Literal["auto", "ortools", "ppo", "greedy"] = "auto"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
