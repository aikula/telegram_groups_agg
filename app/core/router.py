"""
Router Agent - Classify user queries and select appropriate skill (v2.2)

Implements AGENTS.md specification for intelligent skill routing.
The Router uses LLM to understand user intent and choose the best skill.

Available skills:
- summary: Create chat summaries and reports
- coach: Communication analysis and recommendations
- qa: Answer questions about chat content
- analytics: Statistics, data queries, and metrics
- about: Information about bot capabilities and origin
"""

import logging
from typing import List, Optional, Dict, Any

from app.core.llm import LLMClient, get_llm_client
from app.core.db import Database

logger = logging.getLogger(__name__)


# Available skills (must match classes in skills module)
AVAILABLE_SKILLS = ["summary", "coach", "qa", "analytics", "about"]

# Triggers for "about" skill (bypass LLM for direct routing)
ABOUT_TRIGGERS = [
    "что ты умеешь", "что умеешь", "твои возможности",
    "кто тебя создал", "кто создал", "кто разработал",
    "расскажи о себе", "представься", "представьcя",
    "что ты за бот", "что за бот", "ты кто",
    "что ты можешь", "ты умеешь"
]

# Input validation constants (v2.2)
MAX_QUERY_LENGTH = 500  # Maximum query length in characters

# Telegram chat_id ranges:
# - Personal chats: positive ID (e.g., 78792751)
# - Groups/supergroups: negative ID (e.g., -1001234567890)
# Telegram uses 64-bit signed integers for some chat IDs
MIN_POSITIVE_CHAT_ID = 1
MIN_NEGATIVE_CHAT_ID = -2**63  # Most negative signed 64-bit int
MAX_CHAT_ID = 2**63 - 1


