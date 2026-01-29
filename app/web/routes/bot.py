"""
Bot Routes - Chat with bot via web interface (v2.1)

Allows users to send messages to the bot and receive responses.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class BotMessageRequest(BaseModel):
    """Send message to bot request model."""
    chat_id: int = Field(..., description="Target chat ID for bot context")
    message: str = Field(..., min_length=1, max_length=4096, description="Message text")


class BotMessageResponse(BaseModel):
    """Bot message response model."""
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None


class BotChatHistoryResponse(BaseModel):
    """Bot chat history response model."""
    chat_id: int
    messages: List[dict]
    total: int


@router.post("/send", response_model=BotMessageResponse)
async def send_bot_message(request: Request, msg_data: BotMessageRequest):
    """
    Send a message to the bot and get a response.

    The bot will process the message in the context of the specified chat
    and return its response.

    Request body:
    {
        "chat_id": 123,  // Target chat ID for context
        "message": "What was discussed today?"
    }

    Returns:
        Bot response or error message
    """
    from app.web.middleware import required_auth
    from app.bot.bot import get_bot
    from app.core.rate_limiter import get_rate_limiter

    user = await required_auth(request)
    db = request.app.state.db

    # Rate limit check - prevent cost attacks using user-scoped limiting
    rate_limiter = get_rate_limiter()
    allowed, retry_after = await rate_limiter.acquire(
        tokens=1,
        user_id=user.user_id,
        chat_type="private"  # Use private limits for individual user requests
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please try again in {retry_after:.0f} seconds."
        )

    # Check chat exists and user has access
    chat = await db.get_chat_by_id(msg_data.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Check if user is member of chat (or superadmin)
    # Note: is_user_in_chat uses internal chat id (chats.id), not Telegram chat_id
    if not user.is_superadmin:
        is_member = await db.is_user_in_chat(user.user_id, chat["id"])
        if not is_member:
            raise HTTPException(status_code=403, detail="You don't have access to this chat")

    # Get bot instance
    bot = get_bot()
    if not bot:
        return BotMessageResponse(
            success=False,
            error="Bot is not available. Please try again later."
        )

    try:
        # Get user info from database
        db_user = await db.get_user_by_id(user.user_id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Directly call the LLM with the query
        from app.core.llm import get_llm_client
        from app.core.router import RouterAgent
        from app.core.agent import SkillAgent

        llm = get_llm_client()

        # Route query to appropriate skill
        router = RouterAgent(db, llm)
        skill_name = await router.route(msg_data.message, chat_id=msg_data.chat_id)

        # Execute skill
        agent = SkillAgent(db, llm)
        response = await agent.execute(
            skill_name=skill_name,
            query=msg_data.message,
            chat_id=msg_data.chat_id,
            user_id=user.user_id
        )

        # Log the interaction
        await db.audit_log(
            user_id=user.user_id,
            action="bot_web_query",
            chat_id=msg_data.chat_id,
            details={
                "skill_used": skill_name,
                "query": msg_data.message[:200]  # Truncate for logging
            }
        )

        return BotMessageResponse(
            success=True,
            response=response
        )

    except Exception as e:
        logger.error(f"Error processing bot message: {e}")
        return BotMessageResponse(
            success=False,
            error=str(e)
        )


@router.get("/chats", response_model=List[dict])
async def get_available_bot_chats(
    request: Request,
    active_only: bool = Query(default=True, description="Only return active chats")
):
    """
    Get list of chats available for bot interaction.

    Returns chats where the current user is a member (or all chats for superadmins).

    Query parameters:
        active_only: Only return active chats (default: true)

    Returns:
        List of available chats
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)
    db = request.app.state.db

    # Superadmins see all chats, regular users only see their chats
    if user.is_superadmin:
        chats = await db.get_chats(active_only=active_only, limit=100)
    else:
        chats = await db.get_user_chats(
            user_id=user.user_id,
            active_only=active_only,
            limit=100
        )

    return [
        {
            "chat_id": chat.get("chat_id") or chat["id"],
            "title": chat.get("title", "Unknown Chat"),
            "chat_type": chat.get("type", "unknown"),
            "member_count": chat.get("member_count", 0)
        }
        for chat in chats
    ]
