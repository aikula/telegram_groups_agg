"""
Base skill class and common types for all skills (v2.0)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from abc import ABC, abstractmethod

from app.core.db import Database
from app.core.llm import LLMClient, get_llm_client
from app.core.i18n import get_text

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result of a skill execution."""

    success: bool
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "text": self.text,
            "metadata": self.metadata,
            "usage": self.usage,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class SkillConfig:
    """Configuration for a skill."""

    max_messages: int = 100
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    language: str = "ru"
    include_system_prompt: bool = True


class SkillError(Exception):
    """Base exception for skill-related errors."""

    def __init__(self, message: str, skill_name: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.skill_name = skill_name
        self.details = details or {}


class BaseSkill(ABC):
    """
    Base class for all AI-powered skills.

    Provides common functionality for message retrieval,
    LLM interaction, and result formatting.
    """

    def __init__(
        self,
        db: Database,
        llm: Optional[LLMClient] = None,
        config: Optional[SkillConfig] = None
    ):
        """
        Initialize the skill.

        Args:
            db: Database instance
            llm: Optional LLM client (uses default if None)
            config: Optional skill configuration
        """
        self.db = db
        self.llm = llm or get_llm_client()
        self.config = config or SkillConfig()
        self.skill_name = self.__class__.__name__

    @abstractmethod
    async def execute(
        self,
        chat_id: int,
        **kwargs
    ) -> SkillResult:
        """
        Execute the skill.

        Args:
            chat_id: Telegram chat ID
            **kwargs: Additional skill-specific parameters

        Returns:
            SkillResult with generated text and metadata
        """
        pass

    async def _get_messages(
        self,
        chat_id: int,
        limit: Optional[int] = None,
        days: Optional[int] = None,
        exclude_deleted: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get messages for processing.

        Args:
            chat_id: Telegram chat ID
            limit: Maximum messages to retrieve
            days: Number of days to look back
            exclude_deleted: Exclude deleted messages

        Returns:
            List of message dictionaries
        """
        limit = limit or self.config.max_messages

        messages = await self.db.get_messages(
            chat_id=chat_id,
            days=days,
            limit=limit,
            exclude_deleted=exclude_deleted
        )

        logger.debug(f"{self.skill_name}: Retrieved {len(messages)} messages for chat {chat_id}")
        return messages

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Format messages for LLM prompt.

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

            # Format: [timestamp] username: content
            lines.append(f"[{timestamp}] {username}: {content}")

        return "\n".join(lines)

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Call LLM with the given prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system message
            max_tokens: Override max tokens
            temperature: Override temperature

        Returns:
            LLM response dict with text and usage
        """
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        try:
            result = await self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )

            logger.debug(
                f"{self.skill_name}: LLM call completed - "
                f"{result['usage']['total_tokens']} tokens, "
                f"${result.get('cost_usd', 0):.4f} cost"
            )

            return result

        except Exception as e:
            logger.error(f"{self.skill_name}: LLM call failed: {e}")
            raise SkillError(
                f"LLM call failed: {e}",
                skill_name=self.skill_name,
                details={"error_type": type(e).__name__}
            )

    async def _log_usage(
        self,
        chat_id: int,
        usage: Dict[str, int],
        cost_usd: float
    ) -> None:
        """
        Log LLM token usage to database.

        Args:
            chat_id: Telegram chat ID
            usage: Token usage dict
            cost_usd: Estimated cost
        """
        try:
            await self.db.log_llm_usage(
                user_id=0,  # System/skill user
                chat_id=chat_id,
                skill=self.skill_name.lower().replace("skill", ""),
                tokens_prompt=usage.get("prompt_tokens", 0),
                tokens_completion=usage.get("completion_tokens", 0),
                cost_usd=cost_usd
            )
        except Exception as e:
            logger.error(f"{self.skill_name}: Failed to log usage: {e}")

    def _create_error_result(
        self,
        error_message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """
        Create an error result.

        Args:
            error_message: Error message
            details: Optional error details

        Returns:
            SkillResult with success=False
        """
        return SkillResult(
            success=False,
            text=error_message,
            error=error_message,
            metadata=details or {}
        )

    def _create_success_result(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        usage: Optional[Dict[str, int]] = None,
        cost_usd: float = 0.0
    ) -> SkillResult:
        """
        Create a success result.

        Args:
            text: Generated text
            metadata: Optional metadata
            usage: Token usage dict
            cost_usd: Estimated cost

        Returns:
            SkillResult with success=True
        """
        return SkillResult(
            success=True,
            text=text,
            metadata=metadata or {},
            usage=usage or {},
            cost_usd=cost_usd
        )


def validate_chat_id(chat_id: int) -> None:
    """
    Validate chat ID.

    Args:
        chat_id: Telegram chat ID

    Raises:
        ValueError: If chat_id is invalid
    """
    if not isinstance(chat_id, int) or chat_id == 0:
        raise ValueError(f"Invalid chat_id: {chat_id}")


def validate_language(language: str) -> str:
    """
    Validate and normalize language code.

    Args:
        language: Language code

    Returns:
        Normalized language code

    Raises:
        ValueError: If language is not supported
    """
    from app.core.i18n import is_supported_language

    if not is_supported_language(language):
        raise ValueError(f"Unsupported language: {language}")

    return language
