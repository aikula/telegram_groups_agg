"""
Telegram Chat Analytics Bot - Main Entry Point
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
    try:
        logger.info("Starting Telegram Chat Analytics Bot...")
        
        # Import after adding to path
        from app.config import settings
        from app.database import Database
        from app.bot.telegram_bot import TelegramBot
        from app.web.app import create_app
        import uvicorn
        
        # Initialize database
        logger.info("Initializing database...")
        db = Database(settings.database_url.replace('sqlite:///', ''))
        db.init()
        
        # Create Telegram bot
        logger.info("Creating Telegram bot...")
        bot = TelegramBot(token=settings.telegram_bot_token, db=db, config=settings)
        
        # Create FastAPI app
        logger.info("Creating FastAPI app...")
        app = create_app(db=db, config=settings)
        
        # Run bot and web server
        logger.info(f"Starting services on {settings.web_host}:{settings.web_port}")
        
        # Create tasks
        bot_task = asyncio.create_task(bot.run_polling())
        
        config = uvicorn.Config(
            app=app,
            host=settings.web_host,
            port=settings.web_port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        
        logger.info("✅ All services started successfully!")
        
        # Wait for tasks
        await asyncio.gather(bot_task, server_task)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
