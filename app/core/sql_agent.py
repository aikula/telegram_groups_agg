"""
Core SQL Agent module - Safe SQL generation

Features:
- LLM-powered natural language to SQL conversion
- Query validation and security checks
- Read-only query enforcement
- Result limits and timeouts
- Support for common analytical queries
"""

import re
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from app.core.llm import LLMClient, get_llm_client
from app.core.i18n import get_text


logger = logging.getLogger(__name__)


# Dangerous SQL keywords that are never allowed
FORBIDDEN_KEYWORDS = {
    "DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE",
    "ALTER", "CREATE", "GRANT", "REVOKE", "EXECUTE",
    "EXEC", "SCRIPT",
}

# Allowed keywords for read-only queries
READONLY_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT",
    "INNER", "OUTER", "ON", "AND", "OR", "NOT", "IN",
    "LIKE", "BETWEEN", "IS", "NULL", "ORDER", "BY",
    "GROUP", "HAVING", "LIMIT", "OFFSET", "DISTINCT",
    "COUNT", "SUM", "AVG", "MIN", "MAX", "AS",
    "WITH", "UNION", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END",
    "CAST", "COALESCE", "NULLIF", "EXTRACT", "DATE", "TIME",
}

# Table names that are allowed in queries
ALLOWED_TABLES = {
    "users", "chats", "chat_members", "messages", "chat_settings",
    "llm_usage", "audit_log", "task_queue",
}


class SQLValidationError(Exception):
    """SQL query validation failed."""

    def __init__(self, message: str, sql: str = ""):
        super().__init__(message)
        self.sql = sql


