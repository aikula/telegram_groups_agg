"""
OpenRouter API Client - Integration with OpenRouter for LLM services
"""

import logging
from typing import List, Dict, Optional, Any
from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from app.llm.prompts import (
    format_qa_context,
    format_summary_prompt,
    format_coaching_prompt,
    get_system_prompt
)

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """
    Client for interacting with OpenRouter API.

    Provides methods for:
    - Answering questions with chat context
    - Generating daily summaries
    - Generating coaching recommendations
    """

    # Default model to use
    DEFAULT_MODEL = "deepseek/deepseek-r1:free"
    # Alternative models
    FALLBACK_MODELS = [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-mini",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]

    def __init__(self, api_key: str, model: Optional[str] = None):
        """
        Initialize the OpenRouter client.

        Args:
            api_key: OpenRouter API key
            model: Model identifier (uses DEFAULT_MODEL if not specified)
        """
        if not api_key:
            raise ValueError("OpenRouter API key is required")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = model or self.DEFAULT_MODEL
        self.current_model_index = 0
        logger.info(f"OpenRouter client initialized with model: {self.model}")

    def _get_models_to_try(self) -> List[str]:
        """
        Get list of models to try in order.

        Returns:
            List of model identifiers
        """
        models = [self.model]
        models.extend(self.FALLBACK_MODELS)
        return models

    def _call_llm(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """
        Internal method to call LLM with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (overrides default)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            LLM response text

        Raises:
            APIError: If all models fail
        """
        models_to_try = [model] if model else self._get_models_to_try()
        last_error = None

        for attempt_model in models_to_try:
            try:
                logger.debug(f"Trying model: {attempt_model}")

                response = self.client.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                result = response.choices[0].message.content
                logger.info(f"Successfully got response from {attempt_model}")
                return result

            except RateLimitError as e:
                logger.warning(f"Rate limit error for {attempt_model}: {e}")
                last_error = e
                continue
            except APIConnectionError as e:
                logger.warning(f"Connection error for {attempt_model}: {e}")
                last_error = e
                continue
            except APIError as e:
                logger.warning(f"API error for {attempt_model}: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"Unexpected error for {attempt_model}: {e}")
                last_error = e
                continue

        # All models failed
        logger.error(f"All models failed. Last error: {last_error}")
        raise APIError(f"Failed to get response from any model. Last error: {last_error}")

    def answer_question(
        self,
        question: str,
        context_messages: List[Dict],
        language: str = "ru"
    ) -> str:
        """
        Answer a question using chat context.

        Args:
            question: User's question
            context_messages: List of message dictionaries for context
            language: Language code ('ru' or 'en')

        Returns:
            Answer text from LLM
        """
        if not question:
            return "Пожалуйста, задайте вопрос."

        if not context_messages:
            return "Недостаточно контекста для ответа. В чате пока нет сообщений."

        # Format prompt
        user_prompt = format_qa_context(context_messages, question, language)
        system_prompt = get_system_prompt(f"qa_{language}" if language == "en" else "qa_ru")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_llm(messages, max_tokens=1000, temperature=0.7)
            return response.strip()
        except APIError as e:
            logger.error(f"Error answering question: {e}")
            return f"Извините, произошла ошибка при генерации ответа: {str(e)}"

    def generate_summary(
        self,
        messages: List[Dict],
        language: str = "ru"
    ) -> str:
        """
        Generate a daily summary from chat messages.

        Args:
            messages: List of message dictionaries
            language: Language code ('ru' or 'en')

        Returns:
            Summary text from LLM
        """
        if not messages:
            return "Нет сообщений для анализа."

        # Limit messages to avoid token limits
        limited_messages = messages[:100]

        # Format prompt
        user_prompt = format_summary_prompt(limited_messages, language)
        system_prompt = get_system_prompt(f"analyst_{language}" if language == "en" else "analyst_ru")

        messages_list = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_llm(messages_list, max_tokens=2000, temperature=0.5)
            return response.strip()
        except APIError as e:
            logger.error(f"Error generating summary: {e}")
            return f"Ошибка при генерации сводки: {str(e)}"

    def generate_recommendations(
        self,
        messages: List[Dict],
        language: str = "ru"
    ) -> str:
        """
        Generate coaching recommendations from chat messages.

        Args:
            messages: List of message dictionaries
            language: Language code ('ru' or 'en')

        Returns:
            Recommendations text from LLM
        """
        if not messages:
            return "Нет сообщений для анализа."

        # Limit messages to avoid token limits
        limited_messages = messages[:100]

        # Format prompt
        user_prompt = format_coaching_prompt(limited_messages, language)
        system_prompt = get_system_prompt(f"coach_{language}" if language == "en" else "coach_ru")

        messages_list = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_llm(messages_list, max_tokens=2000, temperature=0.6)
            return response.strip()
        except APIError as e:
            logger.error(f"Error generating recommendations: {e}")
            return f"Ошибка при генерации рекомендаций: {str(e)}"

    def generate_daily_report(
        self,
        messages: List[Dict],
        language: str = "ru"
    ) -> Dict[str, str]:
        """
        Generate both summary and recommendations in one call structure.

        Args:
            messages: List of message dictionaries
            language: Language code ('ru' or 'en')

        Returns:
            Dictionary with 'summary' and 'recommendations' keys
        """
        if not messages:
            return {
                "summary": "Нет сообщений для анализа.",
                "recommendations": "Недостаточно данных для рекомендаций."
            }

        # Generate summary
        summary = self.generate_summary(messages, language)

        # Generate recommendations
        recommendations = self.generate_recommendations(messages, language)

        return {
            "summary": summary,
            "recommendations": recommendations
        }

    def test_connection(self) -> bool:
        """
        Test the connection to OpenRouter API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OK' if you can read this."}
            ]

            response = self._call_llm(messages, max_tokens=10)
            result = "OK" in response.upper()

            if result:
                logger.info("OpenRouter connection test successful")
            else:
                logger.warning(f"OpenRouter connection test returned unexpected: {response}")

            return result

        except Exception as e:
            logger.error(f"OpenRouter connection test failed: {e}")
            return False

    def set_model(self, model: str) -> None:
        """
        Change the default model.

        Args:
            model: New model identifier
        """
        self.model = model
        logger.info(f"Model changed to: {model}")

    def get_available_models(self) -> List[str]:
        """
        Get list of configured models.

        Returns:
            List of model identifiers
        """
        return [self.model] + self.FALLBACK_MODELS


def create_openrouter_client(api_key: str, model: Optional[str] = None) -> OpenRouterClient:
    """
    Factory function to create an OpenRouter client.

    Args:
        api_key: OpenRouter API key
        model: Optional model identifier

    Returns:
        OpenRouterClient instance
    """
    return OpenRouterClient(api_key=api_key, model=model)
