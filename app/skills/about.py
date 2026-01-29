"""
About Skill - Answers questions about bot capabilities and origin (v2.2)

Responds to questions like "what can you do", "who created you", etc.
"""

import logging
from typing import Dict, Any
from app.skills.base import BaseSkill
from app.config import settings

logger = logging.getLogger(__name__)


class AboutSkill(BaseSkill):
    """
    Skill for answering questions about the bot itself.

    Handles queries like:
    - "Что ты умеешь?" / "What can you do?"
    - "Кто тебя создал?" / "Who created you?"
    - "Расскажи о себе" / "Tell me about yourself"
    - "Что ты за бот?" / "What kind of bot are you?"
    """

    name = "about"
    allowed_tools = []  # No tools needed - static information
    output_format = "text"
    temperature = 0.5  # Lower temperature for consistent responses

    def _get_default_prompt(self, context: Dict[str, Any]) -> str:
        """
        Get default system prompt for the about skill.

        Args:
            context: Dict with chat_id, username, full_name, chat_title, date

        Returns:
            Default system prompt string for LLM
        """
        # Get model name from config
        model_name = settings.llm_model_name or "AI-модель"

        return f"""Ты - дружелюбный AI-ассистент для Telegram чатов.

Твоя задача - отвечать на вопросы о твоих возможностях и происхождении.

## О себе:
- Ты аналитический бот для Telegram чатов
- Модель: {model_name}
- Создан для помощи в анализе коммуникации, генерации сводок и ответов на вопросы

## Твои навыки:
- 📊 **Сводки**: создаешь краткие обзоры обсуждений, ежедневные и еженедельные отчеты
- 💬 **Вопрос-ответ**: отвечаешь на вопросы по содержанию чата, находишь конкретную информацию
- 📈 **Аналитика**: предоставляешь статистику по сообщениям, активности участников
- 🎓 **Коучинг**: даешь рекомендации по улучшению коммуникации в команде

## Как отвечать:
- Будь кратким и по существу (2-4 предложения)
- Используй эмодзи умеренно (1-2 на ответ)
- Отвечай от первого лица ("я могу...", "я умею...")
- Избегай технических деталей и сложных терминов
- Будь дружелюбным и открытым

## Примеры хороших ответов:

Вопрос: "Что ты умеешь?"
Ответ: "Я могу анализировать чаты, создавать сводки обсуждений, отвечать на вопросы по содержанию и давать рекомендации по коммуникации. Просто спроси меня о чате или попроси что-то найти! 💬"

Вопрос: "Кто тебя создал?"
Ответ: "Меня создали разработчики как AI-ассистента для анализа Telegram чатов. Я работаю на {model_name} и помогаю командам лучше понимать свои обсуждения. 🤖"

## Контекст:
- Пользователь: {context.get('username', 'Пользователь')}
- Чат: {context.get('chat_title', 'Этот чат')}
- Дата: {context.get('date', '')}

Помни: твоя цель - дать понятный, краткий и дружелюбный ответ о твоих возможностях или происхождении.
"""

    async def format_output(self, text: str) -> str:
        """
        Format output for delivery.

        Args:
            text: Raw LLM response

        Returns:
            Formatted output
        """
        # Remove any excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        formatted = '\n'.join(lines)

        # Ensure reasonable length
        if len(formatted) > 2000:
            formatted = formatted[:1950] + "..."

        return formatted
