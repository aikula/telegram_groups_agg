"""
Bot handlers for aiogram 3.4+

Command and message handlers for the Telegram bot.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Set

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import settings
from app.core.db import Database
from app.core.i18n import get_text
from app.core.llm import get_llm_client
from app.core.router import RouterAgent
from app.core.agent import SkillAgent


logger = logging.getLogger(__name__)


# Create routers for different handler types
command_router = Router()
message_router = Router()
callback_router = Router()


# Track processed QA requests to prevent duplicates (message_id, timestamp)
_processed_qa_requests: Set[tuple[int, int]] = set()
_qa_cleanup_task: Optional[asyncio.Task] = None


async def _cleanup_old_qa_requests():
    """Remove old QA request tracking entries every minute."""
    global _qa_cleanup_task
    while True:
        await asyncio.sleep(60)
        current_time = int(datetime.now().timestamp())
        # Remove entries older than 30 seconds
        to_remove = {msg_id for msg_id, ts in _processed_qa_requests if current_time - ts > 30}
        for msg_id in to_remove:
            _processed_qa_requests.discard((msg_id, ts))  # Need both parts for exact match


# ============================================================================
# Command Handlers
# ============================================================================

@command_router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    """
    Handle /start command.

    Shows welcome message with bot features.
    """
    language = "ru"  # TODO: Get from user settings

    text = get_text("bot.start", lang=language)
    await message.answer(text)


@command_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command - show help message."""
    language = "ru"  # TODO: Get from user settings

    text = get_text("bot.help", lang=language)
    await message.answer(text)


@command_router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database) -> None:
    """
    Handle /stats command - show chat statistics.

    Shows message count, active members, messages today, and last activity.
    """
    language = "ru"  # TODO: Get from user settings
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Get chat stats
    stats = await db.get_chat_stats(chat_id)

    text = get_text(
        "bot.stats",
        lang=language,
        message_count=stats["message_count"],
        member_count=stats["member_count"],
        messages_today=stats["messages_today"],
        last_activity=stats.get("last_activity", "N/A")
    )

    await message.answer(text)


@command_router.message(Command("export"))
async def cmd_export(message: Message, db: Database) -> None:
    """
    Handle /export command - export chat history.

    Sends a text file with all messages from the chat.
    """
    language = "ru"  # TODO: Get from user settings
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Get all messages
    messages = await db.get_messages(chat_id, limit=10000, include_deleted=False)

    if not messages:
        text = get_text("export.empty_chat", lang=language)
        await message.answer(text)
        return

    # Build export content
    lines = []
    for msg in messages:
        username = msg.get("username") or msg.get("first_name", "Unknown")
        timestamp = msg.get("timestamp", "")
        content = msg.get("content", "")
        lines.append(f"[{timestamp}] {username}: {content}")

    content = "\n".join(lines)

    # Send as file
    from aiogram.types import BufferedInputFile
    file_data = content.encode("utf-8")
    file = BufferedInputFile(file_data, filename=f"chat_export_{chat_id}.txt")

    await message.answer_document(
        document=file,
        caption=get_text("export.completed", lang=language, file_name=f"chat_export_{chat_id}.txt")
    )


@command_router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    """
    Handle /settings command - show chat settings.

    Shows inline keyboard for managing chat settings.
    """
    language = "ru"  # TODO: Get from user settings
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Get current settings
    settings = await db.get_chat_settings(chat_id)
    if settings is None:
        # Initialize default settings
        async with db.get_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)",
                (chat_id,)
            )
            await conn.commit()
        settings = await db.get_chat_settings(chat_id)

    # Build inline keyboard
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Сводки: " + ("✅" if settings.get("summary_enabled") else "❌"),
        callback_data=f"settings_toggle_summary_{chat_id}"
    )
    builder.button(
        text="🎓 Коучинг: " + ("✅" if settings.get("coach_enabled") else "❌"),
        callback_data=f"settings_toggle_coach_{chat_id}"
    )
    builder.button(
        text="🌐 Язык: " + settings.get("language", "ru").upper(),
        callback_data=f"settings_language_{chat_id}"
    )
    builder.adjust(2)

    await message.answer(
        "⚙️ Настройки чата:",
        reply_markup=builder.as_markup()
    )


