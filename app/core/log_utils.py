"""
Log Utilities - Sanitization for sensitive data in logs (v2.2)

Provides functions to redact sensitive information from logs before output.
Prevents leakage of:
- Passwords, tokens, API keys
- User messages content
- PII (personal identifiable information)
- Sensitive query parameters
"""

import re
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Patterns that may contain sensitive data in SQL queries
SENSITIVE_SQL_PATTERNS = [
    # Message content
    (r"content\s*=\s*'[^']*'", "content = '***'"),
    (r'content\s*=\s*"[^"]*"', 'content = "***"'),
    (r"content\s+LIKE\s+'[^']*'", "content LIKE '***'"),
    # User text/search terms
    (r"WHERE\s+[^']*'[^']{20,}'", "WHERE ***"),  # Long string literals
    # Usernames (partially redact)
    (r"username\s*=\s*'([^']*)'", lambda m: f"username = '{_partial_redact(m.group(1))}'"),
    # Email patterns
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***'),
    # Phone numbers (basic pattern)
    (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '***-***-****'),
]

# Sensitive field names in arguments/tool calls
SENSITIVE_FIELDS = [
    'password', 'passwd', 'pwd',
    'token', 'access_token', 'refresh_token', 'auth_token',
    'api_key', 'apikey', 'api-key',
    'secret', 'private_key', 'secret_key',
    'credential', 'credentials',
    'ssn', 'social_security',
    'credit_card', 'card_number',
]


def _partial_redact(value: str, visible_chars: int = 2) -> str:
    """
    Partially redact a value, showing first few chars only.

    Args:
        value: String to redact
        visible_chars: Number of characters to show at start

    Returns:
        Redacted string like "ab***"
    """
    if not value or len(value) <= visible_chars:
        return "***"
    return value[:visible_chars] + "***"


def sanitize_log_query(query: str, max_length: int = 200) -> str:
    """
    Sanitize SQL query for logging, redacting sensitive data.

    Redacts:
    - Message content values
    - Long string literals (likely user input)
    - Email addresses
    - Phone numbers
    - Truncates very long queries

    Args:
        query: SQL query string
        max_length: Maximum length of returned string

    Returns:
        Sanitized query safe for logging
    """
    if not query:
        return ""

    # Truncate first if very long
    if len(query) > max_length:
        query = query[:max_length] + "..."

    # Apply redaction patterns
    sanitized = query

    for pattern, replacement in SENSITIVE_SQL_PATTERNS:
        if callable(replacement):
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        else:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def sanitize_log_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize function arguments for logging.

    Redacts values for sensitive field names.

    Args:
        args: Arguments dictionary

    Returns:
        Sanitized arguments dictionary
    """
    if not args:
        return {}

    sanitized = {}
    args_lower_keys = {k.lower(): k for k in args.keys()}

    for key, value in args.items():
        key_lower = key.lower()

        # Check if this is a sensitive field
        is_sensitive = any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS)

        if is_sensitive:
            # Redact the entire value
            sanitized[key] = "***"
        elif isinstance(value, str) and len(value) > 100:
            # Truncate long string values
            sanitized[key] = value[:100] + "..."
        elif isinstance(value, dict):
            # Recursively sanitize nested dicts
            sanitized[key] = sanitize_log_args(value)
        elif isinstance(value, list):
            # Sanitize list items (truncate if strings)
            sanitized[key] = [
                (v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v)
                for v in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_log_message(message: str) -> str:
    """
    Sanitize a general log message for sensitive patterns.

    Removes:
    - Email addresses
    - Phone numbers
    - API keys (common formats)
    - Tokens (common formats)

    Args:
        message: Log message string

    Returns:
        Sanitized message
    """
    if not message:
        return ""

    sanitized = message

    # Email addresses
    sanitized = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***', sanitized)

    # Phone numbers
    sanitized = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '***-***-****', sanitized)

    # Bearer tokens
    sanitized = re.sub(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer ***', sanitized)

    # API keys (common patterns: sk-..., pk-..., etc.)
    sanitized = re.sub(r'\b[A-Za-z0-9]{20,}\b', '***', sanitized)

    return sanitized


def safe_log(logger_instance: logging.Logger, level: str, message: str, **kwargs):
    """
    Safely log a message, sanitizing sensitive data.

    Args:
        logger_instance: Logger instance to use
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        message: Message to log
        **kwargs: Additional data to sanitize before logging
    """
    # Sanitize message
    safe_message = sanitize_log_message(message)

    # Sanitize kwargs
    safe_kwargs = sanitize_log_args(kwargs)

    # Get log function
    log_func = getattr(logger_instance, level.lower(), logger_instance.info)

    # Log with sanitized data
    if safe_kwargs:
        log_func(f"{safe_message} | Data: {safe_kwargs}")
    else:
        log_func(safe_message)


def get_safe_dict_repr(data: Dict[str, Any], max_value_length: int = 50) -> str:
    """
    Get a safe string representation of a dictionary for logging.

    Args:
        data: Dictionary to represent
        max_value_length: Maximum length for string values

    Returns:
        Safe string representation
    """
    if not data:
        return "{}"

    safe_items = []
    for key, value in data.items():
        key_lower = key.lower()

        # Check for sensitive keys
        is_sensitive = any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS)

        if is_sensitive:
            safe_items.append(f"'{key}': '***'")
        elif isinstance(value, str):
            if len(value) > max_value_length:
                safe_items.append(f"'{key}': '{value[:max_value_length]}...'")
            else:
                safe_items.append(f"'{key}': '{value}'")
        elif isinstance(value, dict):
            safe_items.append(f"'{key}': {get_safe_dict_repr(value, max_value_length)}")
        elif isinstance(value, list):
            safe_items.append(f"'{key}': [list of {len(value)} items]")
        else:
            safe_items.append(f"'{key}': {value}")

    return "{" + ", ".join(safe_items) + "}"


# ============================================================================
# Convenience decorators for automatic logging sanitization
# ============================================================================

def log_with_sanitization(func):
    """
    Decorator to automatically sanitize function arguments in logs.

    Use on functions that log their parameters.
    """
    def wrapper(*args, **kwargs):
        # Log sanitized call
        func_name = func.__name__
        safe_kwargs = sanitize_log_args(kwargs)

        logger.debug(f"Calling {func_name} with args: {safe_kwargs}")

        return func(*args, **kwargs)
    return wrapper


class SafeLogger:
    """
    A logger wrapper that automatically sanitizes all logged data.

    Usage:
        safe_logger = SafeLogger(logger)
        safe_logger.info("User login", username="john", token="secret")
        # Logs: "User login | Data: {'username': 'john', 'token': '***'}"
    """

    def __init__(self, logger_instance: logging.Logger):
        self.logger = logger_instance

    def _sanitize_and_log(self, level: str, message: str, **kwargs):
        safe_message = sanitize_log_message(message)
        safe_kwargs = sanitize_log_args(kwargs)

        log_func = getattr(self.logger, level.lower())
        if safe_kwargs:
            log_func(f"{safe_message} | Data: {safe_kwargs}")
        else:
            log_func(safe_message)

    def debug(self, message: str, **kwargs):
        self._sanitize_and_log("debug", message, **kwargs)

    def info(self, message: str, **kwargs):
        self._sanitize_and_log("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._sanitize_and_log("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._sanitize_and_log("error", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._sanitize_and_log("critical", message, **kwargs)
