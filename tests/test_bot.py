"""
Tests for Telegram Bot modules
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime

# Import modules to test
from app.bot.utils import (
    format_message,
    extract_context,
    parse_summary,
    get_user_display_name,
    is_bot_mentioned,
    extract_question_from_mention,
    format_summary_message,
    truncate_text
)
from app.bot.handlers import BotHandlers
from app.bot.scheduler import BotScheduler
from app.bot.telegram_bot import TelegramBot


# ========== Utils Tests ==========

def test_format_message():
    """Test message formatting"""
    message = Mock()
    message.from_user.username = "testuser"
    message.from_user.first_name = "Test"
    message.chat.title = "Test Chat"
    message.chat.id = 123
    message.text = "Hello world"
    message.date = datetime(2024, 1, 1, 12, 0, 0)

    result = format_message(message)

    assert "@testuser" in result
    assert "Hello world" in result
    assert "Test Chat" in result


def test_extract_context():
    """Test context extraction for LLM"""
    messages = [
        {"username": "user1", "first_name": "User 1", "message_text": "First message", "timestamp": "2024-01-01 10:00"},
        {"username": "user2", "first_name": "User 2", "message_text": "Second message", "timestamp": "2024-01-01 10:01"},
    ]

    result = extract_context(messages, limit=10)

    assert "user1" in result
    assert "First message" in result
    assert "user2" in result
    assert "Second message" in result


def test_extract_context_empty():
    """Test context extraction with empty messages"""
    result = extract_context([])
    assert result == "Нет сообщений."


def test_parse_summary():
    """Test summary parsing"""
    response = """Это сводка.

## Рекомендации

