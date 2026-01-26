"""
Telegram Chat Analytics Bot - Main Entry Point
Uses aiogram 3.4+ for Telegram bot integration
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the application"""
    shutdown_func = None

    try:
        logger.info("Starting Telegram Chat Analytics Bot...")

        # Import after adding to path
        from app.config import settings
        from app.bot.bot import (
            get_bot,
            get_dispatcher,
            startup,
            shutdown,
            register_handlers,
            register_middleware
        )
        from app.web.app import get_app
        import uvicorn

        # Store shutdown function
        shutdown_func = shutdown

        # Setup bot dispatcher
        bot = get_bot()
        dispatcher = get_dispatcher()

        # Register handlers and middleware
        register_handlers(dispatcher)
        register_middleware(dispatcher)

        # Create FastAPI app
        logger.info("Creating FastAPI app...")
        web_app = get_app()

        # Store bot in app state for webhook access
        web_app.state.bot = bot
        web_app.state.dispatcher = dispatcher
        logger.info("Bot instance stored in app state for webhook")

        # Run bot startup
        await startup()

        # Run bot and web server
        logger.info(f"Starting services on {settings.host}:{settings.port}")

        # Bot will receive updates via webhook, not polling
        # The webhook endpoint is at /webhook/telegram

        config = uvicorn.Config(
            app=web_app,
            host=settings.host,
            port=settings.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        logger.info("✅ All services started successfully!")
        logger.info("📡 Webhook mode: Bot will receive updates via /webhook/telegram")

        # Wait for server (webhook will handle bot updates)
        await server_task

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise
    finally:
        # Run shutdown if available
        if shutdown_func:
            await shutdown_func()


if __name__ == "__main__":
    asyncio.run(main())
