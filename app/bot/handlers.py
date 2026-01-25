"""
Telegram Bot Handlers - Event handlers for Telegram bot
"""

import logging
from typing import Optional
from telegram import Update, Message
from telegram.ext import ContextTypes
from app.bot.utils import (
    get_user_display_name,
    get_chat_display_name,
    is_bot_mentioned,
    extract_question_from_mention,
    format_summary_message,
    truncate_text
)

logger = logging.getLogger(__name__)


class BotHandlers:
    """
    Collection of Telegram bot event handlers.

    Handles:
    - New messages
    - Edited messages
    - Deleted messages
    - Bot mentions (QA)
    - New chat members
    """

    def __init__(self, db, llm_client, config):
        """
        Initialize handlers with dependencies.

        Args:
            db: Database instance
            llm_client: OpenRouter LLM client
            config: Application configuration (Settings object)
        """
        self.db = db
        self.llm_client = llm_client
        self.config = config
        self.bot_username = None  # Will be set from the bot itself

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle incoming messages - save to database and check for mentions.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.message or not update.effective_chat:
            return

        message = update.message
        chat = update.effective_chat
        user = message.from_user

        # Set bot username if not set
        if context.bot and not self.bot_username:
            self.bot_username = context.bot.username

        # Skip messages from bots to avoid loops
        if user and user.is_bot:
            return

        try:
            # Add chat to database if new
            chat_name = get_chat_display_name(chat)
            self.db.add_chat(
                chat_id=chat.id,
                chat_name=chat_name,
                chat_type=chat.type
            )

            # Extract message data
            telegram_message_id = message.message_id
            user_id = user.id
            username = user.username
            first_name = user.first_name
            last_name = user.last_name
            message_text = message.text or message.caption or None
            timestamp = message.date

            # Save to database
            success = self.db.insert_message(
                telegram_message_id=telegram_message_id,
                chat_id=chat.id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                message_text=message_text,
                timestamp=timestamp
            )

            if success:
                logger.debug(f"Saved message {telegram_message_id} from chat {chat.id}")
            else:
                logger.warning(f"Failed to save message {telegram_message_id} (may be duplicate)")

            # Check if bot is mentioned and handle QA
            if self.bot_username and message_text and is_bot_mentioned(message, self.bot_username):
                await self._handle_mention(update, context)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle edited messages.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.edited_message or not update.effective_chat:
            return

        message = update.edited_message
        chat = update.effective_chat

        logger.info(f"Message {message.message_id} in chat {chat.id} was edited")

        # For now, we just log edits. Could be extended to track edits in database.
        # Edit tracking would require a separate table or modifying the messages table.

    async def handle_deleted_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle deleted messages.

        Note: Telegram doesn't send delete events for all message types.
        This handler is for future enhancement.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        # Telegram Bot API doesn't provide direct delete events
        # This would need to be implemented via other means
        pass

    async def handle_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle chat member updates (e.g., bot added to chat).

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.chat_member:
            return

        status_change = update.chat_member
        old_status = status_change.old_chat_member.status
        new_status = status_change.new_chat_member.status
        user = status_change.new_chat_member.user

        # Check if bot was added
        if user.is_bot and new_status in ["member", "administrator"]:
            logger.info(f"Bot was added to chat")
            await self._send_welcome_message(update, context)

        # Log member status changes
        logger.info(f"User {user.id} status changed from {old_status} to {new_status}")

    async def handle_my_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle updates about the bot's status in a chat.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.my_chat_member:
            return

        status_change = update.my_chat_member
        new_status = status_change.new_chat_member.status

        # Bot was added to a chat
        if new_status in ["member", "administrator"]:
            chat = update.effective_chat
            logger.info(f"Bot was added to chat {chat.id if chat else 'unknown'}")

            # Send welcome message
            await self._send_welcome_message(update, context)

    async def handle_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /start command.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.message:
            return

        chat = update.effective_chat

        welcome_text = (
            "👋 Привет! Я бот для аналитики чатов.\n\n"
            "Мои возможности:\n"
            "• 📝 Сохраняю историю сообщений\n"
            "• 💬 Отвечаю на вопросы (упомяни @bot)\n"
            "• 📊 Присылаю ежедневные сводки\n"
            "• 💡 Даю рекомендации по коммуникации\n\n"
            "Добавь меня в групповой чат и выдай права администратора."
        )

        await update.message.reply_text(welcome_text)

    async def handle_command_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /help command.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        help_text = (
            "📖 *Справка по боту*\n\n"
            "*Команды:*\n"
            "/start - Приветственное сообщение\n"
            "/help - Эта справка\n"
            "/stats - Статистика чата\n\n"
            "*Функции в чате:*\n"
            "• @bot вопрос - задать вопрос боту\n"
            "• Бот автоматически сохраняет сообщения\n"
            "• Ежедневная сводка в 16:00 МСК\n\n"
            "*Веб-интерфейс:*\n"
            "Доступен на порту, указанном в настройках."
        )

        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def handle_command_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /stats command - show chat statistics.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.message or not update.effective_chat:
            return

        chat = update.effective_chat

        # Get messages from last 7 days
        messages = self.db.get_messages(chat_id=chat.id, days=7)

        if not messages:
            await update.message.reply_text("Нет данных за последние 7 дней.")
            return

        # Calculate basic stats
        total_messages = len(messages)

        # Count by user
        user_counts = {}
        for msg in messages:
            username = msg.get('username') or msg.get('first_name', 'Unknown')
            user_counts[username] = user_counts.get(username, 0) + 1

        active_users = len(user_counts)
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Format response
        stats_text = (
            f"📊 *Статистика чата (7 дней)*\n\n"
            f"📝 Сообщений: {total_messages}\n"
            f"👥 Участников: {active_users}\n"
            f"📈 В среднем: {total_messages / 7:.1f} сообщений/день\n\n"
        )

        if top_users:
            stats_text += "*🏆 Активность:*\n"
            for username, count in top_users:
                stats_text += f"  • {username}: {count}\n"

        await update.message.reply_text(stats_text, parse_mode="Markdown")

    async def _handle_mention(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle when bot is mentioned in a message.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        if not update.message or not self.bot_username:
            return

        message = update.message
        chat = update.effective_chat

        # Extract the question
        question = extract_question_from_mention(message, self.bot_username)

        if not question:
            await message.reply_text(
                "😕 Пожалуйста, задайте вопрос после упоминания.\n"
                f"Пример: @{self.bot_username} Какая была тема обсуждения?"
            )
            return

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")

        # Get context messages
        context_messages = self.db.get_messages(
            chat_id=chat.id,
            days=self.config.summary_days,
            exclude_deleted=True
        )

        # Limit context to avoid token limits
        context_limit = self.config.context_messages
        limited_context = context_messages[:context_limit]

        # Get answer from LLM
        try:
            answer = self.llm_client.answer_question(
                question=question,
                context_messages=limited_context,
                language="ru"
            )

            # Truncate if too long
            answer = truncate_text(answer, max_length=4000)

            # Send reply
            await message.reply_text(answer)

        except Exception as e:
            logger.error(f"Error generating answer: {e}", exc_info=True)
            await message.reply_text(
                "😔 Извините, произошла ошибка при генерации ответа. Попробуйте позже."
            )

    async def _send_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Send welcome message when bot joins a chat.

        Args:
            update: Telegram Update object
            context: Bot context
        """
        chat = update.effective_chat
        if not chat or not self.bot_username:
            return

        welcome_text = (
            f"👋 Привет! Я добавлен в этот чат для аналитики.\n\n"
            f"Я буду:\n"
            f"• 📝 Сохранять историю сообщений\n"
            f"• 💬 Отвечать на вопросы (упомяни @{self.bot_username})\n"
            f"• 📊 Присылать ежедневные сводки в 16:00 МСК\n"
            f"• 💡 Давать рекомендации по коммуникации\n\n"
            f"Для вопросов упомяни меня: @{self.bot_username} вопрос"
        )

        try:
            await context.bot.send_message(chat_id=chat.id, text=welcome_text)
            logger.info(f"Sent welcome message to chat {chat.id}")
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}", exc_info=True)


def create_handlers(db, llm_client, config):
    """
    Factory function to create BotHandlers instance.

    Args:
        db: Database instance
        llm_client: OpenRouter LLM client
        config: Application configuration

    Returns:
        BotHandlers instance
    """
    return BotHandlers(db=db, llm_client=llm_client, config=config)
