"""
Statistics Routes - Message and chat statistics (v2.0)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class MessageStatsResponse(BaseModel):
    """Response model for message statistics."""
    total_messages: int
    active_users: int
    days: int
    avg_per_day: float
    top_contributors: List[tuple[str, int]]
    most_active_hour: Optional[int] = None


class HourlyStatsResponse(BaseModel):
    """Response model for hourly statistics."""
    hour: int
    message_count: int


class DailyStatsResponse(BaseModel):
    """Response model for daily statistics."""
    date: str
    message_count: int
    unique_users: int


@router.get("/messages", response_model=MessageStatsResponse)
async def get_message_stats(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by specific chat ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get message statistics.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to analyze (default: 7, max: 365)

    Returns:
        Message statistics including totals, averages, and top contributors
    """
    from app.web.middleware import required_auth, require_chat_membership

    # If chat_id is specified, verify user has access
    if chat_id is not None:
        await require_chat_membership(request, chat_id)
    else:
        # No chat filter - require auth
        await required_auth(request)

    db = request.app.state.db

    # Get cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)

    # Get messages
    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=True
    )

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
    user_counts: dict[str, int] = {}
    hour_counts: dict[int, int] = {}

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
                except (ValueError, AttributeError):
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


@router.get("/hourly", response_model=List[HourlyStatsResponse])
async def get_hourly_stats(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by specific chat ID"),
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get hourly message distribution.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to analyze (default: 7)

    Returns:
        List of hourly message counts
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=True
    )

    # Count by hour
    hour_counts: dict[int, int] = {}

    for msg in messages:
        timestamp = msg.get('timestamp')
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    continue
            else:
                dt = timestamp

            if dt:
                hour = dt.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1

    # Build response
    return [
        HourlyStatsResponse(hour=h, message_count=hour_counts.get(h, 0))
        for h in range(24)
    ]


@router.get("/daily", response_model=List[DailyStatsResponse])
async def get_daily_stats(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by specific chat ID"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get daily message statistics.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to analyze (default: 30)

    Returns:
        List of daily message counts
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    messages = await db.get_messages(
        chat_id=chat_id,
        days=days,
        exclude_deleted=True
    )

    # Count by day
    day_counts: dict[str, set] = {}

    for msg in messages:
        timestamp = msg.get('timestamp')
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    continue
            else:
                dt = timestamp

            if dt:
                date_str = dt.date().isoformat()
                user_id = msg.get('user_id')

                if date_str not in day_counts:
                    day_counts[date_str] = set()

                if user_id:
                    day_counts[date_str].add(user_id)

    # Build response - include all days in range
    result = []
    for i in range(days):
        date = datetime.now() - timedelta(days=days - i - 1)
        date_str = date.date().isoformat()

        # Get messages for this day
        day_messages = [
            m for m in messages
            if m.get('timestamp')
            and (
                (
                    isinstance(m['timestamp'], str) and
                    datetime.fromisoformat(m['timestamp'].replace('Z', '+00:00')).date().isoformat() == date_str
                )
                or (
                    isinstance(m['timestamp'], datetime) and
                    m['timestamp'].date().isoformat() == date_str
                )
            )
        ]

        unique_users = set()
        for m in day_messages:
            if m.get('user_id'):
                unique_users.add(m['user_id'])

        result.append(DailyStatsResponse(
            date=date_str,
            message_count=len(day_messages),
            unique_users=len(unique_users)
        ))

    return result


# LLM Usage Response Models
class LLMUsageStatsResponse(BaseModel):
    """LLM usage statistics response model."""
    total_tokens_prompt: int
    total_tokens_completion: int
    total_tokens: int
    total_cost_usd: float
    requests_count: int
    by_chat: List[dict]
    by_skill: List[dict]


@router.get("/llm-usage", response_model=LLMUsageStatsResponse)
async def get_llm_usage_stats(
    request: Request,
    chat_id: Optional[int] = Query(None, description="Filter by specific chat ID"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get LLM token usage statistics.

    Query parameters:
        chat_id: Filter by specific chat (optional)
        days: Number of days to analyze (default: 30)

    Returns:
        LLM usage statistics including token counts and costs
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    db = request.app.state.db

    # Get cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)

    # Get LLM usage data
    usage_data = await db.execute_query(
        """
        SELECT
            chat_id,
            skill,
            SUM(tokens_prompt) as total_prompt,
            SUM(tokens_completion) as total_completion,
            SUM(cost_usd) as total_cost,
            COUNT(*) as requests
        FROM llm_usage
        WHERE timestamp >= ?
        GROUP BY chat_id, skill
        ORDER BY total_prompt + total_completion DESC
        """,
        (cutoff_date.isoformat(),)
    )

    if not usage_data:
        return LLMUsageStatsResponse(
            total_tokens_prompt=0,
            total_tokens_completion=0,
            total_tokens=0,
            total_cost_usd=0.0,
            requests_count=0,
            by_chat=[],
            by_skill=[]
        )

    # Calculate totals
    total_prompt = sum(row['total_prompt'] for row in usage_data)
    total_completion = sum(row['total_completion'] for row in usage_data)
    total_cost = sum(row['total_cost'] for row in usage_data)
    total_requests = sum(row['requests'] for row in usage_data)

    # Group by chat
    chat_stats = {}
    for row in usage_data:
        cid = row['chat_id']
        if cid not in chat_stats:
            chat_stats[cid] = {
                'chat_id': cid,
                'tokens_prompt': 0,
                'tokens_completion': 0,
                'tokens_total': 0,
                'cost_usd': 0.0,
                'requests': 0
            }
        chat_stats[cid]['tokens_prompt'] += row['total_prompt']
        chat_stats[cid]['tokens_completion'] += row['total_completion']
        chat_stats[cid]['tokens_total'] += row['total_prompt'] + row['total_completion']
        chat_stats[cid]['cost_usd'] += row['total_cost']
        chat_stats[cid]['requests'] += row['requests']

    # Group by skill
    skill_stats = {}
    for row in usage_data:
        skill = row['skill'] or 'unknown'
        if skill not in skill_stats:
            skill_stats[skill] = {
                'skill': skill,
                'tokens_prompt': 0,
                'tokens_completion': 0,
                'tokens_total': 0,
                'cost_usd': 0.0,
                'requests': 0
            }
        skill_stats[skill]['tokens_prompt'] += row['total_prompt']
        skill_stats[skill]['tokens_completion'] += row['total_completion']
        skill_stats[skill]['tokens_total'] += row['total_prompt'] + row['total_completion']
        skill_stats[skill]['cost_usd'] += row['total_cost']
        skill_stats[skill]['requests'] += row['requests']

    return LLMUsageStatsResponse(
        total_tokens_prompt=total_prompt,
        total_tokens_completion=total_completion,
        total_tokens=total_prompt + total_completion,
        total_cost_usd=round(total_cost, 4),
        requests_count=total_requests,
        by_chat=list(chat_stats.values()),
        by_skill=list(skill_stats.values())
    )
