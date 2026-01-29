"""
Tools module - Low-level operations for AI agents (v2.2)

Implements AGENTS.md specification with OpenAI Function Calling format.
Tools are atomic functions that can be called by LLM agents.

Available tools:
- get_chat_history: Retrieve recent messages from chat
- sql_analytics: Execute safe SELECT SQL queries
- general_answer: Use LLM general knowledge

Security v2.2:
- Enhanced SQL validation with UNION/subquery blocking
- Mandatory LIMIT clause with max value check
- Query complexity limits (JOINs, length)
- Dangerous function detection
- Sensitive data redaction in logs

New v2.2:
- Smart parameter extraction from natural language
- Context size protection with automatic truncation
- Batch mode for large result sets
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta

from app.core.db import Database
from app.core.query_params import (
    extract_query_params,
    format_results_with_limit,
    build_sql_with_params,
)
from app.core.log_utils import sanitize_log_query, sanitize_log_args

logger = logging.getLogger(__name__)

# Security constants
MAX_LIMIT_VALUE = 1000
MAX_JOINS = 3
MAX_QUERY_LENGTH = 2000
MAX_SUBQUERY_DEPTH = 0  # No subqueries allowed


# ============================================================================
# Tool Definitions (OpenAI Function Calling format)
# ============================================================================

TOOL_DEFINITIONS = {
    "get_chat_history": {
        "type": "function",
        "function": {
            "name": "get_chat_history",
            "description": "Retrieve recent messages from chat with user information. Automatically extracts limit/days from your query text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's original question for smart parameter extraction (e.g., 'show last 3 messages' → limit=3, 'for a week' → days=7)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Override: Maximum messages (max: 100)",
                        "default": 20
                    },
                    "days": {
                        "type": "integer",
                        "description": "Override: Only messages from last N days",
                        "default": 7
                    }
                }
            }
        }
    },

    "sql_analytics": {
        "type": "function",
        "function": {
            "name": "sql_analytics",
            "description": "Execute SQL analytics query. Accepts natural language (e.g., 'count messages this week') or raw SQL. Auto-adds LIMIT, date filter, and chat_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question OR SQL SELECT query. Examples: 'how many messages today', 'top users this week', or raw SQL with chat_id filter"
                    }
                },
                "required": ["query"]
            }
        }
    },

    "general_answer": {
        "type": "function",
        "function": {
            "name": "general_answer",
            "description": "Use general LLM knowledge. Automatically includes last 10 messages as chat context. Use for general questions that may benefit from chat awareness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's original question (for context)"
                    }
                },
                "required": []
            }
        }
    }
}


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Get all tool definitions for LLM.

    Returns:
        List of tool definitions in OpenAI Function Calling format
    """
    return list(TOOL_DEFINITIONS.values())


# ============================================================================
# Tool Implementations
# ============================================================================

