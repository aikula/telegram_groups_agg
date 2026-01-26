"""
Bot middleware for aiogram 3.4+

Features:
- Database middleware for DB access in handlers
- Rate limiting middleware
- Chat member filter for permission checks
- Admin filter for admin-only commands
"""

import logging
from typing import Callable, Awaitable, Any, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message, CallbackQuery
from aiogram.filters import BaseFilter

from app.core.db import get_database, Database
from app.core.rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware to provide database instance to handlers.

    Adds `db` key to event data with Database instance.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Add database instance to handler data."""
        db = get_database()
        data["db"] = db
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware for bot updates.

    Uses token bucket algorithm to prevent hitting Telegram rate limits.
    """

    def __init__(self, rate_limiter: RateLimiter):
        """
        Initialize rate limit middleware.

        Args:
            rate_limiter: Rate limiter instance
        """
        super().__init__()
        self._limiter = rate_limiter

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Apply rate limiting before handler execution."""
        update = data.get("event_update", event)

        # Extract chat_id and user_id from update
        chat_id = None
        user_id = None
        chat_type = "private"

        if isinstance(update, Update):
            if update.message:
                chat_id = update.message.chat.id
                user_id = update.message.from_user.id if update.message.from_user else None
                chat_type = update.message.chat.type
            elif update.callback_query:
                chat_id = update.callback_query.message.chat.id
                user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
                chat_type = update.callback_query.message.chat.type
            elif update.inline_query:
                user_id = update.inline_query.from_user.id if update.inline_query.from_user else None
        elif isinstance(event, Message):
            chat_id = event.chat.id
            user_id = event.from_user.id if event.from_user else None
            chat_type = event.chat.type
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id
            user_id = event.from_user.id if event.from_user else None
            chat_type = event.message.chat.type

        # Acquire tokens (wait if needed)
        try:
            await self._limiter.wait_if_needed(
                tokens=1,
                chat_id=chat_id,
                user_id=user_id,
                chat_type=chat_type
            )
        except Exception as e:
            logger.warning(f"Rate limit wait failed: {e}")
            # Continue anyway - don't block on rate limit errors

        return await handler(event, data)


class ChatMemberFilter(BaseFilter):
    """
    Filter to check if user is a chat member.

    Usage:
        @router.message(ChatMemberFilter())
    """

    __slots__ = ("require_member", "require_admin")

    def __init__(
        self,
        require_member: bool = True,
        require_admin: bool = False
    ):
        """
        Initialize chat member filter.

        Args:
            require_member: User must be a chat member
            require_admin: User must be a chat admin
        """
        self.require_member = require_member
        self.require_admin = require_admin

    async def __call__(
        self,
        message: Message,
        db: Database
    ) -> bool:
        """
        Check if user passes the filter.

        Args:
            message: Message object
            db: Database instance

        Returns:
            True if user passes the filter
        """
        if not message.from_user:
            return False

        user_id = message.from_user.id
        chat_id = message.chat.id

        # Check if user is a member
        if self.require_member:
            is_member = await db.is_chat_member(user_id, chat_id)
            if not is_member:
                return False

        # Check if user is an admin
        if self.require_admin:
            is_admin = await db.is_chat_admin(user_id, chat_id)
            if not is_admin:
                return False

        return True


class AdminFilter(BaseFilter):
    """
    Filter to check if user is a superadmin.

    Superadmins have additional permissions like global stats.
    """

    async def __call__(
        self,
        message: Message,
        db: Database
    ) -> bool:
        """
        Check if user is a superadmin.

        Args:
            message: Message object
            db: Database instance

        Returns:
            True if user is a superadmin
        """
        if not message.from_user:
            return False

        user = await db.get_or_create_user(
            user_id=message.from_user.id,
            username=message.from_user.username or "",
            first_name=message.from_user.first_name or "",
        )

        return user.get("is_superadmin", 0) == 1


class PrivateChatFilter(BaseFilter):
    """
    Filter to check if chat is private.

    Usage:
        @router.message(PrivateChatFilter())
    """

    async def __call__(self, message: Message) -> bool:
        """Check if message is from private chat."""
        return message.chat.type == "private"


class GroupChatFilter(BaseFilter):
    """
    Filter to check if chat is a group (group or supergroup).

    Usage:
        @router.message(GroupChatFilter())
    """

    async def __call__(self, message: Message) -> bool:
        """Check if message is from group chat."""
        return message.chat.type in ("group", "supergroup")
