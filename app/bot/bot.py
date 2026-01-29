"""
Bot setup and configuration using aiogram 3.4+

Features:
- Bot instance management
- Dispatcher setup with routers
- Command and message handler registration
- Startup and shutdown hooks
"""

import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.core.db import get_database
from app.core.rate_limiter import get_rate_limiter


logger = logging.getLogger(__name__)


# Singleton instances
_bot: Optional[Bot] = None
_dispatcher: Optional[Dispatcher] = None


def get_bot() -> Bot:
    """
    Get bot singleton instance.

    Returns:
        Bot instance
    """
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
        logger.info("Bot instance created")
    return _bot


def get_dispatcher() -> Dispatcher:
    """
    Get dispatcher singleton instance.

    Returns:
        Dispatcher instance
    """
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher()
        logger.info("Dispatcher instance created")
    return _dispatcher


async def set_bot_commands() -> None:
    """
    Set bot commands for different scopes.

    Sets different command lists for private chats and group chats.
    """
    bot = get_bot()

    # Private chat commands
    private_commands = [
        BotCommand(command="start", description="Начать работу / Показать справку"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="login", description="Вход в веб-интерфейс"),
        BotCommand(command="stats", description="Статистика чата"),
        BotCommand(command="export", description="Экспорт истории чата"),
        BotCommand(command="settings", description="Настройки чата"),
        BotCommand(command="diagnostics", description="Диагностика бота"),
    ]

    # Group chat commands
    group_commands = [
        BotCommand(command="start", description="Показать справку"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="stats", description="Статистика чата"),
        BotCommand(command="export", description="Экспорт истории чата"),
        BotCommand(command="settings", description="Настройки чата"),
        BotCommand(command="summarize_thread", description="Сводка обсуждения (ответить на сообщение)"),
        BotCommand(command="ask", description="Задать вопрос о чате"),
        BotCommand(command="diagnostics", description="Диагностика бота"),
    ]

    await bot.set_my_commands(
        private_commands,
        scope=BotCommandScopeAllPrivateChats()
    )

    await bot.set_my_commands(
        group_commands,
        scope=BotCommandScopeAllGroupChats()
    )

    logger.info("Bot commands set")


async def startup() -> None:
    """
    Bot startup hook.

    Initializes database, sets commands, sets webhook, checks chat membership, starts scheduler.
    """
    logger.info("Bot starting up...")

    # Initialize database
    db = get_database()
    await db.init_database()
    logger.info("Database initialized")

    # Set bot commands
    await set_bot_commands()

    # Set webhook if BASE_URL is configured
    from app.config import settings
    if hasattr(settings, 'base_url') and settings.base_url:
        bot = get_bot()
        webhook_url = f"{settings.base_url}/webhook/telegram"
        try:
            await bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")

    # Check bot permissions and group membership
    bot = get_bot()
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot info: {bot_info.first_name} (@{bot_info.username})")
        logger.info(f"Can read all group messages: {bot_info.can_read_all_group_messages}")

        if not bot_info.can_read_all_group_messages:
            logger.warning("⚠️ Bot cannot read all group messages!")
            logger.warning("⚠️ Make the bot ADMIN in groups OR disable Privacy Mode in BotFather")
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")

    # Start scheduler
    from app.bot.scheduler import start_scheduler
    await start_scheduler()
    logger.info("Scheduler started")

    # Log chat list for diagnostics (chats are created automatically via webhook)
    logger.info("Getting chat list from database...")
    await get_chat_list()

    logger.info("Bot startup complete")
    logger.info("ℹ️ Chats will be automatically synced when messages arrive via webhook")