async def get_chat_history(
    chat_id: int,
    limit: int = 20,
    days: int = 7,
    query: str = "",
    db: Optional[Database] = None
) -> Dict[str, Any]:
    """
    Tool: Get recent chat messages with user information.

    v2.2: Smart parameter extraction from query text.
    If 'query' is provided, extracts limit/days from natural language.

    Args:
        chat_id: Telegram chat ID
        limit: Maximum messages to return (max: 100, extracted from query if provided)
        days: Only messages from last N days (extracted from query if provided)
        query: Original user query for parameter extraction (optional)
        db: Database instance (uses default if None)

    Returns:
        Dict with messages list, count, and metadata
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

    # Extract parameters from query if provided
    if query:
        try:
            params = await extract_query_params(query)
            extracted_limit = params.get('limit', limit)
            extracted_days = params.get('days', days)

            # Use extracted values if more specific
            if params.get('confidence', 0) > 0.6:
                limit = extracted_limit
                days = extracted_days
                logger.info(f"Extracted params from query: limit={limit}, days={days}")
        except Exception as e:
            logger.warning(f"Param extraction failed: {e}, using defaults")

    # Validate and clamp parameters
    limit = max(1, min(limit, 100))
    days = max(1, min(days, 365))

    logger.info(f"Tool get_chat_history: chat_id={chat_id}, limit={limit}, days={days}")

    # Get messages with user info
    messages = await db.get_messages(
        chat_id=chat_id,
        limit=limit,
        days=days,
        exclude_deleted=True
    )

    # Format for LLM consumption with context protection
    formatted = []
    for msg in messages:
        formatted.append({
            "timestamp": msg.get("timestamp", ""),
            "user_id": msg.get("user_id"),
            "username": msg.get("username") or msg.get("first_name", "Unknown"),
            "content": msg.get("content", "")
        })

    # Context size protection
    result_data = await format_results_with_limit(formatted, max_tokens=6000)

    return {
        "messages": result_data["results"],
        "count": result_data["shown_count"],
        "total_count": len(formatted),
        "truncated": result_data.get("truncated", False),
        "message": result_data.get("truncated_message", "")
    }


async def sql_analytics(
    chat_id: int,
    query: str,
    db: Optional[Database] = None
) -> Dict[str, Any]:
    """
    Tool: Execute safe SQL analytics query.

    v2.2: Auto-parameters from query + context size protection.

    Security features:
    - SELECT queries only
    - Mandatory chat_id filter
    - Forbidden keyword detection
    - Injection pattern detection
    - Read-only execution

    Args:
        chat_id: Telegram chat ID (for filtering and validation)
        query: SQL SELECT query (can be incomplete - params added automatically)
        db: Database instance (uses default if None)

    Returns:
        Dict with columns, data, count, and metadata
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

    logger.info(f"Tool sql_analytics: chat_id={chat_id}, query={sanitize_log_query(query, max_length=100)}")

    # Extract parameters from query if it's a natural language description
    # (starts with non-SQL keywords like "show", "count", etc.)
    is_natural_language = not query.strip().upper().startswith(('SELECT', 'WITH'))

    if is_natural_language:
        # Extract params and build proper SQL
        try:
            params = await extract_query_params(query)

            # Build base query from natural language intent
            base_query = _build_sql_from_intent(query, chat_id)

            # Add extracted parameters
            query = build_sql_with_params(base_query, params, chat_id)

            logger.info(f"Built SQL from natural language: {sanitize_log_query(query, max_length=100)}")
        except Exception as e:
            logger.warning(f"SQL building failed: {e}")
            # Fall through to validation with original query

    # Security validation
    validation = _validate_sql_query(query, chat_id)
    if not validation["valid"]:
        logger.warning(f"SQL blocked: {validation['reason']}")
        return {
            "error": "Query rejected for security reasons",
            "details": validation["reason"]
        }

    try:
        # Execute query
        results = await db.execute_query(query)

        # Log to audit
        await db.audit_log(
            user_id=None,
            action="sql_query_executed",
            chat_id=chat_id,
            details={"query": query[:500], "rows": len(results)}
        )

        # Extract columns from first row
        columns = list(results[0].keys()) if results else []

        # Context size protection for large results
        result_data = await format_results_with_limit(results, max_tokens=8000)

        return {
            "columns": columns,
            "data": result_data["results"],
            "count": result_data["shown_count"],
            "total_count": len(results),
            "truncated": result_data.get("truncated", False),
            "message": result_data.get("truncated_message", "")
        }

    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return {
            "error": str(e),
            "data": [],
            "count": 0
        }


