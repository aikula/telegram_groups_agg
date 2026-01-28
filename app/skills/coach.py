"""
Coach skill - Communication analysis and feedback (v2.1)

Implements AGENTS.md specification with tool calling support.
"""

import logging
from typing import Optional, Dict, Any
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
class CoachSkillConfig(SkillConfig):
    """Configuration for coach skill."""

    max_messages: int = 150
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    language: str = "ru"
    analysis_type: str = "general"  # general, conflict, productivity


class CoachSkill(BaseSkill):
    """
    Coach skill for communication analysis.

    Provides constructive feedback on:
    - Communication tone and style
    - Team dynamics
    - Potential conflicts
    - Productivity improvements

    AGENTS.md v2.1 specification:
    - Uses tools: get_chat_history
    - Output format: text
    - Temperature: 0.7
    """

    name = "coach"
    allowed_tools = ["get_chat_history"]
    output_format = "text"
    temperature = 0.7

    def __init__(
        self,
        db,
        llm=None,
        config: Optional[CoachSkillConfig] = None
    ):
        super().__init__(db, llm, config or CoachSkillConfig())

    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Get coach system prompt."""
        language = self.config.language
        if language == "ru":
            base_prompt = (
                "Ты - профессиональный консультант по коммуникации. "
                "Твоя задача - дать конструктивную, объективную обратную связь. "
                "Будь специфичным, дай конкретные примеры и рекомендации."
            )
        else:
            base_prompt = (
                "You are a professional communication consultant. "
                "Your task is to provide constructive, objective feedback. "
                "Be specific, give concrete examples and recommendations."
            )

        return f"""{base_prompt}

Task: Analyze communication patterns and provide recommendations.

Tools available:
- get_chat_history(days) - Retrieve messages to analyze

Output format:
✅ Positive observations
⚠️ Areas to improve
💡 Recommendations (3-5 specific items)

Analysis guidelines:
- Be constructive and specific
- Cite actual message examples when relevant
- Focus on actionable recommendations
- Consider team dynamics and individual contributions
- Highlight both strengths and areas for growth

Current context:
- Chat: {context.get('chat_title', 'N/A')}
- Chat ID: {context['chat_id']}
- Date: {context.get('date', 'N/A')}

When analyzing:
1. Use get_chat_history() to retrieve recent messages
2. Look for patterns in communication style
3. Identify tone, constructiveness, clarity
4. Note positive behaviors to reinforce
5. Suggest specific improvements
6. Provide 3-5 actionable recommendations"""

    async def format_output(self, text: str) -> str:
        """Format coach output."""
        # Clean up formatting
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
        days: int = 7,
        language: Optional[str] = None,
        analysis_type: Optional[str] = None,
        **kwargs
    ) -> SkillResult:
        """
        Generate communication analysis (legacy method).

        Args:
            chat_id: Telegram chat ID
            days: Number of days to analyze (default: 7)
            language: Language for analysis (default: from config)
            analysis_type: Type of analysis (general, conflict, productivity)
            **kwargs: Additional parameters

        Returns:
            SkillResult with coaching insights
        """
        try:
            validate_chat_id(chat_id)

            language = language or self.config.language
            language = validate_language(language)

            analysis_type = analysis_type or self.config.analysis_type

            # Get messages
            messages = await self._get_messages(
                chat_id=chat_id,
                days=days
            )

            if not messages:
                return self._create_success_result(
                    text=get_text("summary.no_messages", lang=language),
                    metadata={"chat_id": chat_id, "days": days, "message_count": 0}
                )

            # Format messages for prompt
            formatted_messages = self._format_messages(messages)

            # Build analysis prompt based on type
            prompt = self._build_analysis_prompt(
                formatted_messages,
                analysis_type,
                language
            )

            # System prompt for coach
            system_prompt = self._get_legacy_system_prompt(language)

            # Call LLM
            result = await self._call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
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
                    "analysis_type": analysis_type,
                    "model": result.get("model", "")
                },
                usage=result["usage"],
                cost_usd=result.get("cost_usd", 0.0)
            )

        except SkillError:
            raise
        except Exception as e:
            logger.error(f"Coach skill failed for chat {chat_id}: {e}")
            return self._create_error_result(
                error_message=f"Coach analysis failed: {str(e)}",
                details={"chat_id": chat_id, "days": days}
            )

    def _build_analysis_prompt(
        self,
        messages: str,
        analysis_type: str,
        language: str
    ) -> str:
        """Build analysis prompt based on type."""
        if analysis_type == "conflict":
            return get_text(
                "coach.conflict_prompt",
                lang=language,
                messages=messages
            )
        elif analysis_type == "productivity":
            return get_text(
                "coach.productivity_prompt",
                lang=language,
                messages=messages
            )
        else:
            return get_text(
                "coach.prompt",
                lang=language,
                messages=messages
            )

    def _get_legacy_system_prompt(self, language: str) -> str:
        """Get system prompt for coach (legacy method)."""
        if language == "ru":
            return (
                "Ты - профессиональный консультант по коммуникации. "
                "Твоя задача - дать конструктивную, объективную обратную связь. "
                "Будь специфичным, дай конкретные примеры и рекомендации."
            )
        else:
            return (
                "You are a professional communication consultant. "
                "Your task is to provide constructive, objective feedback. "
                "Be specific, give concrete examples and recommendations."
            )

    async def analyze_team_dynamics(
        self,
        chat_id: int,
        days: int = 7,
        language: str = "ru"
    ) -> SkillResult:
        """Analyze team dynamics and collaboration."""
        return await self.execute(
            chat_id=chat_id,
            days=days,
            language=language,
            analysis_type="team"
        )

    async def detect_conflicts(
        self,
        chat_id: int,
        days: int = 3,
        language: str = "ru"
    ) -> SkillResult:
        """Detect potential conflicts in communication."""
        return await self.execute(
            chat_id=chat_id,
            days=days,
            language=language,
            analysis_type="conflict"
        )

    async def suggest_improvements(
        self,
        chat_id: int,
        days: int = 7,
        language: str = "ru"
    ) -> SkillResult:
        """Suggest improvements for team productivity."""
        return await self.execute(
            chat_id=chat_id,
            days=days,
            language=language,
            analysis_type="productivity"
        )


async def generate_coach_insights(
    db,
    chat_id: int,
    days: int = 7,
    language: str = "ru",
    analysis_type: str = "general"
) -> SkillResult:
    """
    Convenience function to generate coaching insights.

    Args:
        db: Database instance
        chat_id: Telegram chat ID
        days: Number of days to analyze
        language: Analysis language
        analysis_type: Type of analysis

    Returns:
        SkillResult with coaching insights
    """
    skill = CoachSkill(db)
    return await skill.execute(
        chat_id=chat_id,
        days=days,
        language=language,
        analysis_type=analysis_type
    )
