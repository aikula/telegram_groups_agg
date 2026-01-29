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

    def _get_default_prompt(self, context: Dict[str, Any]) -> str:
        """Get analytics system prompt."""
        chat_id = context.get('chat_id', 'N/A')
        chat_title = context.get('chat_title', 'N/A')
        date = context.get('date', 'N/A')
        username = context.get('username') or context.get('full_name', 'Anonymous')

        return f"""Ты - ассистент по аналитике данных.

Доступные инструменты:
- sql_analytics(query) - Выполнять SELECT запросы для статистики

## ВАЖНЫЕ ПРАВИЛА ОТВЕТА:

1. **Будь кратким и конкретным**
   - Отвечай прямо на вопрос
   - Избегай вступлений типа "Вот результаты..."

2. **Используй естественный русский**
   - Разговорный стиль
   - Читаемые форматы чисел

Схема базы данных:
- users (id, username, first_name, language_code)
- chats (id, chat_id, title, chat_type)
- messages (id, message_id, chat_id, user_id, content, timestamp)
- chat_members (chat_id, user_id, role, joined_at)

КРИТИЧЕСКИЕ ПРАВИЛА БЕЗОПАСНОСТИ:
- ВСЕГДА фильтруй по chat_id = {chat_id}
- НИКОГДА не включай конфиденциальные данные в вывод
- Используй только SELECT запросы (без INSERT, UPDATE, DELETE и т.д.)
- Ограничивай результаты, чтобы не перегружать вывод

Задача:
1. Понимай вопрос пользователя
2. Генерируй SQL запрос
3. Используй sql_analytics() для выполнения
4. Форматируй результаты понятно и естественно на русском

Форматирование результатов:
- Числа форматируй четко (1 234)
- Объясняй, что означают результаты
- Будь кратким, но информативным
- Используй русский язык

Текущий контекст:
- Chat ID: {chat_id}
- Chat title: {chat_title}
- User: {username}
- Date: {date}

Типичные паттерны запросов:
-- Количество сообщений
SELECT COUNT(*) as total FROM messages WHERE chat_id = {chat_id}

-- Сообщений по пользователям
SELECT u.username, COUNT(*) as count
FROM messages m
JOIN users u ON m.user_id = u.id
WHERE m.chat_id = {chat_id}
GROUP BY u.id
ORDER BY count DESC

-- Сообщений по дням
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
