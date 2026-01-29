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

    # Get all chats (lightweight)
    all_chats = await db.get_chats(active_only=False, limit=10000)
    active_chats = await db.get_chats(active_only=True, limit=10000)

    # Use SQL aggregation for stats (much faster than loading all messages)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = datetime.now() - timedelta(days=7)

    # Total messages
    total_result = await db.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE reply_to_id IS NULL"
    )
    total_messages = total_result[0]["count"] if total_result else 0

    # Messages today
    today_result = await db.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE reply_to_id IS NULL AND timestamp >= ?",
        (today_start.isoformat(),)
    )
    messages_today = today_result[0]["count"] if today_result else 0

    # Messages this week
    week_result = await db.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE reply_to_id IS NULL AND timestamp >= ?",
        (week_start.isoformat(),)
    )
    messages_this_week = week_result[0]["count"] if week_result else 0

    # Unique users
    users_result = await db.execute_query(
        "SELECT COUNT(DISTINCT user_id) as count FROM messages WHERE reply_to_id IS NULL"
    )
    total_users = users_result[0]["count"] if users_result else 0

    # Top chats by message count (single query with JOIN)
    top_chats_result = await db.execute_query("""
        SELECT
            m.chat_id,
            c.title,
            COUNT(*) as message_count
        FROM messages m
        LEFT JOIN chats c ON m.chat_id = c.chat_id
        WHERE m.reply_to_id IS NULL
        GROUP BY m.chat_id, c.title
        ORDER BY message_count DESC
        LIMIT 10
    """)

    top_chats = [
        {
            "chat_id": row["chat_id"],
            "title": row.get("title") or f'Chat {row["chat_id"]}',
            "message_count": row["message_count"]
        }
        for row in top_chats_result
    ]

    # Calculate storage size (estimate) - use executor to avoid blocking
    storage_size_mb = None
    try:
        import os
        import asyncio

        db_path = db.db_path
        loop = asyncio.get_event_loop()

        # Run blocking file stat in executor to avoid blocking event loop
        storage_size_mb = await loop.run_in_executor(
            None,
            lambda: round(os.path.getsize(db_path) / (1024 * 1024), 2) if os.path.exists(db_path) else None
        )
    except Exception:
        pass

    return GlobalStatsResponse(
        total_chats=len(all_chats),
        active_chats=len(active_chats),
        total_messages=total_messages,
        total_users=total_users,
        messages_today=messages_today,
        messages_this_week=messages_this_week,
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


@router.get("/users")
async def get_users_stats(request: Request):
    """
    Get users statistics (superadmin only).

    Returns list of users with their chat count, message count, and LLM usage.
    """
    await require_superadmin(request)

    db = request.app.state.db

    # Query to get users with their stats
    query = """
        SELECT
            u.id as user_id,
            u.username,
            u.first_name,
            COUNT(DISTINCT cm.chat_id) as chat_count,
            COUNT(DISTINCT m.id) as message_count,
            (SELECT COUNT(*) FROM llm_usage WHERE user_id = u.id) as llm_requests
        FROM users u
        LEFT JOIN chat_members cm ON COALESCE(cm.user_id, u.id) = u.id
        LEFT JOIN messages m ON m.user_id = u.id
        GROUP BY u.id
        ORDER BY message_count DESC
    """

    rows = await db.execute_query(query)

    return [
        {
            "user_id": row["user_id"],
            "username": row.get("username"),
            "chat_count": row.get("chat_count", 0),
            "message_count": row.get("message_count", 0),
            "llm_requests": row.get("llm_requests", 0)
        }
        for row in rows
    ]


@router.get("/feedback")
async def get_admin_feedback(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status")
):
    """
    Get all feedback entries (superadmin only).

    This endpoint provides the same data as /api/feedback but is explicitly
    for the admin panel. Maintains consistency with admin routes structure.
    """
    await require_superadmin(request)

    db = request.app.state.db

    feedback_list = await db.get_feedback(status=status)

    return [
        {
            "id": item['id'],
            "user_id": item.get('user_id'),
            "username": item.get('username'),
            "chat_id": item.get('chat_id'),
            "chat_title": item.get('chat_title'),
            "source": item['source'],
            "category": item['category'],
            "message": item['message'],
            "rating": item.get('rating'),
            "status": item['status'],
            "created_at": item['created_at'],
            "resolved_at": item.get('resolved_at')
        }
        for item in feedback_list
    ]


# ============================================================================
# Skill Prompts Management (v2.2)
# ============================================================================

class SkillPromptUpdate(BaseModel):
    """Skill prompt update model."""
    prompt: str = Field(..., min_length=50, max_length=50000, description="Prompt text")
    is_active: bool = True
    change_reason: Optional[str] = Field(None, max_length=500, description="Reason for change")


class SkillPromptResponse(BaseModel):
    """Skill prompt response model."""
    skill_name: str
    prompt: str
    is_active: bool
    version: int
    updated_at: str


@router.get("/skill-prompts")
async def get_skill_prompts(request: Request):
    """
    Get all skill prompts (superadmin only).

    Returns list of skill prompts with their status.
    """
    await require_superadmin(request)

    db = request.app.state.db
    prompts = await db.get_all_skill_prompts()

    return prompts


@router.get("/skill-prompts/{skill_name}/history")
async def get_skill_prompt_history(
    request: Request,
    skill_name: str,
    limit: int = 20
):
    """
    Get version history for a skill prompt (superadmin only).

    Path parameters:
        skill_name: Skill name ('qa', 'summary', 'coach', 'analytics')

    Query parameters:
        limit: Maximum versions to return (default: 20)

    Returns list of prompt versions.
    """
    await require_superadmin(request)

    if skill_name not in ['qa', 'summary', 'coach', 'analytics', 'about']:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    db = request.app.state.db
    history = await db.get_skill_prompt_history(skill_name, limit)

    return history


@router.put("/skill-prompts/{skill_name}")
async def update_skill_prompt(
    request: Request,
    skill_name: str,
    data: SkillPromptUpdate
):
    """
    Update a skill prompt (superadmin only).

    Path parameters:
        skill_name: Skill name ('qa', 'summary', 'coach', 'analytics')

    Request body:
        prompt: New prompt text
        is_active: Whether to use this custom prompt
        change_reason: Optional reason for the change

    Returns updated prompt info with version.
    """
    user = await require_superadmin(request)

    if skill_name not in ['qa', 'summary', 'coach', 'analytics', 'about']:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    db = request.app.state.db

    try:
        new_version = await db.update_skill_prompt(
            skill_name=skill_name,
            prompt=data.prompt,
            user_id=user['user_id'],
            change_reason=data.change_reason,
            is_active=data.is_active
        )

        return SkillPromptResponse(
            skill_name=skill_name,
            prompt=data.prompt,
            is_active=data.is_active,
            version=new_version,
            updated_at=datetime.now().isoformat()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/skill-prompts/{skill_name}/reset")
async def reset_skill_prompt(
    request: Request,
    skill_name: str
):
    """
    Reset a skill prompt to default (superadmin only).

    This deactivates any custom prompt and reverts to the built-in default.

    Path parameters:
        skill_name: Skill name ('qa', 'summary', 'coach', 'analytics')

    Returns success status.
    """
    user = await require_superadmin(request)

    if skill_name not in ['qa', 'summary', 'coach', 'analytics', 'about']:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    db = request.app.state.db
    success = await db.reset_skill_prompt(skill_name, user['user_id'])

    if not success:
        raise HTTPException(status_code=404, detail=f"No custom prompt found for '{skill_name}'")

    return {"skill_name": skill_name, "reset": True}
