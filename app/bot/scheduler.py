"""
Bot scheduler - APScheduler for background tasks

Features:
- Daily summary generation at configured time
- AsyncIOScheduler integration with aiogram
- Job management (add, remove, list)
"""

import logging
from datetime import datetime, time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone

from app.core.db import get_database
from app.core.llm import get_llm_client
from app.bot.bot import get_bot
from app.core.i18n import get_text


logger = logging.getLogger(__name__)


# Singleton instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """
    Get scheduler singleton instance.

    Returns:
        AsyncIOScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=pytz_timezone("Europe/Moscow"))
        logger.info("Scheduler instance created")
    return _scheduler


async def start_scheduler() -> None:
    """
    Start the scheduler and register jobs.

    Initializes all scheduled tasks.
    """
    scheduler = get_scheduler()

    if scheduler.running:
        logger.warning("Scheduler already running")
        return

    # Add jobs
    _add_daily_summary_job(scheduler)

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """
    Stop the scheduler gracefully.

    Shuts down all jobs and closes scheduler.
    """
    global _scheduler

    if _scheduler is None:
        return

    if _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")

    _scheduler = None


def _add_daily_summary_job(scheduler: AsyncIOScheduler) -> None:
    """
    Add daily summary generation job.

    Runs at 16:00 Moscow time by default.
    """
    trigger = CronTrigger(hour=16, minute=0, timezone=pytz_timezone("Europe/Moscow"))

    scheduler.add_job(
        _generate_daily_summaries,
        trigger=trigger,
        id="daily_summary",
        name="Daily Chat Summary",
        replace_existing=True
    )

    logger.info("Daily summary job scheduled for 16:00 Moscow time")


async def _generate_daily_summaries() -> None:
    """
    Generate and send daily summaries for all active chats.

    This job runs automatically at the scheduled time.
    """
    logger.info("Starting daily summary generation...")

    db = get_database()
    bot = get_bot()

    try:
        # Get all chats with summary enabled
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT c.id, c.title, cs.language
                FROM chats c
                LEFT JOIN chat_settings cs ON c.id = cs.chat_id
                WHERE c.deleted_at IS NULL
                AND (cs.summary_enabled IS NULL OR cs.summary_enabled = 1)
                """
            )
            chats = await cursor.fetchall()

        if not chats:
            logger.info("No chats found with summary enabled")
            return

        logger.info(f"Found {len(chats)} chats with summary enabled")

        for chat_id, title, language in chats:
            try:
                await _generate_and_send_summary(db, bot, chat_id, title, language or "ru")
            except Exception as e:
                logger.error(f"Error generating summary for chat {chat_id}: {e}")

        logger.info("Daily summary generation complete")

    except Exception as e:
        logger.error(f"Error in daily summary job: {e}")


async def _generate_and_send_summary(
    db,
    bot,
    chat_id: int,
    title: str,
    language: str
) -> None:
    """
    Generate and send summary for a specific chat.

    Args:
        db: Database instance
        bot: Bot instance
        chat_id: Telegram chat ID
        title: Chat title
        language: Chat language
    """
    logger.info(f"Generating summary for chat {title} ({chat_id})")

    # Get messages from last 24 hours
    messages = await db.get_recent_messages(chat_id, limit=100, hours=24)

    if not messages:
        logger.info(f"No messages found for chat {chat_id} in last 24 hours")
        return

    logger.info(f"Found {len(messages)} messages for chat {chat_id}")

    # Format context
    context_text = "\n".join([
        f"[{msg.get('timestamp', '')}] {msg.get('username', 'User')}: {msg.get('content', '')}"
        for msg in messages
    ])

    # Generate summary
    llm = get_llm_client()

    try:
        result = await llm.generate(
            get_text(
                "summary.prompt",
                lang=language,
                messages=context_text
            )
        )

        # Send summary
        await bot.send_message(chat_id, result["text"])

        # Log usage
        await db.log_llm_usage(
            user_id=0,  # System message
            chat_id=chat_id,
            skill="summary",
            tokens_prompt=result["usage"]["prompt_tokens"],
            tokens_completion=result["usage"]["completion_tokens"],
            cost_usd=result.get("cost_usd", 0.0)
        )

        logger.info(f"Summary sent to chat {chat_id}")

    except Exception as e:
        logger.error(f"Error generating/sending summary for chat {chat_id}: {e}")


async def trigger_manual_summary(chat_id: int) -> bool:
    """
    Manually trigger summary generation for a specific chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        True if successful, False otherwise
    """
    db = get_database()
    bot = get_bot()

    try:
        # Get chat info
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT title FROM chats WHERE id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            title = row[0] if row else f"chat_{chat_id}"

        # Get chat language
        settings = await db.get_chat_settings(chat_id)
        language = settings.get("language", "ru") if settings else "ru"

        await _generate_and_send_summary(db, bot, chat_id, title, language)
        return True

    except Exception as e:
        logger.error(f"Error in manual summary for chat {chat_id}: {e}")
        return False


def get_scheduled_jobs() -> list:
    """
    Get list of all scheduled jobs.

    Returns:
        List of job info dictionaries
    """
    scheduler = get_scheduler()

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time,
        })

    return jobs