async def sync_chats() -> None:
    """
    Sync all chats where bot is a member.

    This function fetches all chats/supergroups where bot is added
    and creates/updates them in the database.
    """
    from app.config import settings

    bot = get_bot()
    db = get_database()

    logger.info("Starting chat synchronization...")

    try:
        bot_info = await bot.get_me()
        bot_user_id = bot_info.id

        # Get updates to see which chats bot has access to
        # Note: This only works if bot can read group messages
        updates = await bot.get_updates(offset=-1, limit=100, timeout=1)

        # Track unique chat IDs from updates
        chat_ids = set()
        for update in updates:
            if update.message:
                chat_ids.add(update.message.chat.id)
            elif update.edited_message:
                chat_ids.add(update.edited_message.chat.id)
            elif update.channel_post:
                chat_ids.add(update.channel_post.chat.id)
            elif update.edited_channel_post:
                chat_ids.add(update.edited_channel_post.chat.id)
            elif update.my_chat_member:
                chat_ids.add(update.my_chat_member.chat.id)

        # Process each chat
        synced_count = 0
        for chat_id in chat_ids:
            try:
                # Skip private chats (only want groups/channels)
                if chat_id > 0:
                    continue

                # Get chat info
                chat_info = await bot.get_chat(chat_id)

                # Create or update chat in database
                await db.get_or_create_chat(
                    chat_id=chat_id,
                    title=chat_info.title or chat_info.full_name or f"Chat {chat_id}",
                    chat_type=chat_info.type
                )

                # Add bot as chat member
                await db.get_or_create_user(
                    user_id=bot_user_id,
                    username=bot_info.username,
                    first_name=bot_info.first_name
                )

                await db.add_chat_member(chat_id, bot_user_id)
                synced_count += 1

                logger.info(f"Synced chat: {chat_info.title} ({chat_id})")

            except Exception as e:
                logger.error(f"Error syncing chat {chat_id}: {e}")

        logger.info(f"Chat synchronization complete: {synced_count} chats synced")

    except Exception as e:
        logger.error(f"Error during chat synchronization: {e}")


async def get_chat_list() -> None:
    """
    Get list of all chats where bot is a member.

    This is a diagnostic function that logs chat information.
    """
    bot = get_bot()
    db = get_database()

    logger.info("Getting chat list...")

    try:
        # Get chats from database
        chats = await db.get_chats(active_only=False, limit=100)

        if not chats:
            logger.warning("⚠️ No chats found in database!")
            logger.info("Bot needs to be added to groups/channels first")
            return

        logger.info(f"Found {len(chats)} chat(s) in database:")
        for chat in chats:
            logger.info(f"  - {chat['title']} (ID: {chat['id']}, Type: {chat['chat_type']})")

            # Check if bot is still a member
            try:
                chat_info = await bot.get_chat(chat['id'])
                logger.info(f"    ✓ Bot is still a member")
            except Exception as e:
                logger.warning(f"    ✗ Bot is NOT a member: {e}")

    except Exception as e:
        logger.error(f"Error getting chat list: {e}")


async def shutdown() -> None:
    """
    Bot shutdown hook.

    Stops scheduler, closes LLM client, closes bot session.
    """
    logger.info("Bot shutting down...")

    # Stop scheduler
    from app.bot.scheduler import stop_scheduler
    await stop_scheduler()
    logger.info("Scheduler stopped")

    # Close LLM client
    from app.core.llm import close_llm_client
    await close_llm_client()
    logger.info("LLM client closed")

    # Close bot session
    bot = get_bot()
    await bot.session.close()
    logger.info("Bot session closed")

    logger.info("Bot shutdown complete")


async def close_bot() -> None:
    """
    Close bot and dispatcher instances.

    Useful for testing or manual cleanup.
    """
    global _bot, _dispatcher

    if _bot is not None:
        await _bot.session.close()
        _bot = None

    if _dispatcher is not None:
        # Dispatcher doesn't have a close method in aiogram 3.x
        _dispatcher = None

    logger.info("Bot instances closed")


def register_handlers(dispatcher: Dispatcher) -> None:
    """
    Register all bot handlers.

    Args:
        dispatcher: Dispatcher instance
    """
    from app.bot import handlers

    # Register command handlers
    dispatcher.include_routers(handlers.command_router)
    dispatcher.include_routers(handlers.message_router)
    dispatcher.include_routers(handlers.callback_router)
    dispatcher.include_routers(handlers.chat_member_router)

    logger.info("Handlers registered")


def register_middleware(dispatcher: Dispatcher) -> None:
    """
    Register middleware.

    Args:
        dispatcher: Dispatcher instance
    """
    from app.bot.middleware import (
        DatabaseMiddleware,
        RateLimitMiddleware,
    )

    # Outer middleware runs first
    dispatcher.update.outer_middleware(DatabaseMiddleware())
    dispatcher.update.middleware(RateLimitMiddleware(get_rate_limiter()))

    logger.info("Middleware registered")
