"""
Skills module - AI-powered skills for chat analysis (v2.1)

Implements AGENTS.md specification with tool calling support.

Available skills:
- Summary: Daily/weekly chat summaries
- Coach: Communication analysis and recommendations
- QA: Question answering based on chat context
- Analytics: Statistics, data queries, and counts
- ThreadSummary: Thread/conversation summarization
"""

from app.skills.base import (
    BaseSkill,
    SkillResult,
    SkillError,
    SkillConfig,
    validate_chat_id,
    validate_language
)

# Import all skill implementations
from app.skills.summary import SummarySkill, generate_summary
from app.skills.coach import CoachSkill, generate_coach_insights
from app.skills.thread_summary import ThreadSummarySkill, generate_thread_summary
from app.skills.qa import QASkill, generate_qa_answer
from app.skills.analytics import AnalyticsSkill, generate_analytics

# Skills registry - maps skill names to classes
_SKILL_REGISTRY = {
    "summary": SummarySkill,
    "coach": CoachSkill,
    "qa": QASkill,
    "analytics": AnalyticsSkill,
    "thread_summary": ThreadSummarySkill,
}


def get_skill_class(skill_name: str):
    """
    Get skill class by name.

    Args:
        skill_name: Name of the skill

    Returns:
        Skill class or None if not found
    """
    return _SKILL_REGISTRY.get(skill_name)


def list_skills() -> list:
    """
    List all available skills.

    Returns:
        List of skill names
    """
    return list(_SKILL_REGISTRY.keys())


def get_skill_info(skill_name: str) -> dict:
    """
    Get information about a skill.

    Args:
        skill_name: Name of the skill

    Returns:
        Dict with skill info or None if not found
    """
    skill_class = get_skill_class(skill_name)
    if not skill_class:
        return None

    return {
        "name": skill_class.name,
        "allowed_tools": skill_class.allowed_tools,
        "output_format": skill_class.output_format,
        "temperature": skill_class.temperature
    }


def list_all_skills_info() -> list:
    """
    List information about all available skills.

    Returns:
        List of skill info dicts
    """
    return [
        {
            "name": name,
            "class": skill_class.__name__,
            "allowed_tools": skill_class.allowed_tools,
            "output_format": skill_class.output_format,
            "temperature": skill_class.temperature
        }
        for name, skill_class in _SKILL_REGISTRY.items()
    ]


# Legacy exports for backward compatibility
__all__ = [
    # Base classes
    "BaseSkill",
    "SkillResult",
    "SkillError",
    "SkillConfig",
    "validate_chat_id",
    "validate_language",

    # Skill classes
    "SummarySkill",
    "CoachSkill",
    "QASkill",
    "AnalyticsSkill",
    "ThreadSummarySkill",

    # Legacy functions
    "generate_summary",
    "generate_coach_insights",
    "generate_thread_summary",
    "generate_qa_answer",
    "generate_analytics",

    # Registry functions
    "get_skill_class",
    "list_skills",
    "get_skill_info",
    "list_all_skills_info",
]