class RouterAgent:
    """
    Route user queries to appropriate skills using LLM classification.

    The Router is a lightweight classifier that:
    1. Analyzes user intent from the query
    2. Checks which skills are enabled for the chat
    3. Selects the most appropriate skill
    4. Falls back to 'qa' if selection fails

    Example:
        router = RouterAgent(db)
        skill_name = await router.route("Сколько сообщений вчера?", chat_id=123)
        # Returns: "analytics"
    """

    def __init__(self, db: Database, llm_client: Optional[LLMClient] = None):
        """
        Initialize router.

        Args:
            db: Database instance for checking enabled skills
            llm_client: Optional LLM client (uses default if None)
        """
        self.db = db
        self.llm = llm_client or get_llm_client()

    async def route(
        self,
        query: str,
        chat_id: int
    ) -> str:
        """
        Route query to appropriate skill.

        Args:
            query: User query text
            chat_id: Telegram chat ID

        Returns:
            Selected skill name (fallback to 'qa' if disabled or error)

        Raises:
            ValueError: If input validation fails
        """
        # Input validation (v2.2)
        if not isinstance(query, str):
            raise ValueError(f"query must be string, got {type(query).__name__}")

        query = query.strip()

        if not query:
            logger.warning("Empty query received, using 'qa'")
            return "qa"

        if len(query) > MAX_QUERY_LENGTH:
            logger.warning(
                f"Query too long ({len(query)} chars), truncating to {MAX_QUERY_LENGTH}"
            )
            query = query[:MAX_QUERY_LENGTH].strip()

        # Validate chat_id (Telegram allows negative IDs for groups/supergroups)
        if not isinstance(chat_id, int):
            raise ValueError(f"chat_id must be int, got {type(chat_id).__name__}")

        # Check if chat_id is within valid Telegram range
        # Positive: personal chats, Negative: groups/supergroups
        is_valid_positive = MIN_POSITIVE_CHAT_ID <= chat_id <= MAX_CHAT_ID
        is_valid_negative = MIN_NEGATIVE_CHAT_ID <= chat_id < 0

        if not (is_valid_positive or is_valid_negative):
            raise ValueError(f"chat_id out of valid range: {chat_id}")

        # Check for "about" triggers first (bypass LLM for direct routing)
        query_lower = query.lower()
        for trigger in ABOUT_TRIGGERS:
            if trigger in query_lower:
                logger.info(f"Router: matched 'about' trigger -> about (chat_id={chat_id})")
                # Check if about skill is enabled
                enabled_skills = await self._get_enabled_skills(chat_id)
                if "about" in enabled_skills:
                    return "about"
                # If about not enabled, fall through to normal routing

        # Get enabled skills for chat
        enabled_skills = await self._get_enabled_skills(chat_id)

        # Filter available skills to enabled ones
        available = [s for s in AVAILABLE_SKILLS if s in enabled_skills]

        # If no skills enabled, default to qa
        if not available:
            logger.warning(f"No enabled skills for chat {chat_id}, using 'qa'")
            return "qa"

        # Build minimal routing prompt
        prompt = self._build_router_prompt(query, available)

        # Get LLM decision
        try:
            result = await self.llm.generate(
                prompt,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=20  # Only need skill name
            )

            # Extract skill name from response
            skill_name = self._extract_skill_name(result["text"], available)

            # Validate skill is in allowed list
            if skill_name not in available:
                logger.warning(
                    f"Router selected invalid skill '{skill_name}', "
                    f"falling back to 'qa'"
                )
                return "qa"

            logger.info(
                f"Router: '{query[:50]}...' -> {skill_name} "
                f"(chat_id={chat_id})"
            )
            return skill_name

        except Exception as e:
            logger.error(f"Router failed: {e}, falling back to 'qa'")
            return "qa"

    async def _get_enabled_skills(self, chat_id: int) -> List[str]:
        """
        Get list of enabled skills for chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List of enabled skill names
        """
        try:
            # Try new JSON format first
            settings = await self.db.get_chat_settings(chat_id)
            if settings:
                enabled_json = settings.get("enabled_skills")
                if enabled_json:
                    import json
                    return json.loads(enabled_json)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback to old boolean format for backward compatibility
        settings = await self.db.get_chat_settings(chat_id)
        if settings:
            enabled = []
            if settings.get("summary_enabled", 1):
                enabled.append("summary")
            if settings.get("coach_enabled", 1):
                enabled.append("coach")
            # qa and analytics are always available in old format
            enabled.extend(["qa", "analytics"])
            return enabled

        # Default: all skills enabled
        return AVAILABLE_SKILLS.copy()

    def _build_router_prompt(self, query: str, available_skills: List[str]) -> str:
        """
        Build minimal routing prompt for LLM.

        Args:
            query: User query
            available_skills: List of enabled skills

        Returns:
            Routing prompt string
        """
        skills_desc = "\n".join(
            f"- {skill}: {_get_skill_description(skill)}"
            for skill in available_skills
        )

        return f"""You are a routing agent. Select the most appropriate skill for the user query.

User query: "{query}"

Available skills:
{skills_desc}

Instructions:
- Return ONLY the skill name
- Choose the best match based on user intent
- If unsure, default to 'qa'

Skill name:"""

    def _extract_skill_name(self, response: str, available: List[str]) -> str:
        """
        Extract skill name from LLM response.

        Args:
            response: LLM response text
            available: List of available skills

        Returns:
            Valid skill name
        """
        # Clean and normalize response
        cleaned = response.strip().lower().rstrip('.')

        # Direct match
        if cleaned in available:
            return cleaned

        # Find partial match (e.g., "summary skill" -> "summary")
        for skill in available:
            if skill in cleaned or cleaned in skill:
                return skill

        # Default to first available (usually qa)
        return available[0] if available else "qa"

    async def get_available_skills(self, chat_id: int) -> List[str]:
        """
        Get list of enabled skills for chat (public method).

        Args:
            chat_id: Telegram chat ID

        Returns:
            List of enabled skill names
        """
        return await self._get_enabled_skills(chat_id)


# ============================================================================
# Skill Descriptions
# ============================================================================

def _get_skill_description(skill: str) -> str:
    """
    Get human-readable skill description for routing prompt.

    Args:
        skill: Skill name

    Returns:
        Skill description
    """
    descriptions = {
        "summary": "Create chat summaries, daily/weekly reports, recap discussions",
        "coach": "Analyze communication patterns, provide team recommendations",
        "qa": "Answer questions about chat content, find specific information",
        "analytics": "Statistics, message counts, user activity, data queries",
        "about": "Answer questions about bot capabilities and origin (what can you do, who created you)"
    }
    return descriptions.get(skill, "General assistance")


# ============================================================================
# Helper Functions
# ============================================================================

def is_valid_skill(skill_name: str) -> bool:
    """Check if skill name is valid."""
    return skill_name in AVAILABLE_SKILLS


def list_all_skills() -> List[str]:
    """List all available skills."""
    return AVAILABLE_SKILLS.copy()
