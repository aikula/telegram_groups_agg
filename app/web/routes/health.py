"""
Health Routes - Health check and system status (v2.0)
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


class DetailedHealthResponse(BaseModel):
    """Detailed health check response."""
    status: str
    timestamp: str
    version: str
    database: dict
    bot: dict
    scheduler: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Basic health check endpoint.

    Returns:
        Health status
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check(request: Request):
    """
    Detailed health check with component status.

    Returns:
        Detailed health status including database, bot, and scheduler
    """
    db = request.app.state.db
    bot = request.app.state.bot

    # Database health
    db_status = {
        "status": "unknown",
        "message": ""
    }

    try:
        # Try to get a connection
        async with db.get_connection() as conn:
            await conn.execute("SELECT 1")
        db_status["status"] = "ok"
        db_status["message"] = "Database connection successful"
    except Exception as e:
        db_status["status"] = "error"
        db_status["message"] = str(e)

    # Bot health
    bot_status = {
        "status": "unknown",
        "message": ""
    }

    if bot is None:
        bot_status["status"] = "not_initialized"
        bot_status["message"] = "Bot not initialized"
    else:
        bot_status["status"] = "ok"
        bot_status["message"] = "Bot running"

    # Scheduler health
    scheduler_status = {
        "status": "unknown",
        "message": ""
    }

    try:
        from app.bot.scheduler import get_scheduler
        scheduler = get_scheduler()

        if scheduler is None:
            scheduler_status["status"] = "not_initialized"
            scheduler_status["message"] = "Scheduler not initialized"
        elif scheduler.running:
            scheduler_status["status"] = "ok"
            scheduler_status["message"] = "Scheduler running"
            scheduler_status["jobs"] = len(scheduler.get_jobs())
        else:
            scheduler_status["status"] = "stopped"
            scheduler_status["message"] = "Scheduler not running"
    except Exception as e:
        scheduler_status["status"] = "error"
        scheduler_status["message"] = str(e)

    return DetailedHealthResponse(
        status="ok" if db_status["status"] == "ok" else "degraded",
        timestamp=datetime.now().isoformat(),
        version="2.0.0",
        database=db_status,
        bot=bot_status,
        scheduler=scheduler_status
    )


@router.get("/status")
async def system_status(request: Request):
    """
    Get overall system status and statistics.

    Returns:
        System status with counts and statistics
    """
    db = request.app.state.db

    try:
        # Get database stats
        async with db.get_connection() as conn:
            # Chat count
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM chats WHERE deleted_at IS NULL"
            )
            chat_count = (await cursor.fetchone())[0]

            # Message count
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM messages WHERE deleted_at IS NULL"
            )
            message_count = (await cursor.fetchone())[0]

            # User count
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM users"
            )
            user_count = (await cursor.fetchone())[0]

        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "statistics": {
                "chats": chat_count,
                "messages": message_count,
                "users": user_count
            }
        }

    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }
