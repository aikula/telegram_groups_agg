"""
QA Skill - Answer questions with chat context (v2.2)

Implements AGENTS.md specification for question answering.
Uses tools to retrieve chat history, run analytics, or provide general answers.

v2.2 Features:
- Smart parameter extraction from natural language
- Context size protection
- Batch mode for large results
"""

from typing import Dict, Any, List
from app.skills.base import BaseSkill


class QASkill(BaseSkill):
    """
    Question-Answering skill.

    Answers user questions about chat content using available tools:
    - get_chat_history: Retrieve messages for context (smart limit/days extraction)
    - sql_analytics: Get statistics and counts (natural language → SQL)
    - general_answer: Use LLM general knowledge

    Example queries:
    - "Что обсуждали вчера?"
    - "Сколько сообщений написал @username?"
    - "Когда было последнее упоминание проекта X?"
    - "Покажи последние 3 сообщения"
    - "Сколько сообщений за неделю?"
    - "Топ 5 самых активных пользователей"
    """

    name = "qa"
    allowed_tools = ["get_chat_history", "sql_analytics", "general_answer"]
    output_format = "text"
    temperature = 0.7

    def _get_default_prompt(self, context: Dict[str, Any]) -> str:
        """Get QA system prompt."""
        chat_id = context.get('chat_id', 'N/A')
        chat_title = context.get('chat_title', 'N/A')
        username = context.get('username') or context.get('full_name', 'Anonymous')
        date = context.get('date', 'N/A')

        return f"""Ты - полезный ассистент чата на русском языке.

## ВАЖНЫЕ ПРАВИЛА ОТВЕТА:

1. **ОТВЕЧАЙ НАПРЯМУЮ** - без вступлений и объяснений
   ❌ Плохо: "Отвечая на ваш вопрос, я проанализировал..."
   ❌ Плохо: "По вашему запросу, я нашел..."
   ✅ Хорошо: "Вчера было 47 сообщений."
   ✅ Хорошо: "Да, в понедельник обсуждали проект X."

2. **Не упоминай @имя пользователя в ответе**
   ❌ Плохо: "@username, по вашему вопросу..."
   ✅ Хорошо: "По вашему вопросу..."

3. **Будь кратким и по существу**
   - 2-4 предложения для большинства ответов
   - Для списков/dashboards можно быть длиннее
   - Избегай воды и повторений

4. **Используй естественный русский**
   - Разговорный стиль, как в обычном чате
   - Без канцелярщины и сложных конструкций
   - Используй эмодзи умеренно (1-2 на ответ)

## Доступные инструменты:

### 1. get_chat_history(query)
Получает сообщения из чата. Автоматически извлекает limit и days из запроса.

Примеры:
- "последние 3 сообщения" → limit=3
- "сообщения за неделю" → days=7
- "что обсуждали вчера" → days=1

Формат: {{"query": "последние 3 сообщения"}}

### 2. sql_analytics(query)
Выполняет аналитические запросы. Понимает естественный язык.

Примеры:
- "сколько сообщений сегодня"
- "топ 5 активных участников"
- "количество сообщений за неделю"

Формат: {{"query": "сколько сообщений сегодня"}}

### 3. general_answer(query)
Использует общие знания С контекстом чата (последние 10 сообщений).

Используй когда:
- Вопросы о погоде, новостях, внешних событиях
- Нужны общие знания + понимание контекста чата

Формат: {{"query": "оригинальный вопрос"}}

## Контекст:
- Чат: {chat_title}
- Дата: {date}

## Примеры хороших ответов:

Вопрос: "Сколько сообщений вчера?"
Ответ: "Вчера было 47 сообщений. Больше всего написал @alex (15 сообщений)."

Вопрос: "Что обсуждали сегодня?"
Ответ: "Сегодня обсуждали три темы: план спринта, обед в пятницу и новый дизайн."

Вопрос: "Когда было последнее упоминание проекта?"
Ответ: "Проект упоминали 2 дня назад, в понедельник в 14:30. @maria предложила пересмотреть сроки."
"""



# Legacy function for backward compatibility
async def generate_qa_answer(
    db,
    llm,
    question: str,
    chat_id: int,
    user_id: int,
    language: str = "ru"
) -> str:
    """
    Generate QA answer (legacy function for backward compatibility).

    Args:
        db: Database instance
        llm: LLM client
        question: User question
        chat_id: Telegram chat ID
        user_id: User ID
        language: Response language

    Returns:
        Generated answer text
    """
    from app.skills.qa import QASkill
    from app.core.agent import SkillAgent

    skill = QASkill(db=db, llm=llm)
    agent = SkillAgent(db=db, llm=llm)

    return await agent.execute(
        skill_name="qa",
        query=question,
        chat_id=chat_id,
        user_id=user_id
    )
