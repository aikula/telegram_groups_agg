"""
Skill Agent - Execute skills with tool calling support (v2.1)

Implements AGENTS.md specification for skill orchestration.
The SkillAgent manages the flow: query → skill selection → tool execution → response.
"""

import logging
import json
from typing import Optional, Dict, Any, List

from app.core.llm import LLMClient, get_llm_client
from app.core.db import Database
from app.core.tools import execute_tool_call, get_tool_definitions

logger = logging.getLogger(__name__)


class SkillAgent:
    """
    Execute skills with tool calling orchestration.

    The SkillAgent coordinates:
    1. Loading the appropriate skill class
    2. Preparing execution context
    3. Running LLM with tool calling support
    4. Handling multi-turn tool conversations
    5. Formatting and returning the response

    Example:
        agent = SkillAgent(db)
        response = await agent.execute(
            skill_name="qa",
            query="Сколько сообщений у Вити?",
            chat_id=123,
            user_id=456
        )
    """

    def __init__(self, db: Database, llm_client: Optional[LLMClient] = None):
        """
        Initialize skill agent.

        Args:
            db: Database instance
            llm_client: Optional LLM client (uses default if None)
        """
        self.db = db
        self.llm = llm_client or get_llm_client()

    async def execute(
        self,
        skill_name: str,
        query: str,
        chat_id: int,
        user_id: Optional[int] = None,
        max_iterations: int = 5
    ) -> str:
        """
        Execute a skill with tool calling.

        Args:
            skill_name: Name of skill to execute
            query: User query
            chat_id: Telegram chat ID
            user_id: User ID (for logging)
            max_iterations: Maximum tool call iterations

        Returns:
            Formatted skill response text
        """
        # Load skill class
        from app.skills import get_skill_class
        skill_class = get_skill_class(skill_name)
        if not skill_class:
            logger.error(f"Skill not found: {skill_name}")
            return f"❌ Ошибка: навык '{skill_name}' не найден"

        # Instantiate skill
        skill = skill_class(db=self.db, llm=self.llm)

        # Prepare context
        context = await self._prepare_context(query, chat_id, user_id)

        # Build messages
        system_prompt = skill.get_system_prompt(context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # Get tool definitions
        tools = skill.get_tool_definitions()

        # Execute with tool calling (if tools available) or direct LLM
        if tools and skill.allowed_tools:
            result = await self._execute_with_tools(
                messages=messages,
                tools=tools,
                chat_id=chat_id,
                skill_name=skill_name,
                max_iterations=max_iterations,
                temperature=skill.temperature
            )
        else:
            # Direct LLM call without tools
            result = await self.llm.chat(
                messages=messages,
                temperature=skill.temperature
            )
            result = {
                "text": result.get("text", ""),
                "usage": result.get("usage", {}),
                "iterations": 1
            }

        # Format output
        formatted = await skill.format_output(result["text"])

        # Log usage
        await self._log_usage(
            skill_name=skill_name,
            chat_id=chat_id,
            user_id=user_id,
            usage=result.get("usage", {}),
            iterations=result.get("iterations", 1)
        )

        return formatted

    async def _execute_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        chat_id: int,
        skill_name: str,
        max_iterations: int,
        temperature: float
    ) -> Dict[str, Any]:
        """
        Execute LLM with tool calling support.

        Implements multi-turn tool conversation:
        1. Send messages + tools to LLM
        2. If LLM calls tool, execute it
        3. Add tool result to messages
        4. Repeat until LLM returns final response

        Args:
            messages: Conversation history
            tools: Tool definitions
            chat_id: Chat for tool execution
            skill_name: Skill name for logging
            max_iterations: Maximum tool call iterations
            temperature: LLM temperature

        Returns:
            Dict with final text, usage, and iteration count
        """
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for iteration in range(max_iterations):
            # Prepare API payload
            payload = {
                "model": self.llm.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": self.llm.max_tokens,
            }

            # Add tools (except on last iteration where we force final response)
            if iteration < max_iterations - 1:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            else:
                # Last iteration: no tools, force final response
                payload["tool_choice"] = "none"

            # Call LLM API
            try:
                api_response = await self.llm._client.post(
                    "/chat/completions",
                    json=payload
                )
                api_response.raise_for_status()
                data = api_response.json()
            except Exception as e:
                logger.error(f"LLM API error in {skill_name}: {e}")
                return {
                    "text": "⚠️ Произошла ошибка при обращении к LLM",
                    "usage": total_usage,
                    "iterations": iteration + 1
                }

            # Extract response
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage", {})

            # Accumulate token usage
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)

            # Check for tool calls
            tool_calls = message.get("tool_calls")

            if not tool_calls:
                # No tool calls - this is the final response
                return {
                    "text": message.get("content", ""),
                    "usage": total_usage,
                    "iterations": iteration + 1
                }

            # Execute tool calls
            logger.info(f"Skill {skill_name}: executing {len(tool_calls)} tool(s)")

            # Add assistant message with tool calls
            messages.append(message)

            # Execute each tool and add results
            for tool_call in tool_calls:
                try:
                    result = await execute_tool_call(
                        tool_call=tool_call,
                        chat_id=chat_id,
                        db=self.db
                    )

                    # Add tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False)
                    })

                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    # Add error as tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({"error": str(e)})
                    })

        # Max iterations reached
        logger.warning(f"Skill {skill_name}: max iterations ({max_iterations}) reached")
        return {
            "text": "⚠️ Превышено максимальное количество итераций",
            "usage": total_usage,
            "iterations": max_iterations
        }

    async def _prepare_context(
        self,
        query: str,
        chat_id: int,
        user_id: Optional[int]
    ) -> Dict[str, Any]:
        """
        Prepare context for skill execution.

        Args:
            query: User query
            chat_id: Chat ID
            user_id: User ID

        Returns:
            Context dict with chat and user information
        """
        from datetime import datetime

        # Get chat info
        chat = await self.db.get_chat_by_id(chat_id)

        # Get user info
        user_info = None
        if user_id:
            user = await self.db.get_or_create_user(user_id)
            user_info = {
                "username": user.get("username"),
                "full_name": user.get("first_name") or user.get("username", "User")
            }

        return {
            "chat_id": chat_id,
            "chat_title": chat.get("title", "") if chat else "",
            "username": user_info.get("username") if user_info else "",
            "full_name": user_info.get("full_name") if user_info else "",
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

    async def _log_usage(
        self,
        skill_name: str,
        chat_id: int,
        user_id: Optional[int],
        usage: Dict[str, int],
        iterations: int = 1
    ) -> None:
        """
        Log LLM usage to database.

        Args:
            skill_name: Name of skill that was executed
            chat_id: Chat ID
            user_id: User ID (None for system)
            usage: Token usage dict
            iterations: Number of iterations (for tool calling)
        """
        try:
            # Calculate cost (rough estimate)
            cost_usd = self._estimate_cost(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0)
            )

            await self.db.log_llm_usage(
                user_id=user_id or 0,
                chat_id=chat_id,
                skill=skill_name,
                tokens_prompt=usage.get("prompt_tokens", 0),
                tokens_completion=usage.get("completion_tokens", 0),
                cost_usd=cost_usd
            )

            logger.debug(
                f"Logged usage: {skill_name} - "
                f"{usage.get('total_tokens', 0)} tokens, "
                f"{iterations} iteration(s), "
                f"${cost_usd:.4f}"
            )

        except Exception as e:
            logger.error(f"Failed to log usage: {e}")

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Estimate LLM API call cost in USD.

        Args:
            prompt_tokens: Input tokens
            completion_tokens: Output tokens

        Returns:
            Estimated cost in USD
        """
        # Rough pricing (adjust based on actual provider)
        pricing = self.llm._estimate_cost(
            self.llm.model_name,
            prompt_tokens,
            completion_tokens
        )
        return pricing


# ============================================================================
# Legacy Execute Method (for backward compatibility)
# ============================================================================

async def execute_skill(
    skill_name: str,
    query: str,
    chat_id: int,
    user_id: Optional[int] = None,
    db: Optional[Database] = None,
    llm_client: Optional[LLMClient] = None
) -> str:
    """
    Execute a skill (convenience function).

    Args:
        skill_name: Name of skill to execute
        query: User query
        chat_id: Telegram chat ID
        user_id: User ID
        db: Database instance (uses default if None)
        llm_client: LLM client (uses default if None)

    Returns:
        Formatted skill response
    """
    if db is None:
        from app.core.db import get_database
        db = get_database()

    agent = SkillAgent(db, llm_client)
    return await agent.execute(skill_name, query, chat_id, user_id)
