"""
Telegram Bot Utilities - Helper functions for bot operations
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from telegram import Update, Message, User, Chat

logger = logging.getLogger(__name__)


def format_message(message: Message) -> str:
    """
    Format a Telegram message for display/storage.

    Args:
        message: Telegram Message object

    Returns:
        Formatted message string
    """
    user = message.from_user
    chat = message.chat

    user_info = f"@{user.username}" if user.username else user.first_name
    chat_info = chat.title if chat.title else f"chat_{chat.id}"

    text = message.text or "[media/file]"
    timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")

    return f"[{timestamp}] {chat_info} | {user_info}: {text}"


def extract_context(messages: List[Dict], limit: int = 10) -> str:
    """
    Extract and format message context for LLM.

    Args:
        messages: List of message dictionaries
        limit: Maximum number of messages to include

    Returns:
        Formatted context string
    """
    if not messages:
        return "No previous messages."

    # Take the most recent messages up to the limit
    recent_messages = messages[:limit]

    context_parts = []
    for msg in reversed(recent_messages):  # Show in chronological order
        username = msg.get('username') or msg.get('first_name', 'Unknown')
        text = msg.get('message_text', '') or '[media/file]'
        timestamp = msg.get('timestamp', '')
        if isinstance(timestamp, str):
            timestamp_str = timestamp
        else:
            timestamp_str = str(timestamp)

        context_parts.append(f"{timestamp_str} | {username}: {text}")

    return "\n".join(context_parts)


def parse_summary(llm_response: str) -> Dict[str, str]:
    """
    Parse LLM response to extract summary and recommendations.

    Args:
        llm_response: Raw response from LLM

    Returns:
        Dictionary with 'summary' and 'recommendations' keys
    """
    response = llm_response.strip()

    # Try to split by common section headers
    separators = [
        "\n## Рекомендации",
        "\n### Рекомендации",
        "\n## Coaching",
        "\n### Coaching",
        "\n---",
        "\n***"
    ]

    for sep in separators:
        if sep in response:
            parts = response.split(sep, 1)
            return {
                "summary": parts[0].strip(),
                "recommendations": parts[1].strip() if len(parts) > 1 else ""
            }

    # If no separator found, put everything in summary
    return {
        "summary": response,
        "recommendations": ""
    }


def get_user_display_name(user: User) -> str:
    """
    Get a display name for a user.

    Args:
        user: Telegram User object

    Returns:
        Display name (username or first_name)
    """
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        if user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.first_name
    return f"User_{user.id}"


def get_chat_display_name(chat: Chat) -> str:
    """
    Get a display name for a chat.

    Args:
        chat: Telegram Chat object

    Returns:
        Display name
    """
    if chat.title:
        return chat.title
    if chat.type == "private":
        return f"private_{chat.id}"
    return f"{chat.type}_{chat.id}"


def is_bot_mentioned(message: Message, bot_username: str) -> bool:
    """
    Check if the bot is mentioned in a message.

    Args:
        message: Telegram Message object
        bot_username: Bot's username (without @)

    Returns:
        True if bot is mentioned
    """
    if not message.text:
        return False

    text = message.text.lower()
    mentions = [f"@{bot_username.lower()}", bot_username.lower()]

    return any(mention in text for mention in mentions)


def extract_question_from_mention(message: Message, bot_username: str) -> Optional[str]:
    """
    Extract the question part from a bot mention message.

    Args:
        message: Telegram Message object
        bot_username: Bot's username (without @)

    Returns:
        Question text or None
    """
    if not message.text:
        return None

    text = message.text

    # Remove bot mention variants
    for prefix in [f"@{bot_username}", f"@{bot_username.lower()}"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    # Remove common prefixes
    prefixes_to_remove = [",", ":", "-"]
    for prefix in prefixes_to_remove:
        if text.startswith(prefix):
            text = text[1:].strip()

    return text if text else None


def format_summary_message(summary: str, recommendations: str = "") -> str:
    """
    Format the daily summary message for sending to chat.

    Args:
        summary: Daily summary text
        recommendations: Coaching recommendations text

    Returns:
        Formatted message ready to send
    """
    message = "📊 *Ежедневная сводка*\n\n"
    message += summary

    if recommendations:
        message += "\n\n💡 *Рекомендации коуча*\n\n"
        message += recommendations

    message += "\n\n---\nGenerated by Telegram Analytics Bot"

    return message


def truncate_text(text: str, max_length: int = 4096, suffix: str = "...") -> str:
    """
    Truncate text to fit Telegram message limit.

    Args:
        text: Text to truncate
        max_length: Maximum length (default 4096 for Telegram)
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def is_group_chat(chat: Chat) -> bool:
    """
    Check if chat is a group chat (group or supergroup).

    Args:
        chat: Telegram Chat object

    Returns:
        True if chat is a group
    """
    return chat.type in ["group", "supergroup"]


def is_private_chat(chat: Chat) -> bool:
    """
    Check if chat is private.

    Args:
        chat: Telegram Chat object

    Returns:
        True if chat is private
    """
    return chat.type == "private"


def get_message_type(message: Message) -> str:
    """
    Get the type of message (text, photo, etc.).

    Args:
        message: Telegram Message object

    Returns:
        Message type string
    """
    if message.text:
        return "text"
    elif message.photo:
        return "photo"
    elif message.video:
        return "video"
    elif message.document:
        return "document"
    elif message.sticker:
        return "sticker"
    elif message.voice:
        return "voice"
    elif message.audio:
        return "audio"
    elif message.animation:
        return "animation"
    else:
        return "unknown"