async def general_answer(
    chat_id: int,
    query: str = "",
    db: Optional[Database] = None
) -> Dict[str, Any]:
    """
    Tool: Use LLM general knowledge with chat context.

    Automatically includes last 10 messages as context for the LLM.
    This allows the LLM to answer general questions while being
    aware of the chat context.

    Args:
        chat_id: Telegram chat ID (for context loading)
        query: Original user query (optional, for logging)
        db: Database instance (uses default if None)

    Returns:
        Dict with chat context for LLM
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

    # Always load minimal chat context (last 10 messages)
    messages = await db.get_messages(
        chat_id=chat_id,
        limit=10,
        days=7,
        exclude_deleted=True
    )

    # Format messages for context
    formatted_context = []
    for msg in messages:
        username = msg.get("username") or msg.get("first_name", "Unknown")
        content = msg.get("content", "")[:200]  # Truncate long messages
        timestamp = msg.get("timestamp", "")

        formatted_context.append({
            "timestamp": timestamp,
            "username": username,
            "content": content
        })

    return {
        "tool": "general_answer",
        "chat_context": {
            "chat_id": chat_id,
            "messages_count": len(formatted_context),
            "recent_messages": formatted_context
        },
        "message": "Answer the question using your general knowledge, "
                  "but be aware of the chat context provided above"
    }


# ============================================================================
# Natural Language to SQL Builder
# ============================================================================

def _build_sql_from_intent(query: str, chat_id: int) -> str:
    """
    Build base SQL query from natural language intent.

    Analyzes the query to determine what the user wants:
    - Count queries ("сколько", "количество") → COUNT(*)
    - List queries ("покажи", "список", "все") → SELECT *
    - User stats ("кто написал", "активность") → GROUP BY user_id
    - Time stats ("по дням", "по часам") → GROUP BY date/time

    Args:
        query: Natural language query
        chat_id: Chat ID for filtering

    Returns:
        Base SQL query (without LIMIT/date filter)

    Security: chat_id is validated as integer to prevent SQL injection.
              The query is later validated by _validate_sql_query().
    """
    # Validate chat_id is a safe integer value
    if not isinstance(chat_id, int) or chat_id <= 0 or chat_id > 2**63 - 1:
        # Return safe default query that will fail validation
        logger.warning(f"Invalid chat_id value in _build_sql_from_intent: {chat_id}")
        return "SELECT 1 WHERE 1=0"

    query_lower = query.lower()

    # Count queries
    count_patterns = [
        r'сколько',
        r'количество',
        r'count',
        r'число',
        r'много',
        r'всего',
    ]

    for pattern in count_patterns:
        if re.search(pattern, query_lower):
            return f"SELECT COUNT(*) as count FROM messages WHERE chat_id = {chat_id}"

    # User activity queries
    user_patterns = [
        r'кто\s+написал',
        r'активность\s+пользовател',
        r'топ\s+пользовател',
        r'most\s+active',
        r'user\s+activity',
    ]

    for pattern in user_patterns:
        if re.search(pattern, query_lower):
            return f"""
                SELECT u.username, COUNT(*) as message_count
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE m.chat_id = {chat_id}
            """

    # Default: list messages
    return f"SELECT * FROM messages WHERE chat_id = {chat_id}"


# ============================================================================
# Tool Security Validation (Enhanced v2.2)
# ============================================================================

def _validate_sql_query(query: str, chat_id: int) -> Dict[str, Any]:
    """
    Validate SQL query for safety with enhanced security checks.

    Security features:
    - SELECT only, no DML/DDL
    - Mandatory chat_id filter
    - UNION/INTERSECT/EXCEPT blocked
    - Subqueries blocked
    - Dangerous functions blocked
    - Mandatory LIMIT clause
    - Query complexity limits
    - Injection pattern detection

    Args:
        query: SQL query string
        chat_id: Required chat_id for filtering

    Returns:
        Dict with 'valid' (bool) and 'reason' (str if invalid)
    """
    q = query.strip()
    q_upper = query.upper().strip()

    # Basic query length check
    if len(q) > MAX_QUERY_LENGTH:
        return {
            "valid": False,
            "reason": f"Query too long (max {MAX_QUERY_LENGTH} chars, got {len(q)})"
        }

    # Check 1: Must start with SELECT (or WITH for CTE, but CTE must start with SELECT)
    if not q_upper.startswith('SELECT') and not q_upper.startswith('WITH'):
        return {
            "valid": False,
            "reason": "Query must start with SELECT or WITH"
        }

    # Check 2: Block set operations that can bypass filters
    set_operations = ['UNION', 'INTERSECT', 'EXCEPT']
    for op in set_operations:
        if re.search(r'\b' + op + r'\b', q_upper):
            return {
                "valid": False,
                "reason": f"Set operation '{op}' not allowed (can bypass filters)"
            }

    # Check 3: Block subqueries that can leak data
    # Look for (SELECT patterns
    if re.search(r'\(\s*SELECT\b', q_upper):
        return {
            "valid": False,
            "reason": "Subqueries not allowed (data leak risk)"
        }

    # Check 4: No IN clauses with subqueries
    if re.search(r'\bIN\s*\(', q_upper):
        return {
            "valid": False,
            "reason": "IN clauses with subqueries not allowed"
        }

    # Check 5: Forbidden DML/DDL keywords
    forbidden_ddl = [
        "DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE",
        "TRUNCATE", "REPLACE", "PRAGMA", "EXEC", "EXECUTE", "SCRIPT",
        "ATTACH", "DETACH", "VACUUM", "REINDEX"
    ]

    for keyword in forbidden_ddl:
        if re.search(r'\b' + keyword + r'\b', q_upper):
            return {
                "valid": False,
                "reason": f"Forbidden keyword: {keyword}"
            }

    # Check 6: No injection patterns
    injection_patterns = ['--', '/*', '*/', ';', '\\x', '0x']
    for pattern in injection_patterns:
        if pattern in q:
            return {
                "valid": False,
                "reason": f"SQL injection pattern detected: {pattern}"
            }

    # Check 7: No unclosed string literals
    single_quote_count = q.count("'")
    if single_quote_count % 2 != 0:
        return {
            "valid": False,
            "reason": "Unclosed string literal detected (odd quote count)"
        }

    # Check 8: Mandatory chat_id filter (CRITICAL - check before LIMIT)
    # Must match: chat_id = <number> or chat_id = ? or chat_id = :param
    chat_id_patterns = [
        rf'\bchat_id\s*=\s*{chat_id}\b',  # chat_id = 123
        r'\bchat_id\s*=\s*\?',           # chat_id = ?
        r'\bchat_id\s*=\s*:\w+',         # chat_id = :param
    ]

    has_chat_id = any(re.search(pattern, q, re.IGNORECASE) for pattern in chat_id_patterns)

    if not has_chat_id:
        return {
            "valid": False,
            "reason": f"Query must filter by chat_id = {chat_id} (or use parameterized ?)"
        }

    # Check 9: Mandatory LIMIT clause
    if 'LIMIT' not in q_upper:
        return {
            "valid": False,
            "reason": "Query must include LIMIT clause (max 1000 rows)"
        }

    # Check 10: Validate LIMIT value
    limit_match = re.search(r'\bLIMIT\s+(\d+)', q, re.IGNORECASE)
    if limit_match:
        limit_value = int(limit_match.group(1))
        if limit_value > MAX_LIMIT_VALUE:
            return {
                "valid": False,
                "reason": f"LIMIT too large (max {MAX_LIMIT_VALUE}, got {limit_value})"
            }
    else:
        # LIMIT with ? or :param is allowed
        if not re.search(r'\bLIMIT\s+[\?:]\w*', q, re.IGNORECASE):
            return {
                "valid": False,
                "reason": "Invalid LIMIT clause format"
            }

    # Check 11: Query complexity - max JOINs
    join_count = len(re.findall(r'\bJOIN\b', q_upper))
    if join_count > MAX_JOINS:
        return {
            "valid": False,
            "reason": f"Too many JOINs (max {MAX_JOINS}, got {join_count})"
        }

    # Check 11: Only allow specific table names
    allowed_tables = {'MESSAGES', 'USERS', 'CHATS', 'CHAT_MEMBERS'}
    from_matches = re.finditer(r'\bFROM\s+(\w+)', q, re.IGNORECASE)
    join_matches = re.finditer(r'\bJOIN\s+(\w+)', q, re.IGNORECASE)

    all_tables = set()
    for match in from_matches:
        all_tables.add(match.group(1).upper())
    for match in join_matches:
        all_tables.add(match.group(1).upper())

    for table in all_tables:
        if table not in allowed_tables:
            return {
                "valid": False,
                "reason": f"Table not allowed: {table}. Allowed: {sorted(allowed_tables)}"
            }

    # Check 12: Dangerous SQLite functions
    dangerous_functions = [
        'LOAD_EXTENSION', 'FTS5_TABLE', 'FTS4_TABLE',
        'FTS3_TOKENIZER', 'ICU_LOAD_COLLATION',
        'SQUOTE', 'QUOTE', 'GLOB', 'RTREE'
    ]

    for func in dangerous_functions:
        if func in q_upper:
            return {
                "valid": False,
                "reason": f"Dangerous function: {func}"
            }

    # Check 13: No CASE WHEN that could leak data via timing
    if re.search(r'\bCASE\s+WHEN\b', q_upper):
        return {
            "valid": False,
            "reason": "CASE WHEN not allowed (timing attack risk)"
        }

    # Check 14: No GROUP BY on sensitive columns without proper aggregation
    if 'GROUP BY' in q_upper and 'COUNT(' not in q_upper and 'SUM(' not in q_upper and 'AVG(' not in q_upper:
        # This is a weak heuristic but helps prevent some data leaks
        pass  # Allow for now, but could be enhanced

    return {"valid": True, "reason": ""}


# ============================================================================
# Tool Execution Engine
# ============================================================================

async def execute_tool_call(
    tool_call: Dict[str, Any],
    chat_id: int,
    db: Optional[Database] = None
) -> Any:
    """
    Execute a tool call from LLM.

    Args:
        tool_call: Tool call dict with 'function' name and 'arguments'
        chat_id: Chat context for tool execution
        db: Database instance

    Returns:
        Tool execution result
    """
    function_name = tool_call["function"]["name"]

    # Parse arguments (JSON string)
    try:
        arguments = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError as e:
        logger.error(f"Invalid tool arguments JSON: {e}")
        return {"error": f"Invalid arguments: {e}"}

    logger.info(f"Executing tool: {function_name} with args: {sanitize_log_args(arguments)}")

    # Map tool names to functions
    tools_map: Dict[str, Callable] = {
        "get_chat_history": lambda: get_chat_history(
            chat_id=chat_id,
            db=db,
            **arguments
        ),
        "sql_analytics": lambda: sql_analytics(
            chat_id=chat_id,
            db=db,
            **arguments
        ),
        "general_answer": lambda: general_answer(
            chat_id=chat_id,
            db=db,
            **arguments
        )
    }

    if function_name not in tools_map:
        return {"error": f"Unknown tool: {function_name}"}

    try:
        result = await tools_map[function_name]()
        return result
    except Exception as e:
        logger.error(f"Tool execution failed for {function_name}: {e}")
        return {"error": str(e)}


# ============================================================================
# Helper Functions
# ============================================================================

def get_tool_description(tool_name: str) -> str:
    """Get human-readable description of a tool."""
    descriptions = {
        "get_chat_history": "Retrieve chat messages with user info (smart params)",
        "sql_analytics": "Execute SQL queries for statistics (natural language OK)",
        "general_answer": "Use general knowledge WITH chat context (last 10 messages)"
    }
    return descriptions.get(tool_name, "Unknown tool")


def list_available_tools() -> List[str]:
    """List all available tool names."""
    return list(TOOL_DEFINITIONS.keys())
