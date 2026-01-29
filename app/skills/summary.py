"""
Summary skill - Generate chat summaries (v2.1)

Implements AGENTS.md specification with tool calling support.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from app.skills.base import (
    BaseSkill,
    SkillResult,
    SkillConfig,
    SkillError,
    validate_chat_id,
    validate_language,
)
from app.core.i18n import get_text
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SummarySkillConfig(SkillConfig):
    """Configuration for summary skill."""

    max_messages: int = 200
    max_tokens: Optional[int] = None
    temperature: float = 0.6  # Lower temperature for consistent summaries
    language: str = "ru"
    include_timestamps: bool = True
    include_usernames: bool = True


class SummarySkill(BaseSkill):
    """
    Summary skill for generating chat summaries.

    Generates concise summaries of chat discussions covering
    key topics, decisions, and action items.

    AGENTS.md v2.1 specification:
    - Uses tools: get_chat_history, sql_analytics
    - Output format: markdown
    - Temperature: 0.6
    """

    name = "summary"
    allowed_tools = ["get_chat_history", "sql_analytics"]
    output_format = "markdown"
    temperature = 0.6

    def __init__(
        self,
        db,
        llm=None,
        config: Optional[SummarySkillConfig] = None
    ):
        super().__init__(db, llm, config or SummarySkillConfig())

    def _get_default_prompt(self, context: Dict[str, Any]) -> str:
        """Get summary system prompt."""
        return f"""Ты - эксперт по созданию сводок чатов.

Задача: Создай структурированную сводку активности чата.

Доступные инструменты:
- get_chat_history(days) - Получить сообщения для сводки
- sql_analytics(query) - Получить статистику

## ВАЖНЫЕ ПРАВИЛА ОТВЕТА:

1. **Будь кратким и конкретным**
   - Избегай вступлений вроде "Вот сводка чата"
   - Избегай канцелярщины

2. **Используй естественный русский**
   - Разговорный стиль
   - Без лишних усложнений

Формат вывода (Markdown):
## 📊 Период
{{start_date}} - {{end_date}}

## 🔥 Основные темы
1. **Тема 1** (N сообщений)
   - Описание темы
   - Ключевые моменты

2. **Тема 2** (M сообщений)
   - Описание темы

## ✅ Принятые решения
- Решение 1 (@username, дата)
- Решение 2 (@username, дата)

## 💬 Активные участники
1. @username1 - N сообщений
2. @username2 - M сообщений

## ❓ Открытые вопросы
- Вопрос 1
- Вопрос 2

## 📝 Заметки
- Дополнительная информация

Правила:
- Используй русский
- Указывай конкретные даты и @имена
- Котируй важные сообщения
- Будь кратким, но исчерпывающим
- Организуй информацию логически
- Выделяй действия и решения

Текущий контекст:
- Чат: {context.get('chat_title', 'N/A')}
- Chat ID: {context['chat_id']}
- Дата: {context.get('date', 'N/A')}

When creating summaries:
1. Use get_chat_history() to retrieve messages
2. Group messages by topics and themes
3. Identify key decisions and action items
4. List most active participants
5. Note any unresolved questions
6. Format as structured markdown"""

    async def format_output(self, text: str) -> str:
        """Format summary output (markdown)."""
        # Ensure proper markdown formatting
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)

        formatted = '\n'.join(lines)

        # Ensure Telegram limit
        if len(formatted) > 4000:
            formatted = formatted[:3950] + "\n\n... (обрезано)"

        return formatted

    # Legacy methods for backward compatibility

    async def execute(
        self,
        chat_id: int,
        days: int = 1,
        language: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **kwargs
    ) -> SkillResult:
        """
        Generate a chat summary (legacy method).

        Args:
            chat_id: Telegram chat ID
            days: Number of days to summarize (default: 1)
            language: Language for summary (default: from config)
            custom_prompt: Optional custom instructions
            **kwargs: Additional parameters

        Returns:
            SkillResult with generated summary
        """
        try:
            validate_chat_id(chat_id)

            language = language or self.config.language
            language = validate_language(language)

            # Get messages
            messages = await self._get_messages(
                chat_id=chat_id,
                days=days
            )

            if not messages:
                no_messages_text = get_text("summary.no_messages", lang=language)
                return self._create_success_result(
                    text=no_messages_text,
                    metadata={"chat_id": chat_id, "days": days, "message_count": 0}
                )

            # Format messages for prompt
            formatted_messages = self._format_messages(messages)

            # Build prompt
            if custom_prompt:
                prompt = get_text(
                    "summary.custom_prompt",
                    lang=language,
                    custom_prompt=custom_prompt,
                    messages=formatted_messages
                )
            else:
                prompt = get_text(
                    "summary.prompt",
                    lang=language,
                    messages=formatted_messages
                )

            # Call LLM
            result = await self._call_llm(
                prompt=prompt,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            # Log usage
            await self._log_usage(
                chat_id=chat_id,
                usage=result["usage"],
                cost_usd=result.get("cost_usd", 0.0)
            )

            return self._create_success_result(
                text=result["text"],
                metadata={
                    "chat_id": chat_id,
                    "days": days,
                    "message_count": len(messages),
                    "language": language,
                    "model": result.get("model", "")
                },
                usage=result["usage"],
                cost_usd=result.get("cost_usd", 0.0)
            )

        except SkillError:
            raise
        except Exception as e:
            logger.error(f"Summary skill failed for chat {chat_id}: {e}")
            return self._create_error_result(
                error_message=f"Summary generation failed: {str(e)}",
                details={"chat_id": chat_id, "days": days}
            )

    async def generate_daily_summary(
        self,
        chat_id: int,
        language: str = "ru"
    ) -> SkillResult:
        """Generate a daily summary (last 24 hours)."""
        return await self.execute(
            chat_id=chat_id,
            days=1,
            language=language
        )

    async def generate_weekly_summary(
        self,
        chat_id: int,
        language: str = "ru"
    ) -> SkillResult:
        """Generate a weekly summary (last 7 days)."""
        return await self.execute(
            chat_id=chat_id,
            days=7,
            language=language
        )

    async def generate_custom_summary(
        self,
        chat_id: int,
        custom_prompt: str,
        days: int = 1,
        language: str = "ru"
    ) -> SkillResult:
        """Generate a summary with custom instructions."""
        return await self.execute(
            chat_id=chat_id,
            days=days,
            language=language,
            custom_prompt=custom_prompt
        )


async def generate_summary(
    db,
    chat_id: int,
    days: int = 1,
    language: str = "ru",
    custom_prompt: Optional[str] = None
) -> SkillResult:
    """
    Convenience function to generate a summary.

    Args:
        db: Database instance
        chat_id: Telegram chat ID
        days: Number of days to summarize
        language: Summary language
        custom_prompt: Optional custom instructions

    Returns:
        SkillResult with generated summary
    """
    skill = SummarySkill(db)
    return await skill.execute(
        chat_id=chat_id,
        days=days,
        language=language,
        custom_prompt=custom_prompt
    )
