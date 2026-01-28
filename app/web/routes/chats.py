"""
Chats Routes - Chat management endpoints (v2.1)

Supports both legacy boolean format and new enabled_skills JSON format.
"""

import logging
import json
from typing import Optional, List, Union
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

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


class ChatSettingsLegacy(BaseModel):
    """Legacy chat settings model (v2.0 format with boolean fields)."""
    chat_id: int
    summary_enabled: bool = True
    coach_enabled: bool = True
    language: str = "ru"


class ChatSettingsV21(BaseModel):
    """Chat settings model (v2.1 format with enabled_skills JSON)."""
    chat_id: int
    enabled_skills: List[str] = Field(
        default=["summary", "coach", "qa", "analytics"],
        description="List of enabled skills"
    )
    language: str = "ru"
    summary_time_local: Optional[str] = None
    summary_timezone: Optional[str] = None
    summary_custom_prompt: Optional[str] = None
    summary_target: Optional[str] = None
    coach_custom_prompt: Optional[str] = None
    coach_target: Optional[str] = None


# Union type for backward compatibility
ChatSettings = Union[ChatSettingsLegacy, ChatSettingsV21]


class ChatSettingsUpdateLegacy(BaseModel):
    """Chat settings update model (v2.0 format)."""
    summary_enabled: Optional[bool] = None
    coach_enabled: Optional[bool] = None
    language: Optional[str] = None


class ChatSettingsUpdateV21(BaseModel):
    """Chat settings update model (v2.1 format)."""
    enabled_skills: Optional[List[str]] = Field(
        default=None,
        description="List of enabled skills: summary, coach, qa, analytics"
    )
    language: Optional[str] = None
    summary_time_local: Optional[str] = None
    summary_timezone: Optional[str] = None
    summary_custom_prompt: Optional[str] = None
    summary_target: Optional[str] = None
    coach_custom_prompt: Optional[str] = None
    coach_target: Optional[str] = None


# Union type for updates
ChatSettingsUpdate = Union[ChatSettingsUpdateLegacy, ChatSettingsUpdateV21]


class ChatDetailResponse(BaseModel):
    """Chat detail response model."""
    chat: ChatInfo
    settings: ChatSettingsV21
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
            "enabled_skills": '["summary", "coach", "qa", "analytics"]',
            "language": "ru"
        }

    # Parse enabled_skills to list (v2.1 format)
    enabled_skills = settings_data.get("enabled_skills", '["summary", "coach", "qa", "analytics"]')
    if isinstance(enabled_skills, str):
        try:
            enabled_skills = json.loads(enabled_skills)
        except json.JSONDecodeError:
            # Fallback to default if JSON is invalid
            enabled_skills = ["qa", "analytics"]

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
        settings=ChatSettingsV21(
            chat_id=chat_id,
            enabled_skills=enabled_skills,
            language=settings_data.get("language", "ru"),
            summary_time_local=settings_data.get("summary_time_local"),
            summary_timezone=settings_data.get("summary_timezone"),
            summary_custom_prompt=settings_data.get("summary_custom_prompt"),
            summary_target=settings_data.get("summary_target"),
            coach_custom_prompt=settings_data.get("coach_custom_prompt"),
            coach_target=settings_data.get("coach_target")
        ),
        message_count=message_count,
        member_count=member_count
    )


