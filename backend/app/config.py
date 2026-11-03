from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://kampungadem:kampungadem@localhost:5432/kampungadem"
    redis_url: str = "redis://localhost:6379/1"

    # Auth
    jwt_secret: str = "change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]

    # Phone protection (base64, 32 bytes each). Generate: python -m app.cli gen-key
    phone_enc_key: str = ""
    phone_hash_key: str = ""

    # Ingest
    ingest_api_key: str = ""  # for POST /api/v1/sensors/readings
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_topic: str = "application/+/device/+/event/up"

    # WhatsApp Cloud API
    wa_enabled: bool = False  # when False, messages are logged as "dry_run" and never sent
    wa_graph_version: str = "v23.0"
    wa_phone_number_id: str = ""
    wa_token: str = ""
    wa_app_secret: str = ""  # verifies X-Hub-Signature-256
    wa_verify_token: str = ""  # webhook subscription handshake
    wa_template_lang: str = "id"

    # Anti-spam (design doc 13.3)
    cooldown_min: int = 180
    max_alerts_per_recipient_per_day: int = 3
    quiet_start_hour: int = 21
    quiet_end_hour: int = 5

    # Node health (design doc 13.4)
    node_late_min: int = 30
    node_offline_min: int = 120
    low_battery_ticket_v: float = 3.4

    # Satellite
    gee_service_account: str = ""
    gee_key_file: str = ""
    gee_rw_asset: str = ""  # FeatureCollection with property rw_id
    lst_overlay_dir: str = "/data/lst"


@lru_cache
def get_settings() -> Settings:
    return Settings()