@command_router.message(Command("login"))
async def cmd_login(message: Message, db: Database) -> None:
    """
    Handle /login command - generate OTP for web authentication.

    Sends a 6-digit one-time code valid for 5 minutes.
    User enters this code on the website to authenticate.
    """
    from app.config import settings

    # Get or create user
    user = await db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Generate OTP
    code = await db.create_otp(
        user_id=user['id'],
        telegram_id=message.from_user.id,
        valid_minutes=5
    )

    # Get site URL
    site_url = getattr(settings, 'base_url', 'https://tghub.kulinich.ru')

    text = f"""🔐 <b>Код для входа на сайт</b>

Ваш код: <code>{code}</code>

⏱ Код действителен 5 минут

🌐 Перейдите на сайт и введите этот код:
{site_url}/login

⚠️ <i>Никому не передавайте этот код!</i>"""

    await message.answer(text, parse_mode="HTML")


@command_router.message(Command("diagnostics"))
async def cmd_diagnostics(message: Message, db: Database) -> None:
    """
    Handle /diagnostics command - show bot and chat information.

    Shows:
    - Bot permissions
    - Chat list in database
    - Whether bot is still a member of each chat
    """
    # Only allow in private chat
    if message.chat.type != "private":
        await message.answer("⚠️ Эта команда работает только в личном сообщении боту")
        return

    from app.bot.bot import get_bot

    bot = get_bot()

    # Get bot info
    try:
        bot_info = await bot.get_me()
    except Exception as e:
        await message.answer(f"❌ Ошибка получения информации о боте: {e}")
        return

    # Build diagnostics message
    lines = [
        "🤖 <b>Диагностика бота</b>",
        "",
        f"👤 Бот: @{bot_info.username}",
        f"📛 Может читать сообщения групп: {'✅ Да' if bot_info.can_read_all_group_messages else '❌ НЕТ'}",
        f"👥 Может вступать в группы: {'✅ Да' if bot_info.can_join_groups else '❌ НЕТ'}",
        "",
    ]

    if not bot_info.can_read_all_group_messages:
        lines.extend([
            "⚠️ <b>ПРОБЛЕМА:</b> Бот НЕ может читать сообщения в группах!",
            "",
            "<b>Решение:</b>",
            "1. Сделайте бота АДМИНОМ в группах",
            "   (Откройте группу → Настройки → Администраторы)",
            "",
            "2. ИЛИ отключите Privacy Mode:",
            "   - Откройте @BotFather",
            "   - /setprivacy",
            "   - Выберите бота",
            "   - Отключите",
            "",
        ])

    # Get chats from database
    lines.append("📊 <b>Чаты в базе данных:</b>")
    lines.append("")

    chats = await db.get_chats(active_only=False, limit=20)

    if not chats:
        lines.extend([
            "   ⚠️ Чатов нет!",
            "",
            "   ➕ Добавьте бота в группы/каналы",
            "   ➕ Отправьте сообщение в группу",
            "   ➕ Запустите /diagnostics снова",
        ])
    else:
        for chat in chats:
            lines.append(f"   • {chat['title']} (ID: {chat['id']})")

            # Check if bot is still a member
            try:
                chat_info = await bot.get_chat(chat['id'])
                member_count = getattr(chat_info, 'member_count', '?')
                lines.append(f"     ✑ Участников: {member_count}")
            except Exception as e:
                lines.append(f"     ❌ Бот НЕ состоит: {str(e)[:50]}")
            lines.append("")

    lines.extend([
        "💡 <b>Что делать:</b>",
        "1. Если бот не в группах → добавьте его",
        "2. Если бот не может читать сообщения → сделайте админом",
        "3. После этого отправьте сообщение в группу",
        "",
        "🔄 Bot Commands v2.0",
    ])

    await message.answer("\n".join(lines), parse_mode="HTML")


@command_router.message(Command("summarize_thread"))
async def cmd_summarize_thread(message: Message, db: Database) -> None:
    """
    Handle /summarize_thread command - summarize discussion thread.

    Works in groups when replying to a message to summarize that thread.
    """
    language = "ru"  # TODO: Get from user settings
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Check if this is a reply to a message
    if not message.reply_to_message:
        text = get_text("thread_summary.no_thread", lang=language)
        await message.answer(text)
        return

    # Get thread messages (reply_to_message and replies to it)
    reply_to_id = message.reply_to_message.message_id

    # Get recent messages as context
    messages = await db.get_recent_messages(chat_id, limit=20, hours=24)

    if not messages:
        text = get_text("qa.no_context", lang=language)
        await message.answer(text)
        return

    # Generate summary
    llm = get_llm_client()

    # Format context
    context_text = "\n".join([
        f"[{msg.get('timestamp', '')}] {msg.get('username', 'User')}: {msg.get('text', msg.get('content', ''))}"
        for msg in messages
    ])

    try:
        result = await llm.generate(
            get_text(
                "thread_summary.prompt",
                lang=language,
                messages=context_text
            )
        )

        # Send summary
        text = get_text("thread_summary.title", lang=language) + "\n\n" + result["text"]
        await message.answer(text)

        # Log usage
        await db.log_llm_usage(
            user_id=message.from_user.id,
            chat_id=chat_id,
            skill="thread_summary",
            tokens_prompt=result["usage"]["prompt_tokens"],
            tokens_completion=result["usage"]["completion_tokens"],
            cost_usd=result.get("cost_usd", 0.0)
        )

    except Exception as e:
        logger.error(f"Error generating thread summary: {e}")
        text = get_text("error.llm_failed", lang=language)
        await message.answer(text)


