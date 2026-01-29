"""
Query Parameters Extraction - Extract SQL parameters from natural language (v2.2)

Extracts limit, date ranges, and other parameters from user queries.
Uses regex patterns and LLM fallback for complex cases.

Features:
- Extract LIMIT from queries ("3 messages" → LIMIT 3)
- Extract date ranges ("for a week" → 7 days)
- Intelligent defaults with min/max clamping
- Context-aware parameter inference
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.core.llm import get_llm_client

logger = logging.getLogger(__name__)


# ============================================================================
# Regex Patterns for Parameter Extraction
# ============================================================================

# Limit patterns (numbers that indicate "how many")
LIMIT_PATTERNS = [
    r'(?:показать|дай|выведи|список|последние)\s+(\d+)\s*(?:сообщен[ияий]|запис[ейи]|строк|результатов?|items?)',
    r'(\d+)\s*(?:последн(?:их|ие)\s*)?(?:сообщен[ияий]|запис[ейи]|строк|результатов?|items?)',
    r'limit[:\s]+(\d+)',
    r'топ\s+(\d+)',
    r'top\s+(\d+)',
    r'last\s+(\d+)\s*(?:messages?|items?)',
]

# Date range patterns
DATE_PATTERNS = {
    'today': [
        r'за\s+сегодня',
        r'сегодняшн(?:ий|ия|ие)',
        r'today',
    ],
    'yesterday': [
        r'за\s+вчера',
        r'вчерашн(?:ий|ия|ие)',
        r'yesterday',
    ],
    'this_week': [
        r'за\s+эту\s+неделю',
        r'на\s+этой\s+неделе',
        r'этой\s+недели',
        r'this\s+week',
    ],
    'last_week': [
        r'за\s+последнюю\s+неделю',
        r'за\s+неделю',
        r'последние?\s+\d+\s+дней?\s+\(неделя\)',
        r'прошлая\s+неделя',
        r'last\s+week',
        r'past\s+week',
        r'week',
    ],
    'last_month': [
        r'за\s+последний\s+месяц',
        r'за\s+месяц',
        r'последние?\s+\d+\s+дней?\s+\(месяц\)',
        r'прошлый\s+месяц',
        r'last\s+month',
        r'past\s+month',
        r'month',
    ],
    'last_3_days': [
        r'за\s+последние?\s+3\s+дн[ея]',
        r'последние?\s+тр[оиие]\s+дн[ея]',
        r'last\s+3\s+days?',
    ],
    'last_7_days': [
        r'за\s+последние?\s+7\s+дней',
        r'последние?\s+семь\s+дней',
        r'last\s+7\s+days?',
    ],
    'last_30_days': [
        r'за\s+последние?\s+30\s+дней',
        r'последние?\s+тридцать\s+дней',
        r'last\s+30\s+days?',
    ],
}

# Day number patterns
DAY_NUMBER_PATTERNS = [
    r'за\s+последние?\s+(\d+)\s+дней?',
    r'последние?\s+(\d+)\s+дней?',
    r'last\s+(\d+)\s+days?',
]


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_LIMIT = 20
MIN_LIMIT = 1
MAX_LIMIT = 1000

DEFAULT_DAYS = 7
MIN_DAYS = 1
MAX_DAYS = 365


# ============================================================================
# Main Extraction Function
# ============================================================================

async def extract_query_params(
    query: str,
    language: str = "ru"
) -> Dict[str, Any]:
    """
    Extract SQL query parameters from natural language.

    Args:
        query: User's natural language query
        language: Query language ("ru" or "en")

    Returns:
        Dict with extracted parameters:
            - limit: Maximum results (DEFAULT_LIMIT if not found)
            - days: Number of days to look back (DEFAULT_DAYS if not found)
            - date_from: Optional explicit start date
            - date_to: Optional explicit end date
            - confidence: How confident we are (0-1)
    """
    query_lower = query.lower()

    # Extract limit
    limit = _extract_limit(query_lower, language)
    limit = max(MIN_LIMIT, min(limit, MAX_LIMIT))

    # Extract date range
    days = _extract_days(query_lower, language)
    days = max(MIN_DAYS, min(days, MAX_DAYS))

    # Extract explicit dates
    date_from, date_to = _extract_dates(query)

    # Calculate confidence
    confidence = _calculate_confidence(query, limit, days)

    result = {
        "limit": limit,
        "days": days,
        "confidence": confidence
    }

    if date_from:
        result["date_from"] = date_from
    if date_to:
        result["date_to"] = date_to

    logger.info(f"Extracted params from query: {result}")

    return result


def _extract_limit(query: str, language: str) -> int:
    """Extract limit value from query."""
    # Try regex patterns first
    for pattern in LIMIT_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue

    # Try generic number extraction (last number in query might be limit)
    numbers = re.findall(r'\b(\d+)\b', query)
    if numbers:
        # Use the last number as it's most likely the limit
        # "show last 5 messages" → 5
        try:
            return int(numbers[-1])
        except ValueError:
            pass

    return DEFAULT_LIMIT


def _extract_days(query: str, language: str) -> int:
    """Extract number of days from query."""
    # Check named patterns first
    for period_name, patterns in DATE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query, re.IGNORECASE):
                # Map period to days
                period_days = {
                    'today': 1,
                    'yesterday': 1,
                    'this_week': 7,
                    'last_week': 7,
                    'last_month': 30,
                    'last_3_days': 3,
                    'last_7_days': 7,
                    'last_30_days': 30,
                }
                return period_days.get(period_name, DEFAULT_DAYS)

    # Try day number patterns
    for pattern in DAY_NUMBER_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue

    return DEFAULT_DAYS


def _extract_dates(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract explicit dates from query."""
    # ISO date pattern: 2024-01-15
    iso_dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', query)
    if len(iso_dates) >= 1:
        date_from = iso_dates[0]
        date_to = iso_dates[1] if len(iso_dates) > 1 else None
        return date_from, date_to

    # Russian date pattern: 15.01.2024 or 15/01/2024
    ru_dates = re.findall(r'\b(\d{2}[./]\d{2}[./]\d{4})\b', query)
    if ru_dates:
        # Convert to ISO format
        dates = []
        for d in ru_dates:
            parts = re.split(r'[./]', d)
            try:
                dates.append(f"{parts[2]}-{parts[1]}-{parts[0]}")
            except (ValueError, IndexError):
                continue

        if dates:
            return dates[0], dates[1] if len(dates) > 1 else None

    return None, None


