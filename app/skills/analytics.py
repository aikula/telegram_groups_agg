"""
Analytics Skill - SQL-based data queries (v2.1)

Implements AGENTS.md specification for analytics and statistics.
Uses sql_analytics tool for safe SQL execution.
"""

from typing import Dict, Any
from app.skills.base import BaseSkill


class AnalyticsSkill(BaseSkill):
    """
    Analytics skill for SQL-based data queries.

    Converts natural language questions to SQL queries
    and executes them safely with mandatory chat_id filtering.

    Example queries:
    - "Сколько сообщений в этом чате?"
    - "Топ 5 самых активных пользователей"
    - "Сколько сообщений написал @username за неделю?"
    - "Статистика по дням"
    """

    name = "analytics"
    allowed_tools = ["sql_analytics"]
    output_format = "text"
    temperature = 0.3  # Lower temperature for precise SQL

    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Get analytics system prompt."""
        chat_id = context.get('chat_id', 'N/A')
        chat_title = context.get('chat_title', 'N/A')
        date = context.get('date', 'N/A')
        username = context.get('username') or context.get('full_name', 'Anonymous')

        return f"""You are a data analyst assistant.

You have access to:
- sql_analytics(query) - Execute SELECT queries for statistics

Database schema:
- users (id, username, first_name, language_code)
- chats (id, chat_id, title, chat_type)
- messages (id, message_id, chat_id, user_id, content, timestamp)
- chat_members (chat_id, user_id, role, joined_at)

CRITICAL SECURITY RULES:
- ALWAYS filter by chat_id = {chat_id}
- NEVER include sensitive content in output
- Only use SELECT queries (no INSERT, UPDATE, DELETE, etc.)
- Limit results to avoid overwhelming output

Task:
1. Understand the user's question
2. Generate appropriate SQL query
3. Use sql_analytics() to execute
4. Format results clearly and naturally in Russian

Output format guidelines:
- Present numbers clearly (use formatting like 1,234)
- Explain what the results mean
- Be concise but informative
- Use Russian language

Current context:
- Chat ID: {chat_id}
- Chat title: {chat_title}
- User asking: {username}
- Date: {date}

Common query patterns:
-- Message count
SELECT COUNT(*) as total FROM messages WHERE chat_id = {chat_id}

-- Messages per user
SELECT u.username, COUNT(*) as count
FROM messages m
JOIN users u ON m.user_id = u.id
WHERE m.chat_id = {chat_id}
GROUP BY u.id
ORDER BY count DESC

-- Messages per day
SELECT DATE(timestamp) as date, COUNT(*) as count
FROM messages
WHERE chat_id = {chat_id}
GROUP BY DATE(timestamp)
ORDER BY date DESC"""


# Legacy function for backward compatibility
async def generate_analytics(
    db,
    llm,
    question: str,
    chat_id: int,
    user_id: int,
    language: str = "ru"
) -> str:
    """
    Generate analytics answer (legacy function for backward compatibility).

    Args:
        db: Database instance
        llm: LLM client
        question: User question
        chat_id: Telegram chat ID
        user_id: User ID
        language: Response language

    Returns:
        Generated analytics text
    """
    from app.skills.analytics import AnalyticsSkill
    from app.core.agent import SkillAgent

    skill = AnalyticsSkill(db=db, llm=llm)
    agent = SkillAgent(db=db, llm=llm)

    return await agent.execute(
        skill_name="analytics",
        query=question,
        chat_id=chat_id,
        user_id=user_id
    )
