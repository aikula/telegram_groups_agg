"""
Bot module - Telegram Bot Core (aiogram 3.4+)

This module provides the Telegram bot functionality:
- bot: Bot setup and configuration
- middleware: Auth, rate limiting, chat checks
- handlers: Command and message handlers
- scheduler: Background tasks (daily summaries, etc.)
"""

from app.bot.bot import get_bot, close_bot
from app.bot.middleware import (
    ChatMemberFilter,
    AdminFilter,
    RateLimitMiddleware,
    DatabaseMiddleware,
    PrivateChatFilter,
    GroupChatFilter,
)
from app.bot.scheduler import get_scheduler, start_scheduler, stop_scheduler

__all__ = [
    # Bot
    "get_bot",
    "close_bot",
    # Middleware
    "ChatMemberFilter",
    "AdminFilter",
    "RateLimitMiddleware",
    "DatabaseMiddleware",
    "PrivateChatFilter",
    "GroupChatFilter",
    # Scheduler
    "get_scheduler",
    "start_scheduler",
    "stop_scheduler",
]
