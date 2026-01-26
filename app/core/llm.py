"""
Core LLM module - OpenAI-compatible client

Features:
- OpenAI API compatible (works with OpenRouter, Anthropic, etc.)
- Token usage tracking
- Cost estimation
- Retry logic with exponential backoff
- Timeout handling
- Support for streaming responses (future)
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx

from app.config import settings


logger = logging.getLogger(__name__)


class LLMClient:
    """
    OpenAI-compatible LLM client.

    Supports OpenAI, OpenRouter, Anthropic (via SDK), and other
    OpenAI-compatible APIs.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM client.

        Args:
            config: Optional configuration dict. If None, uses settings.
        """
        if config is None:
            config = settings.get_model_config()

        self.base_url = config["base_url"]
        self.api_key = config["api_key"]
        self.model_name = config["model_name"]
        self.max_tokens = config["max_tokens"]
        self.temperature = config["temperature"]
        self.timeout = config["timeout"]

        # HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout),
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Generate text completion.

        Args:
            prompt: User prompt
            max_tokens: Override default max_tokens
            temperature: Override default temperature
            system_prompt: Optional system message
            retry_count: Current retry attempt

        Returns:
            Dict with:
                - text: Generated text
                - usage: Token usage dict
                - model: Model name used
                - cost_usd: Estimated cost

        Raises:
            httpx.HTTPStatusError: API error
            asyncio.TimeoutError: Request timeout
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Chat completion with message history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Override default max_tokens
            temperature: Override default temperature
            model: Override default model

        Returns:
            Dict with generated text and usage info
        """
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature
        model = model or self.model_name

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})

            result = {
                "text": choice["message"]["content"],
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "model": data.get("model", model),
                "finish_reason": choice.get("finish_reason"),
            }

            # Estimate cost (rough estimate, varies by provider)
            result["cost_usd"] = self._estimate_cost(
                model,
                result["usage"]["prompt_tokens"],
                result["usage"]["completion_tokens"]
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.TimeoutException:
            logger.error(f"LLM API timeout after {self.timeout}s")
            raise asyncio.TimeoutError(f"LLM request timed out")
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise

    async def chat_qa(
        self,
        question: str,
        context: List[Dict[str, str]],
        language: str = "ru"
    ) -> Dict[str, Any]:
        """
        Answer question based on chat context.

        Args:
            question: User question
            context: List of message dicts with 'user', 'text', 'timestamp'
            language: Response language

        Returns:
            Dict with answer text and usage
        """
        from app.core.i18n import get_text

        # Format context
        context_text = "\n".join([
            f"[{msg.get('timestamp', '')}] {msg.get('username', msg.get('first_name', 'User'))}: {msg.get('content', msg.get('text', ''))}"
            for msg in context
        ])

        # Get QA prompt
        system_prompt = get_text(
            "qa.prompt",
            lang=language,
            context=context_text,
            count=len(context),
            question=question
        )

        # Generate answer
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": system_prompt}
        ]

        return await self.chat(messages=messages)

    async def format_results(
        self,
        question: str,
        results: List[tuple],
        language: str = "ru"
    ) -> Dict[str, Any]:
        """
        Format SQL query results into natural language.

        Args:
            question: Original user question
            results: Query results (list of tuples)
            language: Response language

        Returns:
            Dict with formatted text and usage
        """
        # Format results as text
        if not results:
            from app.core.i18n import get_text
            return {
                "text": get_text("sql_agent.no_results", lang=language),
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "cost_usd": 0.0
            }

        results_text = "\n".join([str(row) for row in results])

        prompt = f"""
        Original question: {question}

        Query results:
        {results_text}

        Provide a clear, concise answer in {language} based on these results.
        Format the answer naturally for a human reader.
        """

        return await self.generate(prompt)

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Estimate cost in USD for API call.

        Note: This is a rough estimate. Actual costs vary by provider
        and specific model pricing.

        Args:
            model: Model name
            prompt_tokens: Input tokens
            completion_tokens: Output tokens

        Returns:
            Estimated cost in USD
        """
        # Rough pricing (update based on actual provider)
        # These are conservative estimates
        pricing = {
            # GPT-4 class
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            # GPT-3.5 class
            "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
            # Claude class
            "claude-3": {"prompt": 0.003, "completion": 0.015},
            "claude-3.5": {"prompt": 0.003, "completion": 0.015},
            # Default
            "default": {"prompt": 0.001, "completion": 0.002},
        }

        # Try to match model
        model_lower = model.lower()
        price = pricing.get("default", pricing["default"])

        for key, value in pricing.items():
            if key in model_lower:
                price = value
                break

        prompt_cost = (prompt_tokens / 1000) * price["prompt"]
        completion_cost = (completion_tokens / 1000) * price["completion"]

        return prompt_cost + completion_cost

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class LLMTimeoutError(LLMError):
    """LLM request timeout."""


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded."""


class LLMInvalidRequestError(LLMError):
    """Invalid request to LLM API."""


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get LLM client singleton instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def close_llm_client() -> None:
    """Close global LLM client if exists."""
    global _llm_client
    if _llm_client is not None:
        await _llm_client.close()
        _llm_client = None
