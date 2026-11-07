from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NOTA LISTRIK API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/nota_listrik"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # NILM
    nilm_model_path: str = "models/nilm_lgbm.pkl"
    nilm_event_threshold_w: float = 50.0
    nilm_event_window_s: int = 3

    # Solar
    site_latitude: float = -7.68
    site_longitude: float = 110.83
    site_altitude_m: float = 103.0
    site_timezone: str = "Asia/Jakarta"

    # Financial
    capex_per_kwp_idr: float = 10_500_000.0
    tarif_pln_per_kwh_idr: float = 1_699.53
    pln_tariff_peak_idr: float = 1_699.53
    pln_tariff_offpeak_idr: float = 1_020.00
    discount_rate: float = 0.07
    panel_lifetime_years: int = 25

    # RL Agent
    rl_model_path: str = "models/ppo_dispatcher.zip"
    n_flexible_machines: int = 4

    # WhatsApp
    whatsapp_send_hour: int = 17
    whatsapp_send_minute: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
