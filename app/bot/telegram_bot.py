"""
Telegram Bot - Main bot class integrating all components
"""

import logging
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
)
from app.llm.openrouter import create_openrouter_client
from app.bot.handlers import create_handlers
from app.bot.scheduler import create_scheduler

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Main Telegram bot class.

    Integrates:
    - Message handlers
    - LLM client for QA and summaries
    - Scheduler for daily tasks
    """

    def __init__(self, token: str, db, config=None):
        """
        Initialize the Telegram bot.

        Args:
            token: Telegram bot token from BotFather
            db: Database instance
            config: Application configuration (Settings object)
        """
        self.token = token
        self.db = db
        self.config = config

        # Create the Telegram Application
        self.application = Application.builder().token(token).build()

        # Initialize LLM client
        self.llm_client = create_openrouter_client(
            api_key=config.openrouter_api_key if config else "",
            model=config.openrouter_model if config else None
        )

        # Create handlers
        self.handlers = create_handlers(
            db=db,
            llm_client=self.llm_client,
            config=config
        )

        # Scheduler (will be initialized later)
        self.scheduler = None

        # Register all handlers
        self._register_handlers()

        logger.info("Telegram bot initialized successfully")

    def _register_handlers(self):
        """
        Register all message and command handlers.
        """
        app = self.application

        # Command handlers
        app.add_handler(CommandHandler("start", self.handlers.handle_command_start))
        app.add_handler(CommandHandler("help", self.handlers.handle_command_help))
        app.add_handler(CommandHandler("stats", self.handlers.handle_command_stats))

        # Message handlers
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handlers.handle_message
        ))

        # Handle photo/media messages with caption
        app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO,
            self.handlers.handle_message
        ))

        # Edited messages
        app.add_handler(MessageHandler(
            filters.UpdateType.EDITED_MESSAGE,
            self.handlers.handle_edited_message
        ))

        # Chat member updates (bot added/removed from chat)
        app.add_handler(ChatMemberHandler(
            self.handlers.handle_chat_member_update,
            ChatMemberHandler.CHAT_MEMBER
        ))

        # Bot's own status updates
        app.add_handler(ChatMemberHandler(
            self.handlers.handle_my_chat_member_update,
            ChatMemberHandler.MY_CHAT_MEMBER
        ))

        logger.info("All handlers registered")

    def setup_scheduler(self):
        """
        Initialize and start the scheduler for daily tasks.
        """
        if not self.config:
            logger.warning("No config provided, scheduler not started")
            return

        self.scheduler = create_scheduler(
            db=self.db,
            llm_client=self.llm_client,
            bot=self.application,
            config=self.config
        )

        self.scheduler.start()
        logger.info("Scheduler started")

    async def run_polling(self):
        """
        Start the bot using polling.

        This is the main entry point for running the bot.
        """
        logger.info("Starting bot polling...")

        # Setup scheduler if configured
        if self.config:
            self.setup_scheduler()

        # Start polling
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
            logger.info("Bot polling started successfully")

            # Keep the bot running
            # The application will run until stopped
            import asyncio
            while self.application.updater.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in bot polling: {e}", exc_info=True)
            raise

    async def stop(self):
        """
        Stop the bot gracefully.
        """
        logger.info("Stopping bot...")

        # Stop scheduler
        if self.scheduler:
            self.scheduler.shutdown()

        # Stop application
        if self.application.updater:
            await self.application.updater.stop()

        await self.application.stop()
        await self.application.shutdown()

        logger.info("Bot stopped")

    def get_application(self) -> Application:
        """
        Get the underlying Telegram Application instance.

        Returns:
            Application instance
        """
        return self.application

    def get_llm_client(self):
        """
        Get the LLM client instance.

        Returns:
            OpenRouterClient instance
        """
        return self.llm_client

    def get_scheduler(self):
        """
        Get the scheduler instance.

        Returns:
            BotScheduler instance or None
        """
        return self.scheduler

    async def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None):
        """
        Send a message to a chat.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Parse mode (e.g., 'Markdown', 'HTML')
        """
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}", exc_info=True)

    async def generate_manual_summary(self, chat_id: int) -> dict:
        """
        Generate a manual summary for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dictionary with 'summary' and 'recommendations' keys
        """
        if self.scheduler:
            return await self.scheduler.generate_manual_summary(chat_id)
        else:
            return {
                "summary": "Scheduler not available",
                "recommendations": ""
            }

    async def send_manual_summary(self, chat_id: int) -> bool:
        """
        Manually send a summary to a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            True if successful, False otherwise
        """
        if self.scheduler:
            return await self.scheduler.send_manual_summary(chat_id)
        return False

    def test_llm_connection(self) -> bool:
        """
        Test the connection to the LLM service.

        Returns:
            True if connection successful, False otherwise
        """
        return self.llm_client.test_connection()


def create_bot(token: str, db, config=None) -> TelegramBot:
    """
    Factory function to create a Telegram bot instance.

    Args:
        token: Telegram bot token
        db: Database instance
        config: Optional application configuration

    Returns:
        TelegramBot instance
    """
    return TelegramBot(token=token, db=db, config=config)
