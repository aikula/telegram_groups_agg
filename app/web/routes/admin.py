"""
Admin Routes - Superadmin panel endpoints (v2.0)

Accessible only by superadmin users.
Provides global statistics, notifications, and audit log access.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class GlobalStatsResponse(BaseModel):
    """Global statistics response model."""
    total_chats: int
    active_chats: int
    total_messages: int
    total_users: int
    messages_today: int
    messages_this_week: int
    top_chats_by_messages: List[dict]
    storage_size_mb: Optional[float] = None


class NotifyRequest(BaseModel):
    """Notification request model."""
    chat_ids: Optional[List[int]] = Field(None, description="Specific chat IDs to notify (empty = all active chats)")
    message: str = Field(..., min_length=1, max_length=4096, description="Message text to send")


class NotifyResponse(BaseModel):
    """Notification response model."""
    success: bool
    targeted_chats: int
    sent_count: int
    failed_count: int
    errors: List[str] = []


class AuditLogEntry(BaseModel):
    """Audit log entry model."""
    id: int
    timestamp: str
    user_id: Optional[int] = None
    action: str
    chat_id: Optional[int] = None
    details: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Audit log response model."""
    total_entries: int
    page: int
    page_size: int
    entries: List[AuditLogEntry]


# ============================================================================
# Helper Functions
# ============================================================================

async def require_superadmin(request: Request) -> dict:
    """
    Verify that the current user is a superadmin.

    Args:
        request: FastAPI request object

    Returns:
        User info dict if superadmin

    Raises:
        HTTPException: If not authenticated or not superadmin
    """
    from app.web.middleware import required_auth
    from app.web.auth import UserInfo

    user: UserInfo = await required_auth(request)

    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    return {
        "user_id": user.user_id,
        "username": user.username,
        "is_superadmin": True
    }


