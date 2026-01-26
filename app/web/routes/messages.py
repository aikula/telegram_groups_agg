"""
Messages Routes - Message retrieval and search (v2.0)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class MessageInfo(BaseModel):
    """Message information model."""
    message_id: int
    chat_id: int
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    content: str
    timestamp: str
    reply_to_id: Optional[int] = None


class MessagesListResponse(BaseModel):
    """Messages list response model."""
    total: int
    offset: int
    limit: int
    messages: List[MessageInfo]


class SearchQuery(BaseModel):
    """Search query model."""
    query: str
    chat_id: Optional[int] = None
    days: int = Query(default=7, ge=1, le=365)
    limit: int = Query(default=50, ge=1, le=500)


@router.get("", response_model=MessagesListResponse)
async def get_messages(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by chat ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to look back"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip")
):
    """
    Get messages with filtering and pagination.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        user_id: Filter by specific user (optional)
        days: Number of days to look back (default: 7)
        limit: Maximum messages to return (default: 100)
        offset: Number of messages to skip (default: 0)

    Returns:
        Paginated list of messages
    """
    from app.web.middleware import required_auth, require_chat_membership

    # If chat_id is specified, verify user has access
    if chat_id is not None:
        await require_chat_membership(request, chat_id)
    else:
        # No chat filter - require auth
        await required_auth(request)

    db = request.app.state.db

    # Get messages from database
    messages = await db.get_messages(
        chat_id=chat_id,
        user_id=user_id,
        days=days,
        exclude_deleted=True
    )

    # Apply pagination
    total = len(messages)
    paginated = messages[offset:offset + limit]

    return MessagesListResponse(
        total=total,
        offset=offset,
        limit=limit,
        messages=[
            MessageInfo(
                message_id=msg.get("message_id", 0),
                chat_id=msg.get("chat_id", 0),
                user_id=msg.get("user_id", 0),
                username=msg.get("username"),
                first_name=msg.get("first_name"),
                last_name=msg.get("last_name"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp", ""),
                reply_to_id=msg.get("reply_to_id")
            )
            for msg in paginated
        ]
    )


@router.get("/{message_id}", response_model=MessageInfo)
async def get_message(request: Request, message_id: int):
    """
    Get a specific message by ID.

    Path parameters:
        message_id: Telegram message ID

    Returns:
        Message information
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    message = await db.get_message_by_id(message_id)

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    return MessageInfo(
        message_id=message.get("message_id", 0),
        chat_id=message.get("chat_id", 0),
        user_id=message.get("user_id", 0),
        username=message.get("username"),
        first_name=message.get("first_name"),
        last_name=message.get("last_name"),
        content=message.get("content", ""),
        timestamp=message.get("timestamp", ""),
        reply_to_id=message.get("reply_to_id")
    )


@router.post("/search", response_model=MessagesListResponse)
async def search_messages(
    request: Request,
    query: str = Query(..., description="Search query", min_length=1),
    chat_id: Optional[int] = Query(None, description="Filter by chat ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to search"),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum results to return")
):
    """
    Search messages by content.

    Query parameters:
        query: Search query text
        chat_id: Filter by specific chat (optional)
        days: Number of days to search (default: 7)
        limit: Maximum results to return (default: 50)

    Returns:
        List of matching messages
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Use full-text search
    messages = await db.search_messages(
        query=query,
        chat_id=chat_id,
        days=days,
        limit=limit
    )

    return MessagesListResponse(
        total=len(messages),
        offset=0,
        limit=limit,
        messages=[
            MessageInfo(
                message_id=msg.get("message_id", 0),
                chat_id=msg.get("chat_id", 0),
                user_id=msg.get("user_id", 0),
                username=msg.get("username"),
                first_name=msg.get("first_name"),
                last_name=msg.get("last_name"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp", ""),
                reply_to_id=msg.get("reply_to_id")
            )
            for msg in messages
        ]
    )


@router.get("/{message_id}/context")
async def get_message_context(
    request: Request,
    message_id: int,
    before: int = Query(default=5, ge=0, le=50, description="Messages before"),
    after: int = Query(default=5, ge=0, le=50, description="Messages after")
):
    """
    Get context around a message (thread/conversation).

    Path parameters:
        message_id: Telegram message ID

    Query parameters:
        before: Number of messages before (default: 5)
        after: Number of messages after (default: 5)

    Returns:
        Thread context with messages
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    context = await db.get_message_context(
        message_id=message_id,
        before=before,
        after=after
    )

    if not context:
        raise HTTPException(status_code=404, detail="Message not found")

    return {
        "message_id": message_id,
        "before": [
            MessageInfo(
                message_id=msg.get("message_id", 0),
                chat_id=msg.get("chat_id", 0),
                user_id=msg.get("user_id", 0),
                username=msg.get("username"),
                first_name=msg.get("first_name"),
                last_name=msg.get("last_name"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp", ""),
                reply_to_id=msg.get("reply_to_id")
            )
            for msg in context.get("before", [])
        ],
        "target": MessageInfo(
            message_id=context["target"].get("message_id", 0),
            chat_id=context["target"].get("chat_id", 0),
            user_id=context["target"].get("user_id", 0),
            username=context["target"].get("username"),
            first_name=context["target"].get("first_name"),
            last_name=context["target"].get("last_name"),
            content=context["target"].get("content", ""),
            timestamp=context["target"].get("timestamp", ""),
            reply_to_id=context["target"].get("reply_to_id")
        ) if context.get("target") else None,
        "after": [
            MessageInfo(
                message_id=msg.get("message_id", 0),
                chat_id=msg.get("chat_id", 0),
                user_id=msg.get("user_id", 0),
                username=msg.get("username"),
                first_name=msg.get("first_name"),
                last_name=msg.get("last_name"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp", ""),
                reply_to_id=msg.get("reply_to_id")
            )
            for msg in context.get("after", [])
        ]
    }
