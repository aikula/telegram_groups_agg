"""
Tools module - Low-level operations for AI agents (v2.1)

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
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta

from app.core.db import Database

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
            "description": "Retrieve recent messages from chat with user information. Use this to get context about what was discussed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum messages to return (default: 20, max: 100)",
                        "default": 20
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only messages from last N days (default: 7)",
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
            "description": "Execute safe SELECT SQL query for analytics, statistics, and counts. Must include chat_id filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query with chat_id filter (e.g., SELECT COUNT(*) FROM messages WHERE chat_id = X)"
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
            "description": "Use general LLM knowledge without accessing chat database. Use for questions that don't require chat context.",
            "parameters": {
                "type": "object",
                "properties": {},
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
    db: Optional[Database] = None
) -> Dict[str, Any]:
    """
    Tool: Get recent chat messages with user information.

    Args:
        chat_id: Telegram chat ID
        limit: Maximum messages to return (max: 100)
        days: Only messages from last N days
        db: Database instance (uses default if None)

    Returns:
        Dict with messages list and count
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

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

    # Format for LLM consumption
    formatted = []
    for msg in messages:
        formatted.append({
            "timestamp": msg.get("timestamp", ""),
            "user_id": msg.get("user_id"),
            "username": msg.get("username") or msg.get("first_name", "Unknown"),
            "content": msg.get("content", "")
        })

    return {
        "messages": formatted,
        "count": len(formatted)
    }


async def sql_analytics(
    chat_id: int,
    query: str,
    db: Optional[Database] = None
) -> Dict[str, Any]:
    """
    Tool: Execute safe SQL analytics query.

    Security features:
    - SELECT queries only
    - Mandatory chat_id filter
    - Forbidden keyword detection
    - Injection pattern detection
    - Read-only execution

    Args:
        chat_id: Telegram chat ID (for filtering and validation)
        query: SQL SELECT query
        db: Database instance (uses default if None)

    Returns:
        Dict with columns, data, and count
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

    logger.info(f"Tool sql_analytics: chat_id={chat_id}, query={query[:100]}...")

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

        return {
            "columns": columns,
            "data": results,
            "count": len(results)
        }

    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return {
            "error": str(e),
            "data": [],
            "count": 0
        }


async def general_answer() -> Dict[str, Any]:
    """
    Tool: Placeholder for general knowledge answer.

    This is a no-op tool that signals the LLM should use
    its general knowledge without accessing the database.

    Returns:
        Dict indicating general knowledge should be used
    """
    return {
        "message": "Use your general knowledge to answer this question",
        "tool": "general_answer"
    }


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

    logger.info(f"Executing tool: {function_name} with args: {arguments}")

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
        "general_answer": lambda: general_answer()
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
        "get_chat_history": "Retrieve chat messages with user info",
        "sql_analytics": "Execute SQL queries for statistics",
        "general_answer": "Use general knowledge without database"
    }
    return descriptions.get(tool_name, "Unknown tool")


def list_available_tools() -> List[str]:
    """List all available tool names."""
    return list(TOOL_DEFINITIONS.keys())
