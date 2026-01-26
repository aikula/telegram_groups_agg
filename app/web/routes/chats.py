"""
Chats Routes - Chat management endpoints (v2.0)
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class ChatInfo(BaseModel):
    """Chat information model."""
    chat_id: int
    title: str
    chat_type: str
    created_at: Optional[str] = None
    deleted_at: Optional[str] = None
    member_count: Optional[int] = None


class ChatSettings(BaseModel):
    """Chat settings model."""
    chat_id: int
    summary_enabled: bool
    coach_enabled: bool
    language: str


class ChatSettingsUpdate(BaseModel):
    """Chat settings update model."""
    summary_enabled: Optional[bool] = None
    coach_enabled: Optional[bool] = None
    language: Optional[str] = None


class ChatDetailResponse(BaseModel):
    """Chat detail response model."""
    chat: ChatInfo
    settings: ChatSettings
    message_count: int
    member_count: int


@router.get("/my-chats", response_model=List[ChatInfo])
async def get_my_chats(
    request: Request,
    active_only: bool = Query(default=True, description="Only return active chats"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum chats to return")
):
    """
    Get list of chats where current user is a member.

    For regular users: returns only their chats
    For superadmins: returns all chats

    Query parameters:
        active_only: Only return active chats (default: true)
        limit: Maximum chats to return (default: 100)

    Returns:
        List of chat information
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)
    db = request.app.state.db

    # Superadmins see all chats, regular users only see their chats
    if user.is_superadmin:
        chats = await db.get_chats(
            active_only=active_only,
            limit=limit
        )
    else:
        # Get only chats where user is a member
        chats = await db.get_user_chats(
            user_id=user.user_id,
            active_only=active_only,
            limit=limit
        )

    return [
        ChatInfo(
            chat_id=chat["id"],
            title=chat.get("title", "Unknown Chat"),
            chat_type=chat.get("chat_type", "unknown"),
            created_at=chat.get("created_at"),
            deleted_at=chat.get("deleted_at"),
            member_count=chat.get("member_count")
        )
        for chat in chats
    ]


@router.get("", response_model=List[ChatInfo])
async def get_chats(
    request: Request,
    active_only: bool = Query(default=True, description="Only return active chats"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum chats to return")
):
    """
    Get list of all chats (ADMIN ONLY).

    Query parameters:
        active_only: Only return active chats (default: true)
        limit: Maximum chats to return (default: 100)

    Returns:
        List of chat information
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)

    # Only superadmins can access this endpoint
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Admin access required")

    db = request.app.state.db

    chats = await db.get_chats(
        active_only=active_only,
        limit=limit
    )

    return [
        ChatInfo(
            chat_id=chat["id"],
            title=chat.get("title", "Unknown Chat"),
            chat_type=chat.get("chat_type", "unknown"),
            created_at=chat.get("created_at"),
            deleted_at=chat.get("deleted_at"),
            member_count=chat.get("member_count")
        )
        for chat in chats
    ]


@router.get("/{chat_id}", response_model=ChatDetailResponse)
async def get_chat_detail(request: Request, chat_id: int):
    """
    Get detailed information about a specific chat.

    Path parameters:
        chat_id: Telegram chat ID

    Returns:
        Detailed chat information including settings and stats
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Get chat info
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get chat settings
    settings_data = await db.get_chat_settings(chat_id)
    if not settings_data:
        settings_data = {
            "summary_enabled": 1,
            "coach_enabled": 1,
            "language": "ru"
        }

    # Get message count
    messages = await db.get_messages(chat_id=chat_id, exclude_deleted=True)
    message_count = len(messages)

    # Get member count
    members = await db.get_chat_members(chat_id)
    member_count = len(members)

    return ChatDetailResponse(
        chat=ChatInfo(
            chat_id=chat["id"],
            title=chat.get("title", "Unknown Chat"),
            chat_type=chat.get("chat_type", "unknown"),
            created_at=chat.get("created_at"),
            deleted_at=chat.get("deleted_at"),
            member_count=member_count
        ),
        settings=ChatSettings(
            chat_id=chat_id,
            summary_enabled=settings_data.get("summary_enabled", 1) == 1,
            coach_enabled=settings_data.get("coach_enabled", 1) == 1,
            language=settings_data.get("language", "ru")
        ),
        message_count=message_count,
        member_count=member_count
    )


@router.get("/{chat_id}/settings", response_model=ChatSettings)
async def get_chat_settings(request: Request, chat_id: int):
    """
    Get settings for a specific chat.

    Path parameters:
        chat_id: Telegram chat ID

    Returns:
        Chat settings
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Check chat exists
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get settings
    settings_data = await db.get_chat_settings(chat_id)
    if not settings_data:
        settings_data = {
            "summary_enabled": 1,
            "coach_enabled": 1,
            "language": "ru"
        }

    return ChatSettings(
        chat_id=chat_id,
        summary_enabled=settings_data.get("summary_enabled", 1) == 1,
        coach_enabled=settings_data.get("coach_enabled", 1) == 1,
        language=settings_data.get("language", "ru")
    )


@router.put("/{chat_id}/settings", response_model=ChatSettings)
async def update_chat_settings(request: Request, chat_id: int, update: ChatSettingsUpdate):
    """
    Update settings for a specific chat.

    Path parameters:
        chat_id: Telegram chat ID

    Request body:
        summary_enabled: Enable/disable summary feature
        coach_enabled: Enable/disable coach feature
        language: Chat language (ru/en)

    Returns:
        Updated chat settings
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Check chat exists
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get current settings
    current = await db.get_chat_settings(chat_id)
    if not current:
        current = {
            "summary_enabled": 1,
            "coach_enabled": 1,
            "language": "ru"
        }

    # Build updates
    updates = {}
    if update.summary_enabled is not None:
        updates["summary_enabled"] = 1 if update.summary_enabled else 0
    if update.coach_enabled is not None:
        updates["coach_enabled"] = 1 if update.coach_enabled else 0
    if update.language is not None:
        if update.language not in ["ru", "en"]:
            raise HTTPException(status_code=400, detail="Language must be 'ru' or 'en'")
        updates["language"] = update.language

    # Apply updates
    if updates:
        await db.update_chat_settings(chat_id, updates)

    # Get updated settings
    updated = await db.get_chat_settings(chat_id)

    # Handle None case with default values
    if updated is None:
        updated = {}

    return ChatSettings(
        chat_id=chat_id,
        summary_enabled=updated.get("summary_enabled", current.get("summary_enabled", 1)) == 1,
        coach_enabled=updated.get("coach_enabled", current.get("coach_enabled", 1)) == 1,
        language=updated.get("language", current.get("language", "ru"))
    )


@router.get("/{chat_id}/members")
async def get_chat_members(
    request: Request,
    chat_id: int,
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get members of a specific chat.

    Path parameters:
        chat_id: Telegram chat ID

    Query parameters:
        limit: Maximum members to return

    Returns:
        List of chat members
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Check chat exists
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    members = await db.get_chat_members(chat_id, limit=limit)

    return {
        "chat_id": chat_id,
        "members": members,
        "total": len(members)
    }