class SQLAgent:
    """
    Safe SQL generation agent.

    Converts natural language questions to SQL queries
    with strict validation and security checks.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_results: int = 1000,
        timeout: float = 30.0
    ):
        """
        Initialize SQL Agent.

        Args:
            llm_client: LLM client for SQL generation
            max_results: Maximum results per query
            timeout: Query timeout in seconds
        """
        self._llm = llm_client or get_llm_client()
        self.max_results = max_results
        self.timeout = timeout

    async def generate_sql(
        self,
        question: str,
        chat_id: int,
        language: str = "ru"
    ) -> Dict[str, Any]:
        """
        Generate SQL from natural language question.

        Args:
            question: User's natural language question
            chat_id: Telegram chat ID (for filtering)
            language: Response language

        Returns:
            Dict with:
                - sql: Generated SQL query
                - explanation: Natural language explanation
                - confidence: Confidence score (0-1)
                - tokens_used: Token usage info

        Raises:
            SQLValidationError: If query generation fails validation
        """
        start_time = time.time()

        try:
            # Build prompt for LLM
            prompt = self._build_sql_prompt(question, chat_id, language)

            # Generate SQL with LLM
            result = await self._llm.generate(
                prompt,
                system_prompt=self._get_system_prompt(language),
                temperature=0.3  # Lower temperature for more deterministic SQL
            )

            # Extract SQL from response
            sql = self._extract_sql(result["text"])

            # Validate SQL
            self._validate_sql(sql)

            # Get explanation
            explanation = await self._explain_query(question, sql, language)

            elapsed = time.time() - start_time

            return {
                "sql": sql,
                "explanation": explanation,
                "confidence": self._estimate_confidence(result, elapsed),
                "tokens_used": result["usage"],
                "elapsed_ms": round(elapsed * 1000, 2),
            }

        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            raise SQLValidationError(
                get_text("sql_agent.generation_error", lang=language),
                sql=""
            ) from e

    def _build_sql_prompt(
        self,
        question: str,
        chat_id: int,
        language: str
    ) -> str:
        """Build prompt for SQL generation."""
        schema = self._get_schema_description(language)

        return get_text(
            "sql_agent.prompt",
            lang=language,
            schema=schema,
            question=question,
            chat_id=chat_id
        )

    def _get_system_prompt(self, language: str) -> str:
        """Get system prompt for SQL generation."""
        return get_text(
            "sql_agent.system_prompt",
            lang=language
        )

    def _get_schema_description(self, language: str) -> str:
        """Get database schema description for LLM."""
        return get_text(
            "sql_agent.schema",
            lang=language
        )

    def _extract_sql(self, response: str) -> str:
        """
        Extract SQL query from LLM response.

        Handles markdown code blocks and plain text.
        """
        # Try to extract from markdown code block
        sql_match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        # Try without language specifier
        sql_match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
        if sql_match:
            candidate = sql_match.group(1).strip()
            if candidate.upper().startswith("SELECT"):
                return candidate

        # Check if response is just SQL
        cleaned = response.strip()
        if cleaned.upper().startswith("SELECT"):
            return cleaned

        # Find first SELECT statement
        select_match = re.search(
            r"(SELECT\s+.*?;?)",
            cleaned,
            re.DOTALL | re.IGNORECASE
        )
        if select_match:
            return select_match.group(1).strip()

        raise SQLValidationError("Could not extract SQL from response")

    def _validate_sql(self, sql: str) -> None:
        """
        Validate SQL query for safety.

        Raises:
            SQLValidationError: If query is unsafe
        """
        sql_upper = sql.upper().strip()

        # Check for forbidden keywords
        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", sql_upper):
                raise SQLValidationError(
                    f"Forbidden keyword detected: {keyword}",
                    sql=sql
                )

        # Must start with SELECT or WITH (CTE)
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            raise SQLValidationError(
                "Query must be SELECT or WITH (CTE) only",
                sql=sql
            )

        # Check for allowed table names
        # First, extract CTE table names to exclude them from validation
        cte_tables = set()
        cte_match = re.search(r"WITH\s+(.+?)\s+SELECT", sql_upper, re.DOTALL | re.IGNORECASE)
        if cte_match:
            # Extract CTE names (format: cte_name AS (...)
            for cte in re.findall(r"(\w+)\s+AS\s*\(", cte_match.group(1)):
                cte_tables.add(cte)

        tables_found = re.findall(
            r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)",
            sql_upper
        )
        for table_tuple in tables_found:
            table = next(t for t in table_tuple if t)
            # Skip CTE tables
            if table in cte_tables:
                continue
            if table.lower() not in ALLOWED_TABLES:
                raise SQLValidationError(
                    f"Table not allowed: {table}",
                    sql=sql
                )

        # Check for LIMIT to prevent large result sets
        if "LIMIT" not in sql_upper:
            logger.warning("Query missing LIMIT, appending default")
            sql = f"{sql.rstrip(';')} LIMIT {self.max_results};"

        # Additional security checks
        self._check_for_sql_injection(sql)

    def _check_for_sql_injection(self, sql: str) -> None:
        """Check for common SQL injection patterns."""
        # Check for comment injection
        if "--" in sql or "/*" in sql:
            raise SQLValidationError("SQL comment detected", sql=sql)

        # Check for multiple statements
        if sql.count(";") > 1:
            raise SQLValidationError("Multiple statements detected", sql=sql)

        # Check for hex encoding attempts
        if re.search(r"0x[0-9A-Fa-f]+", sql):
            raise SQLValidationError("Hex encoding detected", sql=sql)

        # Check for suspicious functions
        dangerous_funcs = ["LOAD_FILE", "INTO OUTFILE", "EXEC"]
        for func in dangerous_funcs:
            if func in sql.upper():
                raise SQLValidationError(f"Dangerous function: {func}", sql=sql)

    async def _explain_query(
        self,
        question: str,
        sql: str,
        language: str
    ) -> str:
        """Generate natural language explanation of the query."""
        prompt = get_text(
            "sql_agent.explain_prompt",
            lang=language,
            sql=sql,
            question=question
        )

        try:
            result = await self._llm.generate(prompt, temperature=0.5)
            return result["text"].strip()
        except Exception as e:
            logger.warning(f"Explanation generation failed: {e}")
            return get_text("sql_agent.explain_failed", lang=language)

    def _estimate_confidence(
        self,
        result: Dict[str, Any],
        elapsed: float
    ) -> float:
        """
        Estimate confidence in generated SQL.

        Based on:
        - Finish reason (stop = high confidence)
        - Elapsed time (faster = higher confidence)
        - Token count (moderate = better)
        """
        confidence = 0.5

        # Finish reason
        if result.get("finish_reason") == "stop":
            confidence += 0.2

        # Response time (under 5 seconds is good)
        if elapsed < 5.0:
            confidence += 0.2

        # Token count (moderate length is better)
        total_tokens = result.get("usage", {}).get("total_tokens", 0)
        if 100 < total_tokens < 2000:
            confidence += 0.1

        return min(confidence, 1.0)

    async def format_results(
        self,
        question: str,
        results: List[Tuple],
        sql: str,
        language: str = "ru"
    ) -> Dict[str, Any]:
        """
        Format SQL results into natural language.

        Args:
            question: Original question
            results: Query results (list of tuples)
            sql: SQL query that was executed
            language: Response language

        Returns:
            Dict with formatted text and metadata
        """
        if not results:
            return {
                "text": get_text("sql_agent.no_results", lang=language),
                "row_count": 0,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                },
                "cost_usd": 0.0
            }

        # Format results as text table
        results_text = self._format_results_table(results)

        # Generate natural language summary
        prompt = get_text(
            "sql_agent.format_prompt",
            lang=language,
            question=question,
            sql=sql,
            count=len(results),
            results=results_text[:2000]  # Truncate for context
        )

        result = await self._llm.generate(prompt, temperature=0.7)

        return {
            "text": result["text"],
            "row_count": len(results),
            "usage": result["usage"],
            "cost_usd": result.get("cost_usd", 0.0)
        }

    def _format_results_table(self, results: List[Tuple]) -> str:
        """Format results as text table."""
        if not results:
            return ""

        lines = []
        for row in results:
            lines.append(" | ".join(str(v) for v in row))

        return "\n".join(lines)

    def get_allowed_tables(self) -> List[str]:
        """Get list of allowed table names."""
        return sorted(ALLOWED_TABLES)

    def is_table_allowed(self, table_name: str) -> bool:
        """Check if table is allowed in queries."""
        return table_name.lower() in ALLOWED_TABLES


# Singleton instance
_sql_agent: Optional[SQLAgent] = None


def get_sql_agent() -> SQLAgent:
    """Get SQL agent singleton instance."""
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SQLAgent()
    return _sql_agent