def _calculate_confidence(query: str, limit: int, days: int) -> float:
    """Calculate confidence in extracted parameters."""
    confidence = 0.5  # Base confidence

    # Higher confidence if we found explicit numbers
    if limit != DEFAULT_LIMIT:
        confidence += 0.2

    if days != DEFAULT_DAYS:
        confidence += 0.2

    # Higher confidence for shorter, specific queries
    if len(query) < 100:
        confidence += 0.1

    return min(confidence, 1.0)


# ============================================================================
# Context Size Management
# ============================================================================

async def estimate_token_count(text: str) -> int:
    """
    Estimate token count for text (rough approximation).

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    # Rough estimate: ~4 chars per token for English/Russian
    return len(text) // 4


async def truncate_for_context(
    text: str,
    max_tokens: int = 8000,
    reserve_for_response: int = 2000
) -> str:
    """
    Truncate text to fit within context window.

    Args:
        text: Text to truncate
        max_tokens: Maximum context tokens
        reserve_for_response: Tokens to reserve for LLM response

    Returns:
        Truncated text
    """
    available = max_tokens - reserve_for_response
    estimated = await estimate_token_count(text)

    if estimated <= available:
        return text

    # Truncate to fit
    ratio = available / estimated
    target_chars = int(len(text) * ratio * 0.9)  # 90% safety margin

    truncated = text[:target_chars]

    # Try to end at a sentence boundary
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    cutoff = max(last_period, last_newline)

    if cutoff > target_chars // 2:  # Don't cut too much
        return truncated[:cutoff + 1]

    return truncated


async def format_results_with_limit(
    results: list,
    max_tokens: int = 6000
) -> Dict[str, Any]:
    """
    Format query results with context size protection.

    If results are too large, uses batching/truncation.

    Args:
        results: Query results (list of dicts)
        max_tokens: Maximum tokens for results

    Returns:
        Dict with formatted results and metadata
    """
    if not results:
        return {
            "results": [],
            "total_count": 0,
            "shown_count": 0,
            "truncated": False,
            "estimated_tokens": 0
        }

    # Format as text for token estimation
    formatted = []
    for row in results:
        formatted.append(str(row))

    text = "\n".join(formatted)
    estimated = await estimate_token_count(text)

    if estimated <= max_tokens:
        # All results fit
        return {
            "results": results,
            "total_count": len(results),
            "shown_count": len(results),
            "truncated": False,
            "estimated_tokens": estimated
        }

    # Results don't fit - need to truncate
    ratio = max_tokens / estimated
    target_count = max(1, int(len(results) * ratio * 0.9))

    logger.warning(
        f"Results too large ({estimated} tokens), "
        f"showing {target_count} of {len(results)} rows"
    )

    return {
        "results": results[:target_count],
        "total_count": len(results),
        "shown_count": target_count,
        "truncated": True,
        "truncated_message": f"Показано {target_count} из {len(results)} результатов",
        "estimated_tokens": max_tokens
    }


# ============================================================================
# SQL Query Builder with Extracted Params
# ============================================================================

def build_sql_with_params(
    base_query: str,
    params: Dict[str, Any],
    chat_id: int
) -> str:
    """
    Build SQL query with extracted parameters.

    Args:
        base_query: Base SQL query (SELECT ... FROM messages ...)
        params: Extracted parameters from extract_query_params
        chat_id: Chat ID to filter by

    Returns:
        Complete SQL query with WHERE, ORDER BY, LIMIT

    Security: chat_id is validated as integer to prevent SQL injection.
              days and limit are clamped to safe ranges.
    """
    # Validate chat_id is a safe integer value
    if not isinstance(chat_id, int) or chat_id <= 0 or chat_id > 2**63 - 1:
        logger.warning(f"Invalid chat_id value in build_sql_with_params: {chat_id}")
        return "SELECT 1 WHERE 1=0 LIMIT 1"

    query = base_query.rstrip()
    if query.endswith(';'):
        query = query[:-1]

    # Ensure chat_id filter
    if 'chat_id' not in query.lower():
        if 'where' in query.lower():
            query += f" AND chat_id = {chat_id}"
        else:
            query += f" WHERE chat_id = {chat_id}"

    # Add date filter
    days = params.get('days', DEFAULT_DAYS)
    days = max(MIN_DAYS, min(days, MAX_DAYS))  # Clamp to safe range
    if 'WHERE' in query.upper():
        query += f" AND date(timestamp) >= date('now', '-{days} days')"
    else:
        query += f" WHERE date(timestamp) >= date('now', '-{days} days')"

    # Add ORDER BY if not present
    if 'order by' not in query.lower():
        query += " ORDER BY timestamp DESC"

    # Add LIMIT
    limit = params.get('limit', DEFAULT_LIMIT)
    limit = max(MIN_LIMIT, min(limit, MAX_LIMIT))  # Clamp to safe range
    if 'limit' not in query.lower():
        query += f" LIMIT {limit}"

    query += ';'
    return query
