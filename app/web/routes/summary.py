"""
Summary Routes - Manual summary generation endpoints

Allows users to trigger manual summary generation for chats.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class SummaryRequest(BaseModel):
    """Manual summary request model."""
    chat_id: int = Field(..., description="Telegram chat ID")
    days: int = Field(default=7, ge=1, le=365, description="Days to analyze")


class SummaryResponse(BaseModel):
    """Summary response model."""
    success: bool
    summary: Optional[str] = None
    recommendations: Optional[str] = None
    error: Optional[str] = None


@router.post("/manual", response_model=SummaryResponse)
async def trigger_manual_summary(request: Request, req: SummaryRequest):
    """
    Manually trigger a summary generation.

    Request body:
        chat_id: Telegram chat ID
        days: Number of days to analyze (default: 7)

    Returns:
        Summary generation result
    """
    from app.web.middleware import required_auth
    from app.bot.scheduler import trigger_manual_summary

    await required_auth(request)

    try:
        success = await trigger_manual_summary(req.chat_id)

        if success:
            return SummaryResponse(
                success=True,
                summary="Summary generation triggered successfully",
                recommendations="Check back later for the summary"
            )
        else:
            return SummaryResponse(
                success=False,
                error="Failed to trigger summary generation"
            )

    except Exception as e:
        logger.error(f"Error triggering summary: {e}")
        return SummaryResponse(
            success=False,
            error=str(e)
        )


@router.post("/send", response_model=SummaryResponse)
async def send_summary_to_chat(request: Request, req: SummaryRequest):
    """
    Send the latest summary to the chat.

    Triggers summary generation and sends it to the chat.

    Request body:
        chat_id: Telegram chat ID

    Returns:
        Summary send result
    """
    from app.web.middleware import required_auth
    from app.bot.scheduler import trigger_manual_summary

    await required_auth(request)

    try:
        success = await trigger_manual_summary(req.chat_id)

        if success:
            return SummaryResponse(
                success=True,
                summary="Summary sent to chat successfully"
            )
        else:
            return SummaryResponse(
                success=False,
                error="Failed to send summary to chat"
            )

    except Exception as e:
        logger.error(f"Error sending summary: {e}")
        return SummaryResponse(
            success=False,
            error=str(e)
        )
