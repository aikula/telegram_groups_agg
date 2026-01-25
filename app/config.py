"""
Configuration module - Load settings from .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

class Settings:
    """Application settings loaded from environment variables"""

    def __init__(self):
        """Load and validate settings from environment variables"""
        # Telegram
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")

        # OpenRouter / LLM
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp")

        # Database
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///data/messages.db")

        # Web Server
        self.web_host = os.getenv("WEB_HOST", "0.0.0.0")
        self.web_port = int(os.getenv("WEB_PORT", 8000))

        # Admin Credentials
        self.admin_username = os.getenv("ADMIN_USERNAME", "admin")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "")

        # Bot Settings
        self.context_messages = int(os.getenv("CONTEXT_MESSAGES", 10))
        self.summary_time = os.getenv("SUMMARY_TIME", "16:00")
        self.summary_days = int(os.getenv("SUMMARY_DAYS", 7))
        self.timezone = os.getenv("TIMEZONE", "Europe/Moscow")

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # JWT
        self.jwt_secret = os.getenv("JWT_SECRET", "telegram-analytics-secret-key-change-in-production")

        # Validate required settings
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        if not self.admin_password:
            raise ValueError("ADMIN_PASSWORD not set in environment")

settings = Settings()
