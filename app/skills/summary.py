"""
Summary skill - Generate chat summaries (v2.0)

Generates daily/weekly summaries of chat messages using LLM.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import timedelta

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
    temperature: float = 0.6  # Lower temperature for more consistent summaries
    language: str = "ru"
    include_timestamps: bool = True
    include_usernames: bool = True


class SummarySkill(BaseSkill):
    """
    Summary skill for generating chat summaries.

    Generates concise summaries of chat discussions covering
    key topics, decisions, and action items.
    """

    def __init__(
        self,
        db,
        llm=None,
        config: Optional[SummarySkillConfig] = None
    ):
        super().__init__(db, llm, config or SummarySkillConfig())

    async def execute(
        self,
        chat_id: int,
        days: int = 1,
        language: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **kwargs
    ) -> SkillResult:
        """
        Generate a chat summary.

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
        """
        Generate a daily summary (last 24 hours).

        Args:
            chat_id: Telegram chat ID
            language: Summary language

        Returns:
            SkillResult with daily summary
        """
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
        """
        Generate a weekly summary (last 7 days).

        Args:
            chat_id: Telegram chat ID
            language: Summary language

        Returns:
            SkillResult with weekly summary
        """
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
        """
        Generate a summary with custom instructions.

        Args:
            chat_id: Telegram chat ID
            custom_prompt: Custom instructions for the summary
            days: Number of days to summarize
            language: Summary language

        Returns:
            SkillResult with custom summary
        """
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
