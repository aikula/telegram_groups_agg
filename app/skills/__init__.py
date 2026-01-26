"""
Skills module - AI-powered skills for chat analysis (v2.0)

Skills:
- Summary: Daily/weekly chat summaries
- Coach: Communication analysis and recommendations
- ThreadSummary: Thread/conversation summarization
- QA: Question answering based on chat context
"""

from app.skills.summary import SummarySkill, generate_summary
from app.skills.coach import CoachSkill, generate_coach_insights
from app.skills.thread_summary import ThreadSummarySkill, generate_thread_summary
from app.skills.base import BaseSkill, SkillResult, SkillError

__all__ = [
    "BaseSkill",
    "SkillResult",
    "SkillError",
    "SummarySkill",
    "CoachSkill",
    "ThreadSummarySkill",
    "generate_summary",
    "generate_coach_insights",
    "generate_thread_summary",
]
