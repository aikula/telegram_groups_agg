"""
Core Rate Limiter module - Telegram API rate limiting

Features:
- Token bucket algorithm for rate limiting
- Per-chat and per-user limits
- Configurable limits for different operation types
- Automatic retry with exponential backoff
- Async-safe with proper locking
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration."""

    max_requests: int  # Maximum requests
    window_seconds: int  # Time window in seconds
    burst: int = 0  # Burst capacity (0 = same as max_requests)

    def __post_init__(self):
        if self.burst == 0:
            self.burst = self.max_requests


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: int  # Maximum tokens
    tokens: float  # Current tokens
    last_update: float  # Last update timestamp
    rate: float  # Tokens per second

    def can_consume(self, tokens: int = 1) -> bool:
        """Check if we can consume tokens."""
        return self.tokens >= tokens

    def consume(self, tokens: int = 1) -> bool:
        """Consume tokens if available."""
        if not self.can_consume(tokens):
            return False

        self.tokens -= tokens
        return True

    def refill(self, now: float) -> None:
        """Refill tokens based on elapsed time."""
        elapsed = now - self.last_update
        if elapsed > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now


# Default rate limits (Telegram API guidelines)
DEFAULT_LIMITS = {
    "global": RateLimit(max_requests=30, window_seconds=1),  # 30 msg/sec
    "group": RateLimit(max_requests=20, window_seconds=1),  # 20 msg/sec for groups
    "private": RateLimit(max_requests=30, window_seconds=1),  # 30 msg/sec for private
    "admin": RateLimit(max_requests=50, window_seconds=1),  # Higher limit for admin operations

    # API endpoint rate limits (v2.2 - Security enhancement)
    "otp_request": RateLimit(max_requests=3, window_seconds=60),  # 3 OTP requests per minute
    "otp_verify": RateLimit(max_requests=10, window_seconds=60),  # 10 verifications per minute
    "auth_login": RateLimit(max_requests=5, window_seconds=300),  # 5 logins per 5 minutes
    "auth_register": RateLimit(max_requests=3, window_seconds=3600),  # 3 registrations per hour
    "settings_update": RateLimit(max_requests=10, window_seconds=60),  # 10 settings updates per minute

    # LLM endpoint rate limits (v2.2 - Cost protection)
    "llm_query": RateLimit(max_requests=10, window_seconds=60),  # 10 LLM queries per minute per user
    "bot_send": RateLimit(max_requests=15, window_seconds=60),  # 15 bot sends per minute per user
    "summary_generate": RateLimit(max_requests=5, window_seconds=60),  # 5 summaries per minute per user
}


