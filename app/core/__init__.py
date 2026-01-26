"""
Core module - Foundation components for v2.0

This module provides the core functionality for the application:
- crypto: Per-chat AES-256 encryption
- i18n: Multi-language support (ru/en)
- db: Database operations with aiosqlite
- llm: LLM client with OpenAI-compatible API
- sql_agent: Safe SQL generation
- rate_limiter: Telegram API rate limiting
"""

from app.core.crypto import ChatCrypto, get_crypto
from app.core.i18n import (
    get_text,
    get_available_languages,
    get_language_info,
    is_supported_language,
    get_translation_keys,
    t,
    t_en,
    LANGUAGES,
)
from app.core.db import Database, get_database
from app.core.llm import LLMClient, get_llm_client, close_llm_client
from app.core.sql_agent import SQLAgent, get_sql_agent, SQLValidationError
from app.core.rate_limiter import (
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
    RateLimitError,
    RateLimit,
)

__all__ = [
    # Crypto
    "ChatCrypto",
    "get_crypto",
    # i18n
    "get_text",
    "get_available_languages",
    "get_language_info",
    "is_supported_language",
    "get_translation_keys",
    "t",
    "t_en",
    "LANGUAGES",
    # Database
    "Database",
    "get_database",
    # LLM
    "LLMClient",
    "get_llm_client",
    "close_llm_client",
    # SQL Agent
    "SQLAgent",
    "get_sql_agent",
    "SQLValidationError",
    # Rate Limiter
    "RateLimiter",
    "get_rate_limiter",
    "reset_rate_limiter",
    "RateLimitError",
    "RateLimit",
]
