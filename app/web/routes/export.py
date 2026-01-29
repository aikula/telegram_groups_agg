"""
Export Routes - Data export endpoints (v2.0)
"""

import logging
import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/csv")
async def export_csv(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by chat ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to export"),
    include_deleted: bool = Query(default=False, description="Include deleted messages")
):
    """
    Export messages to CSV format.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to export (default: 7)
        include_deleted: Include deleted messages (default: false)

    Returns:
        CSV file download
    """
    from app.web.middleware import required_auth, require_chat_membership

    user = await required_auth(request)

    # If chat_id is specified, verify user has access to this chat
    if chat_id is not None:
        await require_chat_membership(request, chat_id)

    db = request.app.state.db

    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=not include_deleted
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'timestamp', 'chat_id', 'message_id', 'user_id', 'username',
        'first_name', 'last_name', 'content', 'reply_to_id'
    ])

    # Rows
    for msg in messages:
        content = msg.get('content', '')
        # Replace newlines and quotes for CSV
        content = content.replace('\n', ' ').replace('\r', ' ')
        if '"' in content:
            content = content.replace('"', '""')

        writer.writerow([
            msg.get('timestamp', ''),
            msg.get('chat_id', ''),
            msg.get('message_id', ''),
            msg.get('user_id', ''),
            msg.get('username', ''),
            msg.get('first_name', ''),
            msg.get('last_name', ''),
            content,
            msg.get('reply_to_id', '')
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


@router.get("/json")
async def export_json(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by chat ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to export"),
    include_deleted: bool = Query(default=False, description="Include deleted messages"),
    pretty: bool = Query(default=True, description="Pretty print JSON")
):
    """
    Export messages to JSON format.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to export (default: 7)
        include_deleted: Include deleted messages (default: false)
        pretty: Pretty print JSON (default: true)

    Returns:
        JSON file download
    """
    from app.web.middleware import required_auth, require_chat_membership
    import json

    user = await required_auth(request)

    # If chat_id is specified, verify user has access to this chat
    if chat_id is not None:
        await require_chat_membership(request, chat_id)

    db = request.app.state.db

    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=not include_deleted
    )

    # Build export data
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "days": days,
        "total_messages": len(messages),
        "messages": messages
    }

    # Convert to JSON
    json_str = json.dumps(
        export_data,
        ensure_ascii=False,
        indent=2 if pretty else None
    )

    # Create response
    filename = f"messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )


@router.get("/stats")
async def export_stats(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by chat ID"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Export statistics as JSON.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to analyze (default: 30)

    Returns:
        Statistics JSON
    """
    from app.web.middleware import required_auth, require_chat_membership
    import json

    user = await required_auth(request)

    # If chat_id is specified, verify user has access to this chat
    if chat_id is not None:
        await require_chat_membership(request, chat_id)

    db = request.app.state.db

    # Get messages
    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=True
    )

    # Calculate statistics
    from collections import Counter

    user_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    day_counts: Counter = Counter()
    word_counts: Counter = Counter()

    for msg in messages:
        # User counts
        username = msg.get('username') or msg.get('first_name', 'Unknown')
        user_counts[username] += 1

        # Time counts
        timestamp = msg.get('timestamp')
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    dt = None
            else:
                dt = timestamp

            if dt:
                hour_counts[dt.hour] += 1
                day_counts[dt.date().isoformat()] += 1

        # Word counts
        content = msg.get('content', '')
        words = content.lower().split()
        for word in words:
            if len(word) > 3:  # Only count words longer than 3 chars
                word_counts[word] += 1

    # Build stats
    stats = {
        "exported_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "days": days,
        "total_messages": len(messages),
        "unique_users": len(user_counts),
        "top_contributors": dict(user_counts.most_common(20)),
        "most_active_hours": dict(hour_counts.most_common(24)),
        "messages_per_day": dict(sorted(day_counts.items())),
        "top_words": dict(word_counts.most_common(50))
    }

    # Convert to JSON
    json_str = json.dumps(stats, ensure_ascii=False, indent=2)

    filename = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )


class SummaryRequest(BaseModel):
    """Manual summary request."""
    chat_id: int
    days: int = 7


class SummaryResponse(BaseModel):
    """Summary response."""
    success: bool
    summary: Optional[str] = None
    error: Optional[str] = None


@router.post("/summary", response_model=SummaryResponse)
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

    if req.days < 1 or req.days > 365:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 365")

    try:
        success = await trigger_manual_summary(req.chat_id)

        if success:
            return SummaryResponse(
                success=True,
                summary="Summary generation triggered successfully"
            )
        else:
            return SummaryResponse(
                success=False,
                error="Failed to trigger summary generation"
            )

    except Exception as e:
        logger.error(f"Error triggering manual summary: {e}")
        return SummaryResponse(
            success=False,
            error=str(e)
        )