class RateLimiter:
    """
    Token bucket rate limiter for Telegram API.

    Prevents hitting Telegram rate limits by tracking
    request rates per chat and globally.
    """

    def __init__(
        self,
        global_limit: Optional[RateLimit] = None,
        default_limits: Optional[Dict[str, RateLimit]] = None
    ):
        """
        Initialize rate limiter.

        Args:
            global_limit: Global rate limit (applies to all requests)
            default_limits: Default limits for different chat types
        """
        self._global_limit = global_limit or DEFAULT_LIMITS["global"]
        self._limits = default_limits or DEFAULT_LIMITS.copy()

        # Token buckets for different scopes
        self._global_bucket = self._create_bucket(self._global_limit)
        self._chat_buckets: Dict[int, TokenBucket] = {}
        self._user_buckets: Dict[int, TokenBucket] = {}

        # Locks for thread-safe operations
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "throttled_requests": 0,
            "retry_after": 0,
        }

    def _create_bucket(self, limit: RateLimit) -> TokenBucket:
        """Create a token bucket from rate limit."""
        rate = limit.max_requests / limit.window_seconds
        return TokenBucket(
            capacity=limit.burst,
            tokens=limit.burst,
            last_update=time.time(),
            rate=rate
        )

    async def acquire(
        self,
        tokens: int = 1,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        chat_type: str = "private"
    ) -> Tuple[bool, Optional[float]]:
        """
        Acquire tokens for a request.

        Args:
            tokens: Number of tokens to acquire
            chat_id: Chat ID for chat-scoped limiting
            user_id: User ID for user-scoped limiting
            chat_type: Type of chat ('private', 'group', 'supergroup', 'channel')

        Returns:
            Tuple of (allowed, retry_after_seconds)
            - allowed: True if request is allowed
            - retry_after: Seconds to wait before retry (if not allowed)
        """
        async with self._lock:
            now = time.time()

            # Refill all buckets
            self._refill_all_buckets(now)

            # Check global limit
            if not self._global_bucket.consume(tokens):
                retry_after = self._calculate_retry_after(self._global_bucket, tokens)
                logger.warning(f"Global rate limit exceeded, retry after {retry_after}s")
                self._stats["throttled_requests"] += 1
                return False, retry_after

            # Check chat limit
            if chat_id is not None:
                chat_bucket = self._get_chat_bucket(chat_id, chat_type)
                if not chat_bucket.consume(tokens):
                    # Refund global token
                    self._global_bucket.tokens += tokens
                    retry_after = self._calculate_retry_after(chat_bucket, tokens)
                    logger.warning(f"Chat {chat_id} rate limit exceeded, retry after {retry_after}s")
                    self._stats["throttled_requests"] += 1
                    return False, retry_after

            # Check user limit
            if user_id is not None:
                user_bucket = self._get_user_bucket(user_id)
                if not user_bucket.consume(tokens):
                    # Refund tokens
                    self._global_bucket.tokens += tokens
                    if chat_id is not None:
                        self._chat_buckets[chat_id].tokens += tokens
                    retry_after = self._calculate_retry_after(user_bucket, tokens)
                    logger.warning(f"User {user_id} rate limit exceeded, retry after {retry_after}s")
                    self._stats["throttled_requests"] += 1
                    return False, retry_after

            self._stats["total_requests"] += 1
            return True, None

    def _refill_all_buckets(self, now: float) -> None:
        """Refill all token buckets."""
        self._global_bucket.refill(now)

        for bucket in self._chat_buckets.values():
            bucket.refill(now)

        for bucket in self._user_buckets.values():
            bucket.refill(now)

    def _get_chat_bucket(self, chat_id: int, chat_type: str) -> TokenBucket:
        """Get or create chat bucket."""
        if chat_id not in self._chat_buckets:
            # Determine limit based on chat type
            if chat_type in ("group", "supergroup"):
                limit = self._limits.get("group", self._limits["private"])
            elif chat_type == "channel":
                limit = self._limits.get("group", self._limits["private"])
            else:
                limit = self._limits.get("private", self._limits["private"])

            self._chat_buckets[chat_id] = self._create_bucket(limit)

        return self._chat_buckets[chat_id]

    def _get_user_bucket(self, user_id: int) -> TokenBucket:
        """Get or create user bucket."""
        if user_id not in self._user_buckets:
            # User limit is typically the same as private chat limit
            limit = self._limits.get("private", self._limits["private"])
            self._user_buckets[user_id] = self._create_bucket(limit)

        return self._user_buckets[user_id]

    def _calculate_retry_after(self, bucket: TokenBucket, tokens: int) -> float:
        """Calculate seconds needed to wait for tokens."""
        if bucket.tokens >= tokens:
            return 0.0

        needed = tokens - bucket.tokens
        return needed / bucket.rate

    async def wait_if_needed(
        self,
        tokens: int = 1,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        chat_type: str = "private"
    ) -> None:
        """
        Wait until tokens are available.

        Args:
            tokens: Number of tokens needed
            chat_id: Chat ID for chat-scoped limiting
            user_id: User ID for user-scoped limiting
            chat_type: Type of chat

        Raises:
            asyncio.TimeoutError: If wait times out
        """
        max_wait = 60  # Maximum wait time in seconds

        while True:
            allowed, retry_after = await self.acquire(
                tokens=tokens,
                chat_id=chat_id,
                user_id=user_id,
                chat_type=chat_type
            )

            if allowed:
                return

            if retry_after and retry_after > max_wait:
                raise asyncio.TimeoutError(
                    f"Rate limit wait would exceed {max_wait}s"
                )

            # Wait for retry_after or a bit longer
            wait_time = min(retry_after or 1, 5)  # Cap wait at 5 seconds
            logger.debug(f"Rate limited, waiting {wait_time}s")
            await asyncio.sleep(wait_time)

    def get_stats(self) -> Dict[str, int]:
        """Get rate limiter statistics."""
        return {
            **self._stats,
            "active_chats": len(self._chat_buckets),
            "active_users": len(self._user_buckets),
            "global_tokens": int(self._global_bucket.tokens),
        }

    def reset_chat(self, chat_id: int) -> None:
        """Reset rate limit for specific chat."""
        if chat_id in self._chat_buckets:
            del self._chat_buckets[chat_id]

    def reset_user(self, user_id: int) -> None:
        """Reset rate limit for specific user."""
        if user_id in self._user_buckets:
            del self._user_buckets[user_id]

    def reset_all(self) -> None:
        """Reset all rate limits."""
        self._chat_buckets.clear()
        self._user_buckets.clear()
        self._global_bucket = self._create_bucket(self._global_limit)

    # API endpoint rate limiting (v2.2)
    async def check_api_rate_limit(
        self,
        endpoint: str,
        identifier: str,
        tokens: int = 1
    ) -> Tuple[bool, Optional[float]]:
        """
        Check rate limit for API endpoints.

        This is a separate rate limiting system for API endpoints like
        OTP generation, authentication, etc. It uses identifier-based
        limiting (IP, telegram_id, user_id) instead of chat/user buckets.

        Args:
            endpoint: Endpoint type (otp_request, otp_verify, auth_login, etc.)
            identifier: Unique identifier (IP address, user_id, telegram_id)
            tokens: Number of tokens to consume

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()

            # Get limit for endpoint
            limit = self._limits.get(endpoint)
            if limit is None:
                # No specific limit for this endpoint, allow
                return True, None

            # Create a bucket key for this endpoint+identifier combination
            bucket_key = f"api:{endpoint}:{identifier}"

            # Get or create bucket
            if bucket_key not in self._chat_buckets:  # Reuse _chat_buckets for API buckets
                self._chat_buckets[bucket_key] = self._create_bucket(limit)

            bucket = self._chat_buckets[bucket_key]

            # Refill based on current time
            bucket.refill(now)

            # Check if we can consume
            if not bucket.consume(tokens):
                retry_after = self._calculate_retry_after(bucket, tokens)
                logger.warning(
                    f"API rate limit exceeded for {endpoint}:{identifier}, "
                    f"retry after {retry_after:.1f}s"
                )
                self._stats["throttled_requests"] += 1
                return False, retry_after

            self._stats["total_requests"] += 1
            return True, None


class RateLimitError(Exception):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


async def with_rate_limit(
    rate_limiter: RateLimiter,
    tokens: int = 1,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    chat_type: str = "private"
):
    """
    Decorator/context manager for rate-limited operations.

    Usage:
        async with with_rate_limit(limiter, chat_id=123):
            await api.send_message(123, "Hello")

        or

        @with_rate_limit(limiter)
        async def my_function():
            ...
    """
    await rate_limiter.wait_if_needed(
        tokens=tokens,
        chat_id=chat_id,
        user_id=user_id,
        chat_type=chat_type
    )
    yield


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get rate limiter singleton instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset global rate limiter."""
    global _rate_limiter
    if _rate_limiter is not None:
        _rate_limiter.reset_all()
    _rate_limiter = RateLimiter()
