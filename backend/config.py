# backend/config.py
"""
Application configuration using Pydantic Settings.
All values are loaded from environment variables or .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Application
    app_name: str = "OTP Device Manager"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = secrets.token_hex(32)
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/device_manager"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = secrets.token_hex(32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # OTP
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 3
    otp_cooldown_seconds: int = 60
    otp_length: int = 6

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_verify_service_sid: str = ""

    # Firebase
    firebase_project_id: str = ""
    firebase_private_key_path: str = "./firebase-service-account.json"

    # Encryption
    encryption_key: str = ""

    # Rate Limiting
    rate_limit_per_minute: int = 60
    otp_rate_limit_per_hour: int = 5

    # WebSocket
    ws_heartbeat_interval: int = 30

    # Logging
    log_level: str = "INFO"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance - loaded once at startup."""
    return Settings()