"""
Tests for LLM integration modules
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

# Import modules to test
from app.llm.prompts import (
    format_qa_context,
    format_summary_prompt,
    format_coaching_prompt,
    get_welcome_message,
    format_statistics_summary,
    get_system_prompt
)
from app.llm.openrouter import (
    OpenRouterClient,
    create_openrouter_client
)


# ========== Prompts Tests ==========

def test_format_qa_context():
    """Test QA context formatting"""
    messages = [
        {"username": "user1", "first_name": "User 1", "message_text": "Hello", "timestamp": "2024-01-01 10:00"},
        {"username": "user2", "first_name": "User 2", "message_text": "Hi there", "timestamp": "2024-01-01 10:01"},
    ]

    result = format_qa_context(messages, "How are you?", language="ru")

    assert "user1" in result or "User 1" in result
    assert "Hello" in result
    assert "How are you?" in result
    assert "Контекст чата" in result


def test_format_qa_context_empty():
    """Test QA context formatting with empty messages"""
    result = format_qa_context([], "Test question")

    # Should still contain the question
    assert "Test question" in result


def test_format_summary_prompt():
    """Test summary prompt formatting"""
    messages = [
        {"username": "user1", "message_text": "Discussion about project", "timestamp": "2024-01-01 10:00"},
    ]

    result = format_summary_prompt(messages, language="ru")

    assert "user1" in result
    assert "Discussion about project" in result
    assert "анализируй" in result or "анализ" in result


def test_format_coaching_prompt():
    """Test coaching prompt formatting"""
    messages = [
        {"username": "user1", "message_text": "Great work everyone!", "timestamp": "2024-01-01 10:00"},
    ]

    result = format_coaching_prompt(messages, language="ru")

    assert "user1" in result
    assert "Great work everyone!" in result
    assert "рекомендации" in result


def test_get_welcome_message():
    """Test welcome message generation"""
    result = get_welcome_message("testbot")

    assert "@testbot" in result
    assert "Привет" in result
    assert "аналитик" in result


def test_format_statistics_summary():
    """Test statistics summary formatting"""
    stats = {
        "total_messages": 100,
        "active_users": 5,
        "days": 7,
        "avg_per_day": 14.3,
        "top_contributors": [("user1", 50), ("user2", 30)],
        "most_active_hour": 14
    }

    result = format_statistics_summary(stats)

    assert "100" in result
    assert "5" in result
    assert "14.3" in result
    assert "user1" in result
    assert "user2" in result


def test_format_statistics_summary_minimal():
    """Test statistics summary with minimal data"""
    stats = {
        "total_messages": 50,
        "active_users": 3,
        "days": 7,
        "avg_per_day": 7.1
    }

    result = format_statistics_summary(stats)

    assert "50" in result
    assert "3" in result
    assert "7.1" in result


def test_get_system_prompt():
    """Test system prompt retrieval"""
    prompt = get_system_prompt("qa_ru")

    assert "ассистент" in prompt or "ответ" in prompt

    prompt_en = get_system_prompt("qa")
    assert "assistant" in prompt or "helpful" in prompt.lower()


def test_get_system_prompt_default():
    """Test system prompt with default mode"""
    prompt = get_system_prompt()

    assert prompt is not None


# ========== OpenRouter Client Tests ==========

def test_openrouter_client_init():
    """Test OpenRouter client initialization"""
    client = OpenRouterClient(api_key="test_key")

    assert client.client is not None
    assert client.model == OpenRouterClient.DEFAULT_MODEL


def test_openrouter_client_init_with_model():
    """Test OpenRouter client initialization with custom model"""
    client = OpenRouterClient(api_key="test_key", model="custom/model")

    assert client.model == "custom/model"


def test_openrouter_client_init_no_key():
    """Test OpenRouter client initialization without API key"""
    with pytest.raises(ValueError):
        OpenRouterClient(api_key="")


def test_get_models_to_try():
    """Test getting models list"""
    client = OpenRouterClient(api_key="test_key")

    models = client._get_models_to_try()

    assert len(models) > 0
    assert client.model in models[0]


def test_set_model():
    """Test setting a different model"""
    client = OpenRouterClient(api_key="test_key")

    original_model = client.model
    client.set_model("new/model")

    assert client.model == "new/model"


def test_get_available_models():
    """Test getting available models"""
    client = OpenRouterClient(api_key="test_key")

    models = client.get_available_models()

    assert isinstance(models, list)
    assert len(models) > 0


@pytest.mark.asyncio
async def test_answer_question_empty_context():
    """Test answering question with empty context"""
    client = OpenRouterClient(api_key="test_key")

    result = await client.answer_question(
        question="Test question",
        context_messages=[],
        language="ru"
    )

    assert "Недостаточно контекста" in result


@pytest.mark.asyncio
async def test_answer_question_no_question():
    """Test answering with no question"""
    client = OpenRouterClient(api_key="test_key")

    result = await client.answer_question(
        question="",
        context_messages=[{"message_text": "test"}],
        language="ru"
    )

    assert "задайте вопрос" in result


@pytest.mark.asyncio
async def test_generate_summary_empty_messages():
    """Test generating summary with no messages"""
    client = OpenRouterClient(api_key="test_key")

    result = await client.generate_summary(
        messages=[],
        language="ru"
    )

    assert "Нет сообщений" in result


@pytest.mark.asyncio
async def test_generate_recommendations_empty_messages():
    """Test generating recommendations with no messages"""
    client = OpenRouterClient(api_key="test_key")

    result = await client.generate_recommendations(
        messages=[],
        language="ru"
    )

    assert "Нет сообщений" in result


@pytest.mark.asyncio
async def test_generate_daily_report_empty():
    """Test daily report generation with no messages"""
    client = OpenRouterClient(api_key="test_key")

    result = await client.generate_daily_report(messages=[])

    assert "summary" in result
    assert "recommendations" in result


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
@pytest.mark.asyncio
async def test_answer_question_with_context(mock_call_llm):
    """Test answering question with context"""
    mock_call_llm.return_value = "Test answer"

    client = OpenRouterClient(api_key="test_key")

    context_messages = [
        {"username": "user1", "message_text": "Previous message", "timestamp": "2024-01-01 10:00"}
    ]

    result = await client.answer_question(
        question="What was discussed?",
        context_messages=context_messages,
        language="ru"
    )

    assert result == "Test answer"
    mock_call_llm.assert_called_once()


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
@pytest.mark.asyncio
async def test_generate_summary_with_messages(mock_call_llm):
    """Test generating summary with messages"""
    mock_call_llm.return_value = "Summary: Topics discussed include X, Y, Z"

    client = OpenRouterClient(api_key="test_key")

    messages = [
        {"username": "user1", "message_text": "Let's discuss X", "timestamp": "2024-01-01 10:00"}
    ]

    result = await client.generate_summary(messages=messages, language="ru")

    assert "Summary" in result
    mock_call_llm.assert_called_once()


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
@pytest.mark.asyncio
async def test_llm_error_handling(mock_call_llm):
    """Test LLM error handling"""
    from openai import APIError

    mock_call_llm.side_effect = APIError("API Error")

    client = OpenRouterClient(api_key="test_key")

    messages = [{"message_text": "test"}]

    result = await client.answer_question(
        question="Test",
        context_messages=messages,
        language="ru"
    )

    assert "ошибка" in result.lower()


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
def test_test_connection_success(mock_call_llm):
    """Test connection test success"""
    mock_call_llm.return_value = "OK"

    client = OpenRouterClient(api_key="test_key")

    result = client.test_connection()

    assert result is True


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
def test_test_connection_failure(mock_call_llm):
    """Test connection test failure"""
    mock_call_llm.side_effect = Exception("Connection error")

    client = OpenRouterClient(api_key="test_key")

    result = client.test_connection()

    assert result is False


def test_create_openrouter_client():
    """Test OpenRouter client factory function"""
    client = create_openrouter_client(api_key="test_key")

    assert isinstance(client, OpenRouterClient)


def test_create_openrouter_client_with_model():
    """Test OpenRouter client factory with model"""
    client = create_openrouter_client(api_key="test_key", model="custom/model")

    assert isinstance(client, OpenRouterClient)
    assert client.model == "custom/model"


# ========== Integration Tests ==========

@patch('app.llm.openrouter.OpenRouterClient._call_llm')
@pytest.mark.asyncio
async def test_full_qa_flow(mock_call_llm):
    """Test full QA flow"""
    mock_call_llm.return_value = "Based on the context, the topic is project updates."

    client = OpenRouterClient(api_key="test_key")

    context_messages = [
        {"username": "alice", "first_name": "Alice", "message_text": "Project status update", "timestamp": "2024-01-01 10:00"},
        {"username": "bob", "first_name": "Bob", "message_text": "Everything looks good", "timestamp": "2024-01-01 10:01"},
    ]

    result = await client.answer_question(
        question="What is the current project status?",
        context_messages=context_messages,
        language="ru"
    )

    assert "project" in result.lower() or "статус" in result.lower()


@patch('app.llm.openrouter.OpenRouterClient._call_llm')
@pytest.mark.asyncio
async def test_full_summary_and_coaching_flow(mock_call_llm):
    """Test full summary and coaching flow"""
    # First call for summary, second for recommendations
    mock_call_llm.side_effect = [
        "Summary: The team discussed project milestones and next steps.",
        "Recommendations: Communication is good, consider more regular updates."
    ]

    client = OpenRouterClient(api_key="test_key")

    messages = [
        {"username": "alice", "message_text": "Let's review milestones", "timestamp": "2024-01-01 10:00"},
        {"username": "bob", "message_text": "We completed phase 1", "timestamp": "2024-01-01 10:01"},
    ]

    summary = await client.generate_summary(messages, language="ru")
    recommendations = await client.generate_recommendations(messages, language="ru")

    assert "milestones" in summary.lower() or "этап" in summary.lower()
    assert "Communication" in recommendations or "коммуникац" in recommendations.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
