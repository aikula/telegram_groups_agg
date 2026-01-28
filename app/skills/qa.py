"""
QA Skill - Answer questions with chat context (v2.1)

Implements AGENTS.md specification for question answering.
Uses tools to retrieve chat history, run analytics, or provide general answers.
"""

from typing import Dict, Any, List
from app.skills.base import BaseSkill


class QASkill(BaseSkill):
    """
    Question-Answering skill.

    Answers user questions about chat content using available tools:
    - get_chat_history: Retrieve messages for context
    - sql_analytics: Get statistics and counts
    - general_answer: Use LLM general knowledge

    Example queries:
    - "Что обсуждали вчера?"
    - "Сколько сообщений написал @username?"
    - "Когда было последнее упоминание проекта X?"
    """

    name = "qa"
    allowed_tools = ["get_chat_history", "sql_analytics", "general_answer"]
    output_format = "text"
    temperature = 0.7

    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Get QA system prompt."""
        chat_id = context.get('chat_id', 'N/A')
        chat_title = context.get('chat_title', 'N/A')
        username = context.get('username') or context.get('full_name', 'Anonymous')
        date = context.get('date', 'N/A')

        return f"""You are a helpful chat assistant.

You have access to the following tools:
1. get_chat_history(limit, days) - Retrieve recent messages from the chat
2. sql_analytics(query) - Execute SELECT queries for statistics
3. general_answer() - Use your general knowledge without database access

Instructions for answering questions:
- For questions about chat content → use get_chat_history()
- For statistics and counts → use sql_analytics()
- For general knowledge questions → use general_answer()
- Always cite sources when using chat data (@username, date, time)
- Be concise and accurate
- Respond in Russian

Current context:
- Chat ID: {chat_id}
- Chat title: {chat_title}
- User asking: {username}
- Date: {date}

When answering:
1. Understand what the user is asking for
2. Choose the appropriate tool
3. Synthesize the information
4. Provide a clear, helpful answer"""


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