@command_router.message(Command("ask"))
async def cmd_ask(message: Message, db: Database) -> None:
    """
    Handle /ask command - ask a question about the chat.

    Usage: /ask What was discussed today?
    """
    language = "ru"  # TODO: Get from user settings
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Extract question from command args
    question = message.text or ""
    question = question.replace("/ask", "").strip()

    if not question:
        await message.answer("Пожалуйста, задайте вопрос после команды.\nПример: /ask Что обсуждали сегодня?")
        return

    # === NEW AGENTIC ARCHITECTURE (v2.1) ===
    # Use Router + SkillAgent instead of direct LLM call
    llm = get_llm_client()

    try:
        # Step 1: Route query to appropriate skill
        router = RouterAgent(db, llm)
        skill_name = await router.route(question, chat_id=chat_id)

        # Step 2: Execute skill with tool calling
        agent = SkillAgent(db, llm)
        response = await agent.execute(
            skill_name=skill_name,
            query=question,
            chat_id=chat_id,
            user_id=message.from_user.id
        )

        # Send answer
        await message.answer(response)

    except Exception as e:
        logger.error(f"Error in agentic flow: {e}")
        text = get_text("error.llm_failed", lang=language)
        await message.answer(text)


# ============================================================================
# Message Handlers (save to database)
# ============================================================================

@message_router.message()
async def handle_message(message: Message, db: Database, bot: Bot) -> None:
    """
    Handle regular messages - save to database and respond to bot mentions.

    This handler processes all text messages:
    1. Saves them to the database
    2. If bot is mentioned (@bot_username), answers using chat context
    """
    # DEBUG: Log all incoming messages
    logger.info(f"📨 Message received: chat_id={message.chat.id}, from={message.from_user.id if message.from_user else None}, has_text={bool(message.text)}, has_caption={bool(message.caption)}, content_type={message.content_type}")

    # Skip messages without text (e.g., stickers, photos without caption)
    if not message.text and not message.caption:
        logger.debug(f"⏭️ Skipping message: no text or caption")
        return

    # Skip messages from bots
    if message.from_user and message.from_user.is_bot:
        logger.debug(f"⏭️ Skipping bot message")
        return

    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None

    if not user_id:
        logger.debug(f"⏭️ Skipping message: no user_id")
        return

    # Get or create user
    user = await db.get_or_create_user(
        user_id=user_id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or "",
        last_name=message.from_user.last_name or "",
    )

    # Get or create chat
    chat = await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )

    # Add user as chat member
    await db.add_chat_member(chat["id"], user["id"])

    # Save message
    content = message.text or message.caption or ""
    timestamp = message.date  # aiogram 3.x already provides datetime object

    await db.save_message(
        chat_id=chat_id,
        message_id=message.message_id,
        user_id=user_id,
        content=content,
        timestamp=timestamp
    )

    logger.debug(f"Saved message {message.message_id} from chat {chat_id}")

    # Check for bot mention and respond if found (only for text messages, not captions)
    if message.text and message.chat.type != "private":
        # Get bot username to check for mentions
        bot_info = await bot.get_me()
        bot_username = bot_info.username

        if bot_username:
            mention = f"@{bot_username}"

            if mention in message.text:
                # Extract question (remove the bot mention)
                question = message.text.replace(mention, "").strip()

                if question:
                    # Check if we already processed this QA request (prevent duplicates)
                    current_time = int(datetime.now().timestamp())
                    request_key = (message.message_id, current_time)

                    if request_key in _processed_qa_requests:
                        logger.debug(f"Skipping duplicate QA request for message {message.message_id}")
                        return

                    # Mark as being processed
                    _processed_qa_requests.add(request_key)

                    language = "ru"  # TODO: Get from user settings
                    logger.info(f"🤖 Bot mention detected from user {user_id}: {question}")

                    # === NEW AGENTIC ARCHITECTURE (v2.1) ===
                    # Use Router + SkillAgent instead of direct LLM call
                    llm = get_llm_client()

                    try:
                        # Step 1: Route query to appropriate skill
                        router = RouterAgent(db, llm)
                        skill_name = await router.route(question, chat_id=chat_id)
                        logger.info(f"📍 Routed to skill: {skill_name}")

                        # Step 2: Execute skill with tool calling
                        agent = SkillAgent(db, llm)
                        response = await agent.execute(
                            skill_name=skill_name,
                            query=question,
                            chat_id=chat_id,
                            user_id=user_id
                        )

                        # Send answer
                        await message.reply(response)

                    except Exception as e:
                        logger.error(f"Error in agentic flow: {e}")
                        text = get_text("error.llm_failed", lang=language)
                        await message.reply(text)


