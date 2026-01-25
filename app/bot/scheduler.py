"""
Bot Scheduler - Scheduled tasks for daily summaries and reports
"""

import logging
from datetime import datetime, time
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone
from app.bot.utils import format_summary_message, truncate_text

logger = logging.getLogger(__name__)


class BotScheduler:
    """
    Scheduler for automated bot tasks.

    Handles:
    - Daily summary generation at configured time
    - Coaching recommendations
    """

    def __init__(self, db, llm_client, bot, config):
        """
        Initialize the scheduler.

        Args:
            db: Database instance
            llm_client: OpenRouter LLM client
            bot: Telegram Bot Application instance
            config: Application configuration (Settings object)
        """
        self.db = db
        self.llm_client = llm_client
        self.bot = bot
        self.config = config

        # Parse timezone
        self.timezone = pytz_timezone(config.timezone)

        # Create scheduler
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)

        logger.info(f"Scheduler initialized with timezone: {config.timezone}")

    def start(self):
        """
        Start the scheduler and add all jobs.
        """
        try:
            # Add daily summary job
            self._add_daily_summary_job()

            # Start the scheduler
            self.scheduler.start()
            logger.info("Scheduler started successfully")

        except Exception as e:
            logger.error(f"Error starting scheduler: {e}", exc_info=True)
            raise

    def shutdown(self):
        """
        Shutdown the scheduler gracefully.
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown complete")

    def _add_daily_summary_job(self):
        """
        Add the daily summary job to the scheduler.
        """
        # Parse the summary time from config (format: "HH:MM")
        try:
            hour, minute = self._parse_time(self.config.summary_time)
        except ValueError as e:
            logger.warning(f"Invalid summary time format: {self.config.summary_time}, using default 16:00")
            hour, minute = 16, 0

        # Create cron trigger for daily execution
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)

        # Add job
        self.scheduler.add_job(
            self._generate_all_summaries,
            trigger=trigger,
            id='daily_summary',
            name='Daily Chat Summary',
            replace_existing=True
        )

        logger.info(f"Daily summary job scheduled for {hour:02d}:{minute:02d} {self.config.timezone}")

    def _parse_time(self, time_str: str) -> tuple:
        """
        Parse time string in "HH:MM" format.

        Args:
            time_str: Time string

        Returns:
            Tuple of (hour, minute)

        Raises:
            ValueError: If format is invalid
        """
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError("Time must be in HH:MM format")
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid hour or minute")
            return hour, minute
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid time format: {time_str}") from e

    async def _generate_all_summaries(self):
        """
        Generate and send daily summaries for all active chats.

        This is the main job function called by the scheduler.
        """
        logger.info("Starting daily summary generation...")

        try:
            # Get all active chats
            chats = self.db.get_chats(active_only=True)

            if not chats:
                logger.info("No active chats found")
                return

            logger.info(f"Found {len(chats)} active chats")

            # Generate summary for each chat
            for chat in chats:
                chat_id = chat.get('chat_id')
                chat_name = chat.get('chat_name', f'chat_{chat_id}')

                try:
                    await self._generate_and_send_summary(chat_id, chat_name)

                except Exception as e:
                    logger.error(f"Error generating summary for chat {chat_id}: {e}", exc_info=True)

            logger.info("Daily summary generation complete")

        except Exception as e:
            logger.error(f"Error in daily summary job: {e}", exc_info=True)

    async def _generate_and_send_summary(self, chat_id: int, chat_name: str):
        """
        Generate and send summary for a specific chat.

        Args:
            chat_id: Telegram chat ID
            chat_name: Chat display name
        """
        logger.info(f"Generating summary for chat {chat_name} ({chat_id})")

        # Get messages from the configured number of days
        messages = self.db.get_messages(
            chat_id=chat_id,
            days=self.config.summary_days,
            exclude_deleted=True
        )

        if not messages:
            logger.info(f"No messages found for chat {chat_id} in last {self.config.summary_days} days")
            return

        logger.info(f"Found {len(messages)} messages for chat {chat_id}")

        # Generate summary
        summary = self.llm_client.generate_summary(messages=messages, language="ru")

        # Generate recommendations
        recommendations = self.llm_client.generate_recommendations(messages=messages, language="ru")

        # Format the message
        message_text = format_summary_message(summary, recommendations)

        # Truncate if too long
        message_text = truncate_text(message_text, max_length=4000)

        # Send to chat
        try:
            await self.bot.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown"
            )
            logger.info(f"Summary sent to chat {chat_id}")

        except Exception as e:
            logger.error(f"Error sending summary to chat {chat_id}: {e}", exc_info=True)

            # Try without markdown if there was a parse error
            try:
                plain_message = format_summary_message(summary, recommendations).replace("*", "")
                await self.bot.bot.send_message(
                    chat_id=chat_id,
                    text=plain_message
                )
                logger.info(f"Plain text summary sent to chat {chat_id}")

            except Exception as e2:
                logger.error(f"Error sending plain summary to chat {chat_id}: {e2}", exc_info=True)

    async def generate_manual_summary(self, chat_id: int) -> dict:
        """
        Manually generate summary for a specific chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dictionary with 'summary' and 'recommendations' keys
        """
        logger.info(f"Generating manual summary for chat {chat_id}")

        # Get messages
        messages = self.db.get_messages(
            chat_id=chat_id,
            days=self.config.summary_days,
            exclude_deleted=True
        )

        if not messages:
            return {
                "summary": "Нет сообщений за указанный период.",
                "recommendations": "Недостаточно данных для анализа."
            }

        # Generate summary and recommendations
        summary = self.llm_client.generate_summary(messages=messages, language="ru")
        recommendations = self.llm_client.generate_recommendations(messages=messages, language="ru")

        return {
            "summary": summary,
            "recommendations": recommendations
        }

    async def send_manual_summary(self, chat_id: int) -> bool:
        """
        Manually trigger summary generation and sending for a specific chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get chat info
            chats = self.db.get_chats(active_only=True)
            chat = next((c for c in chats if c.get('chat_id') == chat_id), None)

            chat_name = chat.get('chat_name', f'chat_{chat_id}') if chat else f'chat_{chat_id}'

            # Generate and send
            await self._generate_and_send_summary(chat_id, chat_name)
            return True

        except Exception as e:
            logger.error(f"Error sending manual summary for chat {chat_id}: {e}", exc_info=True)
            return False

    def get_next_run_time(self) -> Optional[datetime]:
        """
        Get the next scheduled run time for the daily summary.

        Returns:
            Next run datetime or None if not scheduled
        """
        job = self.scheduler.get_job('daily_summary')
        if job:
            return job.next_run_time
        return None

    def get_jobs(self) -> list:
        """
        Get all scheduled jobs.

        Returns:
            List of job dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger)
            })
        return jobs


def create_scheduler(db, llm_client, bot, config):
    """
    Factory function to create a BotScheduler instance.

    Args:
        db: Database instance
        llm_client: OpenRouter LLM client
        bot: Telegram Bot Application instance
        config: Application configuration

    Returns:
        BotScheduler instance
    """
    return BotScheduler(
        db=db,
        llm_client=llm_client,
        bot=bot,
        config=config
    )