Рекомендация 1
Рекомендация 2"""

    result = parse_summary(response)

    assert "summary" in result
    assert "recommendations" in result
    assert "Рекомендация 1" in result["recommendations"]


def test_get_user_display_name():
    """Test user display name"""
    user = Mock()
    user.username = "testuser"
    assert get_user_display_name(user) == "@testuser"

    user.username = None
    user.first_name = "Test"
    assert get_user_display_name(user) == "Test"

    user.first_name = "First"
    user.last_name = "Last"
    assert get_user_display_name(user) == "First Last"


def test_is_bot_mentioned():
    """Test bot mention detection"""
    message = Mock()
    message.text = None

    assert not is_bot_mentioned(message, "testbot")

    message.text = "Hello @testbot how are you?"
    assert is_bot_mentioned(message, "testbot")

    message.text = "Hello @TestBot how are you?"
    assert is_bot_mentioned(message, "testbot")


def test_extract_question_from_mention():
    """Test question extraction from mention"""
    message = Mock()
    message.text = "@testbot What is the weather today?"

    result = extract_question_from_mention(message, "testbot")

    assert result == "What is the weather today?"


def test_truncate_text():
    """Test text truncation"""
    long_text = "a" * 5000
    result = truncate_text(long_text, max_length=100)

    assert len(result) <= 103  # 100 + "..."
    assert result.endswith("...")


def test_truncate_text_short():
    """Test truncation with short text"""
    short_text = "Hello"
    result = truncate_text(short_text, max_length=100)

    assert result == "Hello"


# ========== Handlers Tests ==========

@pytest.fixture
def mock_db():
    """Mock database"""
    db = Mock()
    db.insert_message = Mock(return_value=True)
    db.add_chat = Mock(return_value=True)
    db.get_messages = Mock(return_value=[])
    return db


@pytest.fixture
def mock_llm():
    """Mock LLM client"""
    llm = Mock()
    llm.answer_question = Mock(return_value="Test answer")
    return llm


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.context_messages = 10
    config.summary_days = 7
    return config


@pytest.fixture
def bot_handlers(mock_db, mock_llm, mock_config):
    """Create BotHandlers instance"""
    return BotHandlers(db=mock_db, llm_client=mock_llm, config=mock_config)


def test_bot_handlers_init(bot_handlers, mock_db, mock_llm, mock_config):
    """Test BotHandlers initialization"""
    assert bot_handlers.db == mock_db
    assert bot_handlers.llm_client == mock_llm
    assert bot_handlers.config == mock_config
    assert bot_handlers.bot_username is None


@pytest.mark.asyncio
async def test_handle_command_start(bot_handlers):
    """Test /start command handler"""
    update = Mock()
    update.message = Mock()
    update.message.reply_text = AsyncMock()

    await bot_handlers.handle_command_start(update, None)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0]
    assert "Привет" in args[0]


@pytest.mark.asyncio
async def test_handle_command_help(bot_handlers):
    """Test /help command handler"""
    update = Mock()
    update.message = Mock()
    update.message.reply_text = AsyncMock()

    await bot_handlers.handle_command_help(update, None)

    update.message.reply_text.assert_called_once()


# ========== Scheduler Tests ==========

@pytest.fixture
def mock_scheduler_db():
    """Mock database for scheduler"""
    db = Mock()
    db.get_chats = Mock(return_value=[
        {"chat_id": 123, "chat_name": "Test Chat", "chat_type": "group"}
    ])
    db.get_messages = Mock(return_value=[
        {"username": "user1", "message_text": "Test message", "timestamp": "2024-01-01 10:00"}
    ])
    return db


@pytest.fixture
def mock_scheduler_llm():
    """Mock LLM for scheduler"""
    llm = Mock()
    llm.generate_summary = Mock(return_value="Test summary")
    llm.generate_recommendations = Mock(return_value="Test recommendations")
    return llm


@pytest.fixture
def mock_bot_app():
    """Mock bot application"""
    app = Mock()
    app.bot = Mock()
    app.bot.send_message = AsyncMock()
    return app


@pytest.fixture
def bot_scheduler(mock_scheduler_db, mock_scheduler_llm, mock_bot_app, mock_config):
    """Create BotScheduler instance"""
    scheduler = BotScheduler(
        db=mock_scheduler_db,
        llm_client=mock_scheduler_llm,
        bot=mock_bot_app,
        config=mock_config
    )
    return scheduler


def test_scheduler_init(bot_scheduler, mock_scheduler_db, mock_scheduler_llm, mock_bot_app, mock_config):
    """Test scheduler initialization"""
    assert bot_scheduler.db == mock_scheduler_db
    assert bot_scheduler.llm_client == mock_scheduler_llm
    assert bot_scheduler.bot == mock_bot_app
    assert bot_scheduler.config == mock_config


def test_parse_time(bot_scheduler):
    """Test time parsing"""
    hour, minute = bot_scheduler._parse_time("16:30")
    assert hour == 16
    assert minute == 30

    hour, minute = bot_scheduler._parse_time("09:05")
    assert hour == 9
    assert minute == 5

    with pytest.raises(ValueError):
        bot_scheduler._parse_time("invalid")


def test_parse_time_invalid(bot_scheduler):
    """Test time parsing with invalid format"""
    with pytest.raises(ValueError):
        bot_scheduler._parse_time("25:00")

    with pytest.raises(ValueError):
        bot_scheduler._parse_time("12:60")


@pytest.mark.asyncio
async def test_generate_manual_summary(bot_scheduler):
    """Test manual summary generation"""
    result = await bot_scheduler.generate_manual_summary(123)

    assert "summary" in result
    assert "recommendations" in result


# ========== TelegramBot Tests ==========

@pytest.fixture
def mock_telegram_bot_db():
    """Mock database for TelegramBot"""
    db = Mock()
    db.get_admin_user = Mock(return_value={"username": "admin", "password_hash": "hash"})
    return db


@pytest.fixture
def telegram_bot_instance(mock_telegram_bot_db, mock_config):
    """Create TelegramBot instance with mocked application"""
    with patch('app.bot.telegram_bot.Application') as mock_app:
        app_instance = Mock()
        mock_app.builder.return_value.token.return_value.build.return_value = app_instance

        bot = TelegramBot(token="test_token", db=mock_telegram_bot_db, config=mock_config)

        return bot


def test_telegram_bot_init(telegram_bot_instance):
    """Test TelegramBot initialization"""
    assert telegram_bot_instance.token == "test_token"
    assert telegram_bot_instance.application is not None


def test_telegram_bot_get_application(telegram_bot_instance):
    """Test get_application method"""
    app = telegram_bot_instance.get_application()
    assert app is not None


def test_telegram_bot_get_llm_client(telegram_bot_instance):
    """Test get_llm_client method"""
    llm = telegram_bot_instance.get_llm_client()
    assert llm is not None


# ========== Integration Tests ==========

def test_create_handlers(mock_db, mock_llm, mock_config):
    """Test handlers factory function"""
    from app.bot.handlers import create_handlers

    handlers = create_handlers(mock_db, mock_llm, mock_config)

    assert isinstance(handlers, BotHandlers)
    assert handlers.db == mock_db


def test_create_scheduler(mock_scheduler_db, mock_scheduler_llm, mock_bot_app, mock_config):
    """Test scheduler factory function"""
    from app.bot.scheduler import create_scheduler

    scheduler = create_scheduler(mock_scheduler_db, mock_scheduler_llm, mock_bot_app, mock_config)

    assert isinstance(scheduler, BotScheduler)


def test_create_bot(mock_telegram_bot_db, mock_config):
    """Test bot factory function"""
    from app.bot.telegram_bot import create_bot

    with patch('app.bot.telegram_bot.Application'):
        bot = create_bot(token="test_token", db=mock_telegram_bot_db, config=mock_config)
        assert isinstance(bot, TelegramBot)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
