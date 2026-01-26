"""
API Routes - FastAPI route handlers for the web interface
"""

import logging
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header, Query, Body
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Request/Response Models
class MessageStatsResponse(BaseModel):
    """Response model for message statistics."""
    total_messages: int
    active_users: int
    days: int
    avg_per_day: float
    top_contributors: List[tuple]
    most_active_hour: Optional[int] = None


class ChatInfo(BaseModel):
    """Chat information model."""
    chat_id: int
    chat_name: str
    chat_type: str
    bot_added_at: Optional[str] = None


class SummaryResponse(BaseModel):
    """Response model for summary/recommendations."""
    summary: str
    recommendations: str


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: str


class LoginRequest(BaseModel):
    """Login request model for JSON body."""
    username: str
    password: str


def create_routes(db, auth_manager, bot_instance=None):
    """
    Create and configure API routes.

    Args:
        db: Database instance
        auth_manager: AuthManager instance
        bot_instance: Optional TelegramBot instance for manual summaries

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    async def get_token(authorization: str = Header(None)) -> Optional[str]:
        """Extract bearer token from Authorization header."""
        if authorization and authorization.startswith("Bearer "):
            return authorization[7:]
        return None

    async def verify_auth(token: str = Depends(get_token)) -> dict:
        """Verify authentication and return user info."""
        user = auth_manager.verify_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        return {"username": user.username}

    # ========== Auth Endpoints ==========

    @router.post("/api/auth/login")
    async def login(request: LoginRequest):
        """
        Authenticate user and return access token.

        JSON body expected with username and password.
        """
        logger.info(f"Login attempt for user: {request.username}")

        result = auth_manager.login(request.username, request.password)

        if not result:
            logger.warning(f"Failed login attempt for user: {request.username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")

        logger.info(f"Successful login for user: {request.username}")

        return {
            "access_token": result.access_token,
            "token_type": result.token_type,
            "username": result.username
        }

    @router.get("/api/auth/me")
    async def get_current_user(user: dict = Depends(verify_auth)):
        """Get current authenticated user info."""
        return user

    # ========== Stats Endpoints ==========

    @router.get("/api/stats/messages", response_model=MessageStatsResponse)
    async def get_message_stats(
        chat_id: Optional[int] = None,
        days: int = Query(default=7, ge=1, le=365),
        user: dict = Depends(verify_auth)
    ):
        """
        Get message statistics.

        Query params:
            chat_id: Filter by specific chat (optional)
            days: Number of days to analyze (default: 7, max: 365)
        """
        messages = await db.get_messages(chat_id=chat_id, days=days, exclude_deleted=True)

        if not messages:
            return MessageStatsResponse(
                total_messages=0,
                active_users=0,
                days=days,
                avg_per_day=0.0,
                top_contributors=[]
            )

        # Calculate statistics
        total_messages = len(messages)

        # Count by user
        user_counts = {}
        hour_counts = {}

        for msg in messages:
            # User counts
            username = msg.get('username') or msg.get('first_name', 'Unknown')
            user_counts[username] = user_counts.get(username, 0) + 1

            # Hour counts
            timestamp = msg.get('timestamp')
            if timestamp:
                if isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        dt = None
                else:
                    dt = timestamp

                if dt:
                    hour = dt.hour
                    hour_counts[hour] = hour_counts.get(hour, 0) + 1

        active_users = len(user_counts)
        avg_per_day = total_messages / days

        # Top contributors
        top_contributors = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Most active hour
        most_active_hour = None
        if hour_counts:
            most_active_hour = max(hour_counts.items(), key=lambda x: x[1])[0]

        return MessageStatsResponse(
            total_messages=total_messages,
            active_users=active_users,
            days=days,
            avg_per_day=round(avg_per_day, 1),
            top_contributors=top_contributors,
            most_active_hour=most_active_hour
        )

    # ========== Chat Endpoints ==========

    @router.get("/api/chats")
    async def get_chats(
        active_only: bool = True,
        user: dict = Depends(verify_auth)
    ):
        """
        Get list of all chats.

        Query params:
            active_only: Only return active chats (default: true)
        """
        chats = await db.get_chats(active_only=active_only)

        return [
            ChatInfo(
                chat_id=chat['chat_id'],
                chat_name=chat['chat_name'],
                chat_type=chat.get('chat_type', 'unknown'),
                bot_added_at=chat.get('bot_added_at')
            )
            for chat in chats
        ]

    # ========== Messages Endpoints ==========

    @router.get("/api/messages")
    async def get_messages(
        chat_id: Optional[int] = None,
        days: int = Query(default=7, ge=1, le=365),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        user: dict = Depends(verify_auth)
    ):
        """
        Get messages with filtering and pagination.

        Query params:
            chat_id: Filter by specific chat (optional)
            days: Number of days to look back (default: 7)
            limit: Maximum messages to return (default: 100)
            offset: Number of messages to skip (default: 0)
        """
        messages = await db.get_messages(chat_id=chat_id, days=days, exclude_deleted=True)

        # Apply pagination
        total = len(messages)
        paginated = messages[offset:offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "messages": paginated
        }

    # ========== Export Endpoints ==========

    @router.get("/api/export/csv")
    async def export_csv(
        chat_id: Optional[int] = None,
        days: int = Query(default=7, ge=1, le=365),
        user: dict = Depends(verify_auth)
    ):
        """
        Export messages to CSV format.

        Query params:
            chat_id: Filter by specific chat (optional)
            days: Number of days to export (default: 7)
        """
        messages = await db.get_messages(chat_id=chat_id, days=days, exclude_deleted=True)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            'timestamp', 'chat_id', 'user_id', 'username',
            'first_name', 'last_name', 'message_text'
        ])

        # Rows
        for msg in messages:
            writer.writerow([
                msg.get('timestamp', ''),
                msg.get('chat_id', ''),
                msg.get('user_id', ''),
                msg.get('username', ''),
                msg.get('first_name', ''),
                msg.get('last_name', ''),
                msg.get('message_text', '').replace('\n', ' ')
            ])

        # Create response
        output.seek(0)
        filename = f"messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    # ========== Summary Endpoints ==========

    @router.post("/api/summary/manual", response_model=SummaryResponse)
    async def manual_summary(
        chat_id: int,
        days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
        user: dict = Depends(verify_auth)
    ):
        """
        Manually trigger a summary generation for a chat.

        Query params:
            chat_id: Telegram chat ID
            days: Number of days to analyze (default: 7, max: 365)
        """
        if not bot_instance:
            raise HTTPException(status_code=503, detail="Bot not available")

        try:
            # Get messages for the specified days
            messages = await bot_instance.db.get_messages(
                chat_id=chat_id,
                days=days,
                exclude_deleted=True
            )

            if not messages:
                return SummaryResponse(
                    summary=f"Нет сообщений за последние {days} дней.",
                    recommendations="Недостаточно данных для анализа."
                )

            # Generate summary and recommendations
            summary = bot_instance.llm_client.generate_summary(messages, language="ru")
            recommendations = bot_instance.llm_client.generate_recommendations(messages, language="ru")

            return SummaryResponse(
                summary=summary,
                recommendations=recommendations
            )
        except Exception as e:
            logger.error(f"Error generating manual summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/summary/send")
    async def send_manual_summary(
        chat_id: int,
        days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
        user: dict = Depends(verify_auth)
    ):
        """
        Manually send a summary to a Telegram chat.

        Query params:
            chat_id: Telegram chat ID
            days: Number of days to analyze (default: 7, max: 365)
        """
        if not bot_instance:
            raise HTTPException(status_code=503, detail="Bot not available")

        try:
            # Get messages for the specified days
            messages = await bot_instance.db.get_messages(
                chat_id=chat_id,
                days=days,
                exclude_deleted=True
            )

            if not messages:
                return {"status": "error", "message": f"Нет сообщений за последние {days} дней"}

            # Generate summary and recommendations
            summary = bot_instance.llm_client.generate_summary(messages, language="ru")
            recommendations = bot_instance.llm_client.generate_recommendations(messages, language="ru")

            # Format and send
            from app.bot.utils import format_summary_message, truncate_text

            message_text = format_summary_message(summary, recommendations)
            message_text = truncate_text(message_text, max_length=4000)

            await bot_instance.application.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown"
            )

            return {"status": "ok", "message": f"Summary sent for {days} days"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sending manual summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/recommendations/manual", response_model=SummaryResponse)
    async def manual_recommendations(
        chat_id: int,
        days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
        user: dict = Depends(verify_auth)
    ):
        """
        Manually generate coaching recommendations for a chat.

        Query params:
            chat_id: Telegram chat ID
            days: Number of days to analyze (default: 7, max: 365)
        """
        try:
            # Use CoachSkill for recommendations
            from app.skills.coach import CoachSkill

            coach_skill = CoachSkill(db)
            result = await coach_skill.suggest_improvements(
                chat_id=chat_id,
                days=days,
                language="ru"
            )

            if not result.success:
                raise HTTPException(status_code=500, detail=result.error or "Failed to generate recommendations")

            return SummaryResponse(
                summary="",
                recommendations=result.text
            )

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ========== Health Check ==========

    @router.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    return router


def setup_error_handlers(app):
    """
    Setup global error handlers for the FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail}
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        """Handle general exceptions."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