@router.get("/{chat_id}/settings", response_model=ChatSettingsV21)
async def get_chat_settings(request: Request, chat_id: int):
    """
    Get settings for a specific chat.

    Path parameters:
        chat_id: Telegram chat ID

    Returns:
        Chat settings (v2.1 format with enabled_skills)
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
            "enabled_skills": '["summary", "coach", "qa", "analytics"]',
            "language": "ru"
        }

    # Parse enabled_skills
    enabled_skills = settings_data.get("enabled_skills", '["summary", "coach", "qa", "analytics"]')
    if isinstance(enabled_skills, str):
        try:
            enabled_skills = json.loads(enabled_skills)
        except json.JSONDecodeError:
            enabled_skills = ["qa", "analytics"]

    return ChatSettingsV21(
        chat_id=chat_id,
        enabled_skills=enabled_skills,
        language=settings_data.get("language", "ru"),
        summary_time_local=settings_data.get("summary_time_local"),
        summary_timezone=settings_data.get("summary_timezone"),
        summary_custom_prompt=settings_data.get("summary_custom_prompt"),
        summary_target=settings_data.get("summary_target"),
        coach_custom_prompt=settings_data.get("coach_custom_prompt"),
        coach_target=settings_data.get("coach_target")
    )


@router.put("/{chat_id}/settings", response_model=ChatSettingsV21)
async def update_chat_settings(request: Request, chat_id: int, update: dict = None):
    """
    Update settings for a specific chat.

    Supports both legacy boolean format and new enabled_skills format:
    - Use enabled_skills for v2.1 format (recommended)
    - Use summary_enabled/coach_enabled for legacy v2.0 format

    Path parameters:
        chat_id: Telegram chat ID

    Request body (any of these fields):
    {
        "enabled_skills": ["summary", "coach", "qa", "analytics"],  // v2.1 format
        "summary_enabled": true,  // legacy v2.0 format
        "coach_enabled": false,  // legacy v2.0 format
        "language": "ru",
        "summary_time_local": "16:00",
        "summary_timezone": "Europe/Moscow",
        "summary_custom_prompt": "Custom prompt",
        "summary_target": "chat",
        "coach_custom_prompt": "Custom prompt",
        "coach_target": "chat"
    }

    Returns:
        Updated chat settings (v2.1 format)
    """
    from app.web.middleware import can_modify_chat_settings, get_user_role_in_chat
    from pydantic import BaseModel, Field

    # Authorize using role-based check (v2.2)
    user = await can_modify_chat_settings(request, chat_id)

    db = request.app.state.db

    # Check chat exists
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get current settings
    current = await db.get_chat_settings(chat_id)
    if not current:
        current = {
            "enabled_skills": '["summary", "coach", "qa", "analytics"]',
            "language": "ru"
        }

    # Parse current enabled_skills
    current_enabled = current.get("enabled_skills", '["summary", "coach", "qa", "analytics"]')
    if isinstance(current_enabled, str):
        try:
            current_enabled = json.loads(current_enabled)
        except json.JSONDecodeError:
            current_enabled = ["qa", "analytics"]

    # Use update dict if provided, otherwise empty
    updates = update or {}

    # Handle v2.1 enabled_skills format
    if "enabled_skills" in updates:
        enabled_skills = updates["enabled_skills"]
        # Validate skills
        valid_skills = {"summary", "coach", "qa", "analytics"}
        invalid_skills = set(enabled_skills) - valid_skills
        if invalid_skills:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid skills: {invalid_skills}. Valid skills: {valid_skills}"
            )
        # Will be JSON encoded later

    # Handle legacy v2.0 boolean format (convert to v2.1)
    elif "summary_enabled" in updates or "coach_enabled" in updates:
        # Modify current enabled_skills based on legacy booleans
        if updates.get("summary_enabled") and "summary" not in current_enabled:
            current_enabled.append("summary")
        elif updates.get("summary_enabled") is False and "summary" in current_enabled:
            current_enabled.remove("summary")

        if updates.get("coach_enabled") and "coach" not in current_enabled:
            current_enabled.append("coach")
        elif updates.get("coach_enabled") is False and "coach" in current_enabled:
            current_enabled.remove("coach")

        updates["enabled_skills"] = json.dumps(current_enabled)

    # Handle language validation
    if "language" in updates and updates["language"] not in ["ru", "en"]:
        raise HTTPException(status_code=400, detail="Language must be 'ru' or 'en'")

    # Apply updates
    if updates:
        await db.update_chat_settings(chat_id, updates)

        # Audit log (v2.2)
        user_role = await get_user_role_in_chat(request, chat_id)
        await db.audit_log(
            user_id=user.user_id,
            action="chat_settings_updated",
            chat_id=chat_id,
            details={
                "fields_updated": list(updates.keys()),
                "user_role": user_role,
                "is_superadmin": user.is_superadmin
            }
        )

    # Get updated settings
    updated = await db.get_chat_settings(chat_id)

    # Handle None case with default values
    if updated is None:
        updated = {}

    # Parse enabled_skills from response
    final_enabled = updated.get("enabled_skills", json.dumps(current_enabled))
    if isinstance(final_enabled, str):
        try:
            final_enabled = json.loads(final_enabled)
        except json.JSONDecodeError:
            final_enabled = ["qa", "analytics"]

    logger.info(
        f"Chat settings updated: chat_id={chat_id}, "
        f"user_id={user.user_id}, role={user_role}, "
        f"is_superadmin={user.is_superadmin}"
    )

    return ChatSettingsV21(
        chat_id=chat_id,
        enabled_skills=final_enabled,
        language=updated.get("language", current.get("language", "ru")),
        summary_time_local=updated.get("summary_time_local"),
        summary_timezone=updated.get("summary_timezone"),
        summary_custom_prompt=updated.get("summary_custom_prompt"),
        summary_target=updated.get("summary_target"),
        coach_custom_prompt=updated.get("coach_custom_prompt"),
        coach_target=updated.get("coach_target")
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
