"""
Feedback Routes - User feedback system (v2.2)

Allows users to submit feedback from web UI and bot.
Superadmins can view and manage feedback.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models

class FeedbackCreate(BaseModel):
    """Feedback creation model."""
    category: str = Field(..., description="Category: bug, feature, other")
    message: str = Field(..., min_length=1, max_length=5000, description="Feedback message")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5 (optional)")

    @validator('category')
    def validate_category(cls, v):
        valid_categories = {'bug', 'feature', 'other'}
        if v not in valid_categories:
            raise ValueError(f"Category must be one of: {valid_categories}")
        return v


class FeedbackResponse(BaseModel):
    """Feedback response model."""
    id: int
    status: str


class FeedbackListResponse(BaseModel):
    """Feedback list item model."""
    id: int
    user_id: int
    username: Optional[str]
    chat_id: Optional[int]
    chat_title: Optional[str]
    source: str
    category: str
    message: str
    rating: Optional[int]
    status: str
    created_at: str
    resolved_at: Optional[str]


@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback(request: Request, feedback: FeedbackCreate):
    """
    Create feedback from authenticated user.

    Request body:
        - category: Category (bug/feature/other)
        - message: Feedback message
        - rating: Optional rating 1-5

    Returns:
        Created feedback ID and status
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)
    db = request.app.state.db

    # Try to get chat_id from request body (for bot feedback)
    # For web feedback, we might not have a specific chat
    chat_id = None
    if hasattr(request.state, 'chat_id'):
        chat_id = request.state.chat_id

    feedback_id = await db.create_feedback(
        user_id=user.user_id,
        chat_id=chat_id or 0,
        source="web",
        category=feedback.category,
        message=feedback.message,
        rating=feedback.rating
    )

    logger.info(f"Feedback created by user {user.username}: id={feedback_id}")

    return FeedbackResponse(
        id=feedback_id,
        status="created"
    )


@router.get("/feedback", response_model=List[FeedbackListResponse])
async def get_all_feedback(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100
):
    """
    Get all feedback entries (superadmin only).

    Query parameters:
        status: Filter by status (new/in_progress/resolved), None for all
        limit: Maximum entries to return (default: 100)

    Returns:
        List of feedback entries
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)

    # Only superadmins can access all feedback
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    db = request.app.state.db

    feedback_list = await db.get_feedback(status=status, limit=limit)

    return [
        FeedbackListResponse(
            id=item['id'],
            user_id=item.get('user_id'),
            username=item.get('username'),
            chat_id=item.get('chat_id'),
            chat_title=item.get('chat_title'),
            source=item['source'],
            category=item['category'],
            message=item['message'],
            rating=item.get('rating'),
            status=item['status'],
            created_at=item['created_at'],
            resolved_at=item.get('resolved_at')
        )
        for item in feedback_list
    ]


@router.put("/feedback/{feedback_id}/status", response_model=FeedbackResponse)
async def update_feedback_status(
    request: Request,
    feedback_id: int,
    status: str
):
    """
    Update feedback status (superadmin only).

    Path parameters:
        feedback_id: Feedback ID

    Request body:
        status: New status (new/in_progress/resolved)

    Returns:
        Updated status
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)

    # Only superadmins can update feedback status
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    if status not in ['new', 'in_progress', 'resolved']:
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be: new, in_progress, or resolved"
        )

    db = request.app.state.db

    updated = await db.update_feedback_status(feedback_id, status)

    if not updated:
        raise HTTPException(status_code=404, detail="Feedback not found")

    logger.info(f"Feedback {feedback_id} status updated to '{status}' by {user.username}")

    return FeedbackResponse(
        id=feedback_id,
        status=status
    )