# ============================================================================
# Callback Query Handlers (Inline buttons)
# ============================================================================

@callback_router.callback_query(F.data.startswith("settings_toggle_summary_"))
async def cb_toggle_summary(callback: CallbackQuery, db: Database) -> None:
    """Toggle daily summary setting."""
    language = "ru"
    chat_id = int(callback.data.split("_")[-1])

    # Get current settings
    settings = await db.get_chat_settings(chat_id)
    current = settings.get("summary_enabled", 1) if settings else 1
    new_value = 0 if current else 1

    # Update setting
    await db.update_chat_settings(chat_id, {"summary_enabled": new_value})

    # Update button
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Сводки: " + ("✅" if new_value else "❌"),
        callback_data=f"settings_toggle_summary_{chat_id}"
    )
    builder.button(
        text="🎓 Коучинг: " + ("✅" if (settings.get("coach_enabled", 1) if settings else 1) else "❌"),
        callback_data=f"settings_toggle_coach_{chat_id}"
    )
    builder.button(
        text="🌐 Язык: " + (settings.get("language", "ru") if settings else "ru").upper(),
        callback_data=f"settings_language_{chat_id}"
    )
    builder.adjust(2)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

    text = get_text("settings.summary_enabled" if new_value else "settings.summary_disabled", lang=language)
    await callback.message.answer(text)


@callback_router.callback_query(F.data.startswith("settings_toggle_coach_"))
async def cb_toggle_coach(callback: CallbackQuery, db: Database) -> None:
    """Toggle coaching setting."""
    language = "ru"
    chat_id = int(callback.data.split("_")[-1])

    # Get current settings
    settings = await db.get_chat_settings(chat_id)
    current = settings.get("coach_enabled", 1) if settings else 1
    new_value = 0 if current else 1

    # Update setting
    await db.update_chat_settings(chat_id, {"coach_enabled": new_value})

    # Update button
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Сводки: " + ("✅" if (settings.get("summary_enabled", 1) if settings else 1) else "❌"),
        callback_data=f"settings_toggle_summary_{chat_id}"
    )
    builder.button(
        text="🎓 Коучинг: " + ("✅" if new_value else "❌"),
        callback_data=f"settings_toggle_coach_{chat_id}"
    )
    builder.button(
        text="🌐 Язык: " + (settings.get("language", "ru") if settings else "ru").upper(),
        callback_data=f"settings_language_{chat_id}"
    )
    builder.adjust(2)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

    text = get_text("settings.coach_enabled" if new_value else "settings.coach_disabled", lang=language)
    await callback.message.answer(text)


@callback_router.callback_query(F.data.startswith("settings_language_"))
async def cb_language(callback: CallbackQuery, db: Database) -> None:
    """Cycle through language options."""
    language = "ru"
    chat_id = int(callback.data.split("_")[-1])

    # Get current settings
    settings = await db.get_chat_settings(chat_id)
    current = settings.get("language", "ru") if settings else "ru"

    # Cycle: ru -> en -> ru
    new_value = "en" if current == "ru" else "ru"

    # Update setting
    await db.update_chat_settings(chat_id, {"language": new_value})

    # Update button
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Сводки: " + ("✅" if (settings.get("summary_enabled", 1) if settings else 1) else "❌"),
        callback_data=f"settings_toggle_summary_{chat_id}"
    )
    builder.button(
        text="🎓 Коучинг: " + ("✅" if (settings.get("coach_enabled", 1) if settings else 1) else "❌"),
        callback_data=f"settings_toggle_coach_{chat_id}"
    )
    builder.button(
        text="🌐 Язык: " + new_value.upper(),
        callback_data=f"settings_language_{chat_id}"
    )
    builder.adjust(2)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

    await callback.message.answer(f"Language changed to {new_value.upper()}")


# Export routers for registration
__all__ = [
    "command_router",
    "message_router",
    "callback_router",
]
