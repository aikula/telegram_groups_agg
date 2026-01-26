"""
Thread summary skill - Summarize message threads (v2.0)

Generates concise summaries of specific message threads/conversations.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

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
class ThreadSummarySkillConfig(SkillConfig):
    """Configuration for thread summary skill."""

    max_messages: int = 50
    max_tokens: Optional[int] = None
    temperature: float = 0.6
    language: str = "ru"
    context_before: int = 5
    context_after: int = 5


class ThreadSummarySkill(BaseSkill):
    """
    Thread summary skill for summarizing conversations.

    Summarizes specific message threads based on reply chains
    or recent context around a target message.
    """

    def __init__(
        self,
        db,
        llm=None,
        config: Optional[ThreadSummarySkillConfig] = None
    ):
        super().__init__(db, llm, config or ThreadSummarySkillConfig())

    async def execute(
        self,
        chat_id: int,
        message_id: Optional[int] = None,
        reply_count: int = 10,
        language: Optional[str] = None,
        **kwargs
    ) -> SkillResult:
        """
        Generate a thread summary.

        Args:
            chat_id: Telegram chat ID
            message_id: Target message ID (if None, summarize recent)
            reply_count: Number of messages to include
            language: Summary language
            **kwargs: Additional parameters

        Returns:
            SkillResult with thread summary
        """
        try:
            validate_chat_id(chat_id)

            language = language or self.config.language
            language = validate_language(language)

            # Get messages for the thread
            if message_id:
                messages = await self._get_thread_by_message_id(
                    chat_id=chat_id,
                    message_id=message_id
                )
            else:
                messages = await self._get_recent_thread(
                    chat_id=chat_id,
                    count=reply_count
                )

            if not messages:
                no_thread_text = get_text("thread_summary.no_thread", lang=language)
                return self._create_success_result(
                    text=no_thread_text,
                    metadata={"chat_id": chat_id, "message_count": 0}
                )

            # Format messages for prompt
            formatted_messages = self._format_thread_messages(messages)

            # Build prompt
            prompt = get_text(
                "thread_summary.prompt",
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
                    "message_id": message_id,
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
            logger.error(f"Thread summary skill failed for chat {chat_id}: {e}")
            return self._create_error_result(
                error_message=f"Thread summary failed: {str(e)}",
                details={"chat_id": chat_id, "message_id": message_id}
            )

    async def _get_thread_by_message_id(
        self,
        chat_id: int,
        message_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get thread context around a specific message.

        Args:
            chat_id: Telegram chat ID
            message_id: Target message ID

        Returns:
            List of messages forming the thread
        """
        # Get context around the message
        context = await self.db.get_message_context(
            message_id=message_id,
            before=self.config.context_before,
            after=self.config.context_after
        )

        if not context:
            return []

        # Combine all messages
        messages = []
        if context.get("before"):
            messages.extend(context["before"])
        if context.get("target"):
            messages.append(context["target"])
        if context.get("after"):
            messages.extend(context["after"])

        return messages

    async def _get_recent_thread(
        self,
        chat_id: int,
        count: int
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages as a thread.

        Args:
            chat_id: Telegram chat ID
            count: Number of messages to include

        Returns:
            List of recent messages
        """
        return await self._get_messages(
            chat_id=chat_id,
            limit=count
        )

    def _format_thread_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Format thread messages for LLM prompt.

        Args:
            messages: List of message dictionaries

        Returns:
            Formatted message string
        """
        lines = []
        for msg in messages:
            username = msg.get("username") or msg.get("first_name", "User")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")

            lines.append(f"[{timestamp}] {username}: {content}")

        return "\n".join(lines)

    async def summarize_reply_chain(
        self,
        chat_id: int,
        message_id: int,
        language: str = "ru"
    ) -> SkillResult:
        """
        Summarize the reply chain starting from a message.

        Args:
            chat_id: Telegram chat ID
            message_id: Starting message ID
            language: Summary language

        Returns:
            SkillResult with reply chain summary
        """
        return await self.execute(
            chat_id=chat_id,
            message_id=message_id,
            language=language
        )

    async def summarize_recent(
        self,
        chat_id: int,
        count: int = 20,
        language: str = "ru"
    ) -> SkillResult:
        """
        Summarize recent messages.

        Args:
            chat_id: Telegram chat ID
            count: Number of recent messages
            language: Summary language

        Returns:
            SkillResult with recent messages summary
        """
        return await self.execute(
            chat_id=chat_id,
            message_id=None,
            reply_count=count,
            language=language
        )


async def generate_thread_summary(
    db,
    chat_id: int,
    message_id: Optional[int] = None,
    reply_count: int = 10,
    language: str = "ru"
) -> SkillResult:
    """
    Convenience function to generate a thread summary.

    Args:
        db: Database instance
        chat_id: Telegram chat ID
        message_id: Target message ID (None for recent)
        reply_count: Number of messages to include
        language: Summary language

    Returns:
        SkillResult with thread summary
    """
    skill = ThreadSummarySkill(db)
    return await skill.execute(
        chat_id=chat_id,
        message_id=message_id,
        reply_count=reply_count,
        language=language
    )
