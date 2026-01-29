"""
Bot handlers for aiogram 3.4+

Command and message handlers for the Telegram bot.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
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
chat_member_router = Router()


# ============================================================================
# Command Handlers
# ============================================================================

@command_router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    """
    Handle /start command.

    Shows welcome message with bot features.
    """
    language = settings.default_language

    text = get_text("bot.start", lang=language)
    await message.answer(text)


@command_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command - show help message."""
    language = settings.default_language

    text = get_text("bot.help", lang=language)
    await message.answer(text)


@command_router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database) -> None:
    """
    Handle /stats command - show chat statistics.

    Shows message count, active members, messages today, and last activity.
    """
    language = settings.default_language
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
    language = settings.default_language
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
    language = settings.default_language
    chat_id = message.chat.id

    # Ensure chat exists in database first (fixes FOREIGN KEY constraint)
    chat = await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type
    )
    internal_id = chat["id"]  # Use internal id for chat_settings

    # Get current settings
    settings = await db.get_chat_settings(chat_id)
    if settings is None:
        # Initialize default settings (using internal id)
        async with db.get_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)",
                (internal_id,)
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
    Handle /login command - show Telegram ID and link to web interface.

    Sends:
    1. User's Telegram ID
    2. Link to web interface

    OTP code will be generated when user requests it via web interface.
    """
    from app.config import settings

    # Get site URL
    site_url = getattr(settings, 'base_url', 'https://tghub.kulinich.ru')
    login_url = f"{site_url}/login"

    text = f"""🔐 <b>Вход в веб-интерфейс</b>

👤 <b>Ваш Telegram ID:</b> <code>{message.from_user.id}</code>

🌐 <a href="{login_url}">Открыть страницу входа</a>

<b>Инструкция:</b>
1. Откройте ссылку выше
2. Введите ваш Telegram ID
3. Нажмите "Получить код"
4. Мы отправим код сюда в Telegram"""

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=False)


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
    language = settings.default_language
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
    language = settings.default_language
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

    # Get or create chat (passing creator so they become owner for new chats)
    chat = await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title or message.chat.first_name or "Private Chat",
        chat_type=message.chat.type,
        creator_user_id=user_id  # Add creator as owner for new chats
    )

    # Add user as chat member (only if not already the owner)
    # get_or_create_chat now adds creator as owner for new chats
    # Check if user is already a member to avoid duplicates
    existing_member = await db.is_chat_member(user["id"], chat["id"])
    if not existing_member:
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
                    language = settings.default_language
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
    language = settings.default_language
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
    language = settings.default_language
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
    language = settings.default_language
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


# ============================================================================
# Chat Member Handlers
# ============================================================================

@chat_member_router.chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated, db: Database) -> None:
    """
    Handle chat member updates (users joining/leaving groups).

    This updates the chat_members table when:
    - User joins a group (member, administrator)
    - User leaves a group (left, kicked)
    - User is promoted/demoted (admin role changes)
    """
    from aiogram.enums import ChatMemberStatus

    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    # Skip private chats
    if chat_id > 0:
        return

    # Get internal chat id (chats.id, not telegram chat_id)
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        logger.warning(f"Chat {chat_id} not found in database for member update")
        return

    internal_chat_id = chat["id"]

    # Check status transitions
    if old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        # User is joining the group
        if new_status == ChatMemberStatus.CREATOR:
            role = "owner"  # Creator gets owner role
        elif new_status == ChatMemberStatus.ADMINISTRATOR:
            role = "admin"  # Administrator gets admin role
        else:
            role = "member"
        await db.add_chat_member(internal_chat_id, user_id, role=role)
        logger.info(f"User {user_id} joined chat {chat_id} as {role}")

    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        # User is leaving the group
        await db.update_member_left_at(internal_chat_id, user_id)
        logger.info(f"User {user_id} left chat {chat_id}")

    elif new_status == ChatMemberStatus.CREATOR:
        # User status changed to CREATOR (should be owner)
        await db.update_member_role(internal_chat_id, user_id, "owner")
        logger.info(f"User {user_id} is CREATOR in chat {chat_id}, set as owner")

    elif new_status == ChatMemberStatus.ADMINISTRATOR:
        # User was promoted to admin
        await db.update_member_role(internal_chat_id, user_id, "admin")
        logger.info(f"User {user_id} promoted to admin in chat {chat_id}")

    elif new_status == ChatMemberStatus.MEMBER:
        # User was demoted from admin/creator to regular member
        await db.update_member_role(internal_chat_id, user_id, "member")
        logger.info(f"User {user_id} demoted to member in chat {chat_id}")


@chat_member_router.my_chat_member()
async def handle_my_chat_member_update(event: ChatMemberUpdated, db: Database) -> None:
    """
    Handle bot's own chat member updates.

    This tracks when the bot itself joins or leaves groups.
    """
    from aiogram.enums import ChatMemberStatus

    chat_id = event.chat.id
    new_status = event.new_chat_member.status

    # Skip private chats
    if chat_id > 0:
        return

    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        # Bot was added to a group
        chat = await db.get_or_create_chat(
            chat_id=chat_id,
            title=event.chat.title or f"Group {chat_id}",
            chat_type=event.chat.type
        )
        logger.info(f"Bot added to chat: {chat['title']} ({chat_id})")

        # Add bot as member
        bot_info = event.new_chat_member.user
        await db.get_or_create_user(
            user_id=bot_info.id,
            username=bot_info.username,
            first_name=bot_info.first_name
        )
        await db.add_chat_member(chat["id"], bot_info.id, role="member")

    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        # Bot was removed from a group
        logger.info(f"Bot removed from chat: {chat_id}")
        # Optionally mark chat as inactive


# Export routers for registration
__all__ = [
    "command_router",
    "message_router",
    "callback_router",
    "chat_member_router",
]
