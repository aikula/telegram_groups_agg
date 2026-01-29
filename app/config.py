"""
Configuration module - Pydantic settings for v2.0
"""

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables with Pydantic validation"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # === Telegram ===
    telegram_bot_token: str = Field(..., min_length=10)
    telegram_bot_username: Optional[str] = Field(None, description="Bot username (without @) for Login Widget")
    telegram_webhook_url: Optional[str] = Field(None, json_schema_extra={"example": "https://yourdomain.com/webhook/telegram"})

    # === LLM (OpenAI-compatible API) ===
    llm_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        json_schema_extra={"example": "https://openrouter.ai/api/v1"}
    )
    llm_api_key: str = Field(..., min_length=10)
    llm_model_name: str = Field(default="anthropic/claude-3.5-sonnet")
    llm_max_tokens: int = Field(default=4000, ge=100, le=32000)
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_timeout: int = Field(default=60, ge=5, le=300)

    # === Security ===
    encryption_master_key: str = Field(
        ...,
        description="Base64-encoded 32 bytes for AES-256 encryption. "
                    "Generate with: python -c \"import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
    )
    jwt_secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT tokens. Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60, ge=15, le=1440, description="Token expiration in minutes (default: 1 hour, min: 15min, max: 24hr)")
    superadmin_password_hash: Optional[str] = Field(
        None,
        description="Bcrypt hash of superadmin password. "
                   "Generate with: python -c \"from app.web.auth import hash_password; print(hash_password('YOUR_PASSWORD'))\""
    )
    superadmin_username: str = Field(default="superadmin", description="Superadmin username")

    # === Database ===
    database_url: str = Field(default="sqlite+aiosqlite:///./data/chat_data.db")
    database_path: str = Field(default="data/chat_data.db")

    # === Features ===
    retention_days: int = Field(default=90, ge=1, le=3650)
    summary_time_utc: str = Field(default="13:00", pattern=r"^\d{2}:\d{2}$")
    default_language: str = Field(default="ru")
    context_messages: int = Field(default=20, ge=1, le=100)

    # === Rate Limiting ===
    telegram_global_rate: int = Field(default=30, ge=1, description="Messages per second globally")
    telegram_per_chat_rate: float = Field(default=1.0, ge=0.1, description="Messages per second per chat")
    api_rate_limit: str = Field(default="10/minute")

    # === Server ===
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = Field(default=False)
    base_url: str = Field(default="https://tghub.kulinich.ru", description="Base URL for OTP login messages")

    # === Admin (v1.0 compatibility, deprecated) ===
    admin_username: Optional[str] = Field(None, deprecated="Use superadmin_password_hash instead")
    admin_password: Optional[str] = Field(None, deprecated="Use superadmin_password_hash instead")

    @field_validator("encryption_master_key")
    @classmethod
    def validate_master_key(cls, v: str) -> str:
        """Validate that master key is valid base64"""
        import base64
        try:
            decoded = base64.urlsafe_b64decode(v)
            if len(decoded) < 32:
                raise ValueError("Master key must be at least 32 bytes when decoded")
        except Exception as e:
            raise ValueError(f"Invalid base64 master key: {e}")
        return v

    @field_validator("summary_time_utc")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM format"""
        hours, minutes = v.split(":")
        if not (0 <= int(hours) <= 23):
            raise ValueError("Hour must be between 00 and 23")
        if not (0 <= int(minutes) <= 59):
            raise ValueError("Minute must be between 00 and 59")
        return v

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate supported language"""
        supported = {"ru", "en"}
        if v not in supported:
            raise ValueError(f"Language must be one of: {supported}")
        return v

    def get_model_config(self) -> dict:
        """Get model configuration for LLM client"""
        return {
            "base_url": self.llm_base_url,
            "api_key": self.llm_api_key,
            "model_name": self.llm_model_name,
            "max_tokens": self.llm_max_tokens,
            "temperature": self.llm_temperature,
            "timeout": self.llm_timeout,
        }


# Lazy singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get settings singleton instance (lazy initialization)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Create settings singleton for backward compatibility
# Note: In tests, conftest.py sets env vars before this import
settings = get_settings()