async def send_notification_to_chat(bot, chat_id: int, message: str) -> tuple[bool, str]:
    """
    Send notification message to a specific chat.

    Args:
        bot: Aiogram Bot instance
        chat_id: Target chat ID
        message: Message text

    Returns:
        Tuple of (success, error_message)
    """
    try:
        from aiogram.types import SendMessage
        await bot.send_message(chat_id, message)
        return True, ""
    except Exception as e:
        logger.error(f"Failed to send notification to chat {chat_id}: {e}")
        return False, str(e)


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.get("/stats", response_model=GlobalStatsResponse)
async def get_global_stats(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Get global statistics across all chats.

    Requires superadmin access.

    Returns:
        Global statistics including total chats, messages, users, and top chats
    """
    # Verify superadmin access
    await require_superadmin(request)

    db = request.app.state.db

    # Get all chats
    all_chats = await db.get_chats(active_only=False, limit=10000)
    active_chats = await db.get_chats(active_only=True, limit=10000)

    # Count total messages
    messages = await db.get_messages(limit=1000000, exclude_deleted=True)
    total_messages = len(messages)

    # Count messages today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = [
        m for m in messages
        if m.get('timestamp')
        and (
            (
                isinstance(m['timestamp'], str) and
                datetime.fromisoformat(m['timestamp'].replace('Z', '+00:00')) >= today_start
            )
            or (
                isinstance(m['timestamp'], datetime) and
                m['timestamp'] >= today_start
            )
        )
    ]

    # Count messages this week
    week_start = datetime.now() - timedelta(days=7)
    messages_this_week = [
        m for m in messages
        if m.get('timestamp')
        and (
            (
                isinstance(m['timestamp'], str) and
                datetime.fromisoformat(m['timestamp'].replace('Z', '+00:00')) >= week_start
            )
            or (
                isinstance(m['timestamp'], datetime) and
                m['timestamp'] >= week_start
            )
        )
    ]

    # Get unique users
    unique_users = set()
    for msg in messages:
        if msg.get('user_id'):
            unique_users.add(msg['user_id'])

    # Get top chats by message count
    chat_message_counts = {}
    for msg in messages:
        chat_id = msg.get('chat_id')
        if chat_id:
            chat_message_counts[chat_id] = chat_message_counts.get(chat_id, 0) + 1

    top_chats = []
    for chat_id, count in sorted(chat_message_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        chat = await db.get_chat_by_id(chat_id)
        if chat:
            top_chats.append({
                "chat_id": chat_id,
                "title": chat.get('title', f'Chat {chat_id}'),
                "message_count": count
            })

    # Calculate storage size (estimate)
    storage_size_mb = None
    try:
        import os
        db_path = db.db_path
        if os.path.exists(db_path):
            storage_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    except Exception:
        pass

    return GlobalStatsResponse(
        total_chats=len(all_chats),
        active_chats=len(active_chats),
        total_messages=total_messages,
        total_users=len(unique_users),
        messages_today=len(messages_today),
        messages_this_week=len(messages_this_week),
        top_chats_by_messages=top_chats,
        storage_size_mb=storage_size_mb
    )


@router.post("/notify", response_model=NotifyResponse)
async def send_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    notify_data: NotifyRequest
):
    """
    Send notification to chats.

    Requires superadmin access.

    Request body:
        chat_ids: Optional list of specific chat IDs (if not provided, sends to all active chats)
        message: Message text to send (max 4096 characters)

    Returns:
        Notification result with sent/failed counts
    """
    # Verify superadmin access
    admin_user = await require_superadmin(request)

    db = request.app.state.db
    bot = request.app.state.bot

    if not bot:
        raise HTTPException(status_code=503, detail="Bot is not available. Notifications can only be sent when the bot is running.")

    # Determine target chats
    if notify_data.chat_ids:
        # Specific chats provided
        target_chats = []
        for chat_id in notify_data.chat_ids:
            chat = await db.get_chat_by_id(chat_id)
            if chat:
                target_chats.append(chat)
    else:
        # Send to all active chats
        target_chats = await db.get_chats(active_only=True, limit=1000)

    if not target_chats:
        return NotifyResponse(
            success=True,
            targeted_chats=0,
            sent_count=0,
            failed_count=0
        )

    # Log the notification action
    await db.audit_log(
        user_id=admin_user["user_id"],
        action="admin_notify",
        details={
            "username": admin_user["username"],
            "message": f"Sending notification to {len(target_chats)} chats: {notify_data.message[:100]}..."
        }
    )

    # Send notifications
    sent_count = 0
    failed_count = 0
    errors = []

    for chat in target_chats:
        chat_id = chat["id"]
        success, error = await send_notification_to_chat(bot, chat_id, notify_data.message)

        if success:
            sent_count += 1
        else:
            failed_count += 1
            errors.append(f"Chat {chat_id}: {error}")

    return NotifyResponse(
        success=failed_count == 0,
        targeted_chats=len(target_chats),
        sent_count=sent_count,
        failed_count=failed_count,
        errors=errors
    )


@router.get("/audit", response_model=AuditLogResponse)
async def get_audit_log(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    days: Optional[int] = Query(None, ge=1, le=365, description="Filter by last N days")
):
    """
    Get audit log entries.

    Requires superadmin access.

    Query parameters:
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 500)
        action: Filter by specific action (optional)
        user_id: Filter by specific user (optional)
        days: Only show entries from last N days (optional)

    Returns:
        Paginated audit log entries
    """
    # Verify superadmin access
    await require_superadmin(request)

    db = request.app.state.db

    # Build filter conditions
    conditions = []
    params = []

    if action:
        conditions.append("action LIKE ?")
        params.append(f"%{action}%")

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    if days:
        cutoff_date = datetime.now() - timedelta(days=days)
        conditions.append("timestamp >= ?")
        params.append(cutoff_date.isoformat())

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Get total count
    count_query = f"SELECT COUNT(*) as count FROM audit_log WHERE {where_clause}"
    result = await db.execute_query(count_query, tuple(params))
    total_entries = result[0]["count"] if result else 0

    # Get paginated entries
    offset = (page - 1) * page_size
    query = f"""
        SELECT * FROM audit_log
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])

    rows = await db.execute_query(query, tuple(params))

    entries = []
    for row in rows:
        # Parse details JSON if present
        details = row.get("details")
        if details and isinstance(details, str):
            try:
                import json
                details = json.loads(details)
            except Exception:
                pass

        entries.append(AuditLogEntry(
            id=row["id"],
            timestamp=row.get("timestamp", ""),
            user_id=row.get("user_id"),
            action=row.get("action", ""),
            chat_id=row.get("chat_id"),
            details=str(details) if details else None
        ))

    return AuditLogResponse(
        total_entries=total_entries,
        page=page,
        page_size=page_size,
        entries=entries
    )
