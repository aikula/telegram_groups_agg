"""
Core internationalization module - Multi-language support (ru/en)

Provides translation strings for bot messages, API responses, and UI text.
All translations are stored inline to avoid external file dependencies.
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class TranslationSet:
    """A set of translations for a specific language"""
    code: str
    name: str
    flag: str
    translations: Dict[str, str]

    def get(self, key: str, **kwargs) -> str:
        """
        Get translated string with optional formatting.

        Args:
            key: Translation key (e.g., 'welcome', 'error.access_denied')
            **kwargs: Optional formatting arguments

        Returns:
            Translated string, or the key itself if not found
        """
        text = self.translations.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text


# Russian translations
RU_TRANSLATIONS = {
    # Bot commands
    "bot.start": (
        "👋 Добро пожаловать в Chat Analytics Bot!\n\n"
        "Команды:\n"
        "/stats - Статистика чата\n"
        "/export - Экспорт истории чата\n"
        "/summarize_thread - Суммаризация обсуждения\n"
        "/help - Справка"
    ),
    "bot.stats": (
        "📊 Статистика чата:\n"
        "- Всего сообщений: {message_count}\n"
        "- Активных участников: {member_count}\n"
        "- Сообщений сегодня: {messages_today}\n"
        "- Последняя активность: {last_activity}"
    ),
    "bot.help": (
        "Команды:\n"
        "/start - Приветственное сообщение\n"
        "/stats - Статистика чата\n"
        "/export - Экспорт чата в TXT\n"
        "/summarize_thread - Суммаризация обсуждения\n"
        "/help - Это сообщение\n\n"
        "Функции:\n"
        "- @{bot} вопрос - Задать вопрос о чате\n"
        "- В личном чате - SQL-агент для запросов к данным"
    ),

    # Errors
    "error.access_denied": "🚫 Доступ запрещён",
    "error.chat_not_found": "❌ Чат не найден",
    "error.invalid_request": "❌ Неверный запрос",
    "error.rate_limit_exceeded": "⚠️ Превышен лимит запросов. Попробуйте позже.",
    "error.encryption_failed": "❌ Ошибка шифрования",
    "error.decryption_failed": "❌ Ошибка расшифровки",
    "error.llm_failed": "❌ Ошибка AI сервиса",
    "error.database_error": "❌ Ошибка базы данных",

    # SQL Agent
    "sql_agent.unsafe_query": "⚠️ Небезопасный SQL запрос заблокирован",
    "sql_agent.query_error": "❌ Ошибка выполнения запроса",
    "sql_agent.no_results": "🔍 Запрос не вернул результатов",
    "sql_agent.prompt": (
        "Вы эксперт по SQL. Сгенерируйте ТОЛЬКО читаемый SQL запрос.\n\n"
        "Схема базы данных:\n{schema}\n\n"
        "КРИТИЧЕСКИЕ ПРАВИЛА:\n"
        "1. ТОЛЬКО SELECT запросы\n"
        "2. ОБЯЗАТЕЛЬНО: WHERE chat_id = {chat_id}\n"
        "3. НИКОГДА не используйте DELETE, UPDATE, INSERT, DROP, ALTER, CREATE\n\n"
        "Вопрос пользователя: {question}\n"
        "Язык ответа: {lang}\n\n"
        "Верните ТОЛЬКО SQL запрос, без объяснений:"
    ),

    # Summary
    "summary.title": "📋 Ежедневная сводка",
    "summary.no_messages": "Сегодня не было новых сообщений",
    "summary.prompt": (
        "Создай краткую сводку обсуждения в чате за последние 24 часа.\n\n"
        "Требования:\n"
        "- 3-5 ключевых тем\n"
        "- Важные решения\n"
        "- Действия, требующие внимания\n\n"
        "Формат: список пунктов с эмодзи для каждого раздела.\n\n"
        "История сообщений:\n{messages}"
    ),
    "summary.custom_prompt": (
        "Создай сводку обсуждения.\n\n"
        "Кастомные инструкции:\n{custom_prompt}\n\n"
        "История сообщений:\n{messages}"
    ),

    # Coach
    "coach.title": "🎓 Анализ коммуникации",
    "coach.prompt": (
        "Проанализируй коммуникацию в чате и дай конструктивную обратную связь.\n\n"
        "Оцени:\n"
        "- Тон общения\n"
        "- Эффективность коммуникации\n"
        "- Потенциальные конфликты\n"
        "- Рекомендации по улучшению\n\n"
        "Формат: 3-5 конкретных наблюдений с рекомендациями.\n\n"
        "История сообщений:\n{messages}"
    ),
    "coach.conflict_prompt": (
        "Проанализируй коммуникацию на наличие потенциальных конфликтов.\n\n"
        "Ищи:\n"
        "- Признаки напряжения в общении\n"
        "- Возможные разногласия\n"
        "- Стиль конфликтного общения\n"
        "- Рекомендации по разрешению\n\n"
        "Формат: 2-4 конкретных наблюдения с рекомендациями.\n\n"
        "История сообщений:\n{messages}"
    ),
    "coach.productivity_prompt": (
        "Проанализируй коммуникацию с точки зрения продуктивности.\n\n"
        "Оцени:\n"
        "- Эффективность обсуждений\n"
        "- Практичность коммуникации\n"
        "- Потерянное время\n"
        "- Рекомендации по улучшению\n\n"
        "Формат: 3-5 конкретных наблюдений с рекомендациями.\n\n"
        "История сообщений:\n{messages}"
    ),

    # Thread summary
    "thread_summary.title": "📝 Сводка обсуждения",
    "thread_summary.prompt": (
        "Создай краткую сводку этого обсуждения в 3-5 пунктах.\n\n"
        "Выдели:\n"
        "- Основную тему\n"
        "- Ключевые аргументы\n"
        "- Достигнутые договорённости\n\n"
        "Обсуждение:\n{messages}"
    ),
    "thread_summary.no_thread": "Ответьте на сообщение, чтобы суммаризировать тред",
    "thread_summary.recent_messages": "Суммаризация последних {count} сообщений",

    # QA
    "qa.prompt": (
        "Ответь на вопрос пользователя на основе контекста чата.\n\n"
        "Контекст (последние {count} сообщений):\n{context}\n\n"
        "Вопрос: {question}\n\n"
        "Ответь кратко и по существу. Если информации недостаточно, так и скажи."
    ),
    "qa.no_context": "Недостаточно контекста для ответа на вопрос",

    # SQL Agent
    "sql_agent.unsafe_query": "⚠️ Небезопасный SQL-запрос заблокирован",
    "sql_agent.query_error": "❌ Ошибка выполнения запроса",
    "sql_agent.no_results": "🔍 Запрос не вернул результатов",
    "sql_agent.generation_error": "Не удалось сгенерировать SQL-запрос",
    "sql_agent.explain_failed": "Не удалось объяснить запрос",
    "sql_agent.schema": (
        "Таблицы:\n"
        "- users(id, username, first_name, last_name, language_code, is_superadmin)\n"
        "- chats(id, title, type, created_at, deleted_at)\n"
        "- chat_members(chat_id, user_id, role, joined_at, left_at)\n"
        "- messages(id, message_id, chat_id, user_id, content, timestamp, is_deleted)\n"
        "- chat_settings(chat_id, summary_enabled, coach_enabled, language)\n"
        "- llm_usage(id, user_id, chat_id, skill, tokens_prompt, tokens_completion, cost_usd, timestamp)\n"
        "- audit_log(id, user_id, chat_id, action, details, timestamp)\n"
    ),
    "sql_agent.system_prompt": (
        "Ты эксперт по SQL. Генерируй ТОЛЬКО SELECT запросы.\n\n"
        "ПРАВИЛА:\n"
        "1. ТОЛЬКО SELECT запросы (никаких DELETE, UPDATE, INSERT)\n"
        "2. ВСЕГДА включай WHERE chat_id = {chat_id} для фильтрации по чату\n"
        "3. Используй LIMIT для ограничения результатов\n"
        "4. Не добавляй объяснений, только SQL\n"
        "5. Используй JOIN для связи таблиц\n\n"
        "Допустимые таблицы: users, chats, chat_members, messages, chat_settings, llm_usage, audit_log"
    ),
    "sql_agent.prompt": (
        "Схема базы данных:\n{schema}\n\n"
        "Вопрос пользователя: {question}\n\n"
        "Чат ID: {chat_id}\n\n"
        "Сгенерируй SQL запрос для ответа на вопрос. "
        "Верни ТОЛЬКО SQL без объяснений."
    ),
    "sql_agent.explain_prompt": (
        "Объясни этот SQL запрос простым языком:\n\n"
        "SQL: {sql}\n\n"
        "Исходный вопрос: {question}\n\n"
        "Кратко объясни, что делает запрос."
    ),
    "sql_agent.format_prompt": (
        "Отформатируй результаты запроса в виде естественного ответа.\n\n"
        "Вопрос: {question}\n"
        "SQL: {sql}\n"
        "Найдено записей: {count}\n\n"
        "Результаты:\n{results}\n\n"
        "Сформулируй краткий и понятный ответ на русском языке."
    ),

    # Settings
    "settings.updated": "⚙️ Настройки обновлены",
    "settings.summary_enabled": "Ежедневная сводка включена",
    "settings.summary_disabled": "Ежедневная сводка отключена",
    "settings.coach_enabled": "AI-коучинг включён",
    "settings.coach_disabled": "AI-коучинг отключён",

    # Export
    "export.started": "📤 Экспорт истории чата начат...",
    "export.completed": "✅ Экспорт завершён: {file_name}",
    "export.error": "❌ Ошибка экспорта",
    "export.empty_chat": "Чат не содержит сообщений",

    # Admin
    "admin.stats": (
        "📊 Глобальная статистика:\n"
        "- Пользователей: {total_users}\n"
        "- Чатов: {total_chats}\n"
        "- Сообщений: {total_messages}\n"
        "- Использовано токенов: {total_tokens}"
    ),
    "admin.notify_sent": "📩 Уведомление отправлено пользователю {user_id}",
    "admin.notify_failed": "❌ Не удалось отправить уведомление",

    # Common
    "common.yes": "Да",
    "common.no": "Нет",
    "common.cancel": "Отмена",
    "common.back": "Назад",
    "common.loading": "Загрузка...",
    "common.done": "Готово",
}


# English translations
EN_TRANSLATIONS = {
    # Bot commands
    "bot.start": (
        "👋 Welcome to Chat Analytics Bot!\n\n"
        "Commands:\n"
        "/stats - Chat statistics\n"
        "/export - Export chat history\n"
        "/summarize_thread - Summarize discussion\n"
        "/help - Show help"
    ),
    "bot.stats": (
        "📊 Chat Statistics:\n"
        "- Total messages: {message_count}\n"
        "- Active members: {member_count}\n"
        "- Messages today: {messages_today}\n"
        "- Last activity: {last_activity}"
    ),
    "bot.help": (
        "Commands:\n"
        "/start - Show welcome message\n"
        "/stats - Chat statistics\n"
        "/export - Export chat as TXT\n"
        "/summarize_thread - Summarize discussion\n"
        "/help - Show this message\n\n"
        "Features:\n"
        "- @{bot} question - Ask question about chat\n"
        "- In personal chat - SQL agent mode to query chat data"
    ),

    # Errors
    "error.access_denied": "🚫 Access denied",
    "error.chat_not_found": "❌ Chat not found",
    "error.invalid_request": "❌ Invalid request",
    "error.rate_limit_exceeded": "⚠️ Rate limit exceeded. Please try again later.",
    "error.encryption_failed": "❌ Encryption failed",
    "error.decryption_failed": "❌ Decryption failed",
    "error.llm_failed": "❌ AI service error",
    "error.database_error": "❌ Database error",

    # SQL Agent
    "sql_agent.unsafe_query": "⚠️ Unsafe SQL query blocked",
    "sql_agent.query_error": "❌ Query execution error",
    "sql_agent.no_results": "🔍 Query returned no results",
    "sql_agent.generation_error": "Failed to generate SQL query",
    "sql_agent.explain_failed": "Failed to explain query",
    "sql_agent.schema": (
        "Tables:\n"
        "- users(id, username, first_name, last_name, language_code, is_superadmin)\n"
        "- chats(id, title, type, created_at, deleted_at)\n"
        "- chat_members(chat_id, user_id, role, joined_at, left_at)\n"
        "- messages(id, message_id, chat_id, user_id, content, timestamp, is_deleted)\n"
        "- chat_settings(chat_id, summary_enabled, coach_enabled, language)\n"
        "- llm_usage(id, user_id, chat_id, skill, tokens_prompt, tokens_completion, cost_usd, timestamp)\n"
        "- audit_log(id, user_id, chat_id, action, details, timestamp)\n"
    ),
    "sql_agent.system_prompt": (
        "You are a SQL expert. Generate ONLY SELECT queries.\n\n"
        "RULES:\n"
        "1. ONLY SELECT queries (no DELETE, UPDATE, INSERT)\n"
        "2. ALWAYS include WHERE chat_id = {chat_id} to filter by chat\n"
        "3. Use LIMIT to limit results\n"
        "4. No explanations, just SQL\n"
        "5. Use JOIN to join tables\n\n"
        "Allowed tables: users, chats, chat_members, messages, chat_settings, llm_usage, audit_log"
    ),
    "sql_agent.prompt": (
        "Database schema:\n{schema}\n\n"
        "User question: {question}\n\n"
        "Chat ID: {chat_id}\n\n"
        "Generate SQL query to answer the question. "
        "Return ONLY SQL without explanations."
    ),
    "sql_agent.explain_prompt": (
        "Explain this SQL query in simple terms:\n\n"
        "SQL: {sql}\n\n"
        "Original question: {question}\n\n"
        "Briefly explain what the query does."
    ),
    "sql_agent.format_prompt": (
        "Format query results as a natural language answer.\n\n"
        "Question: {question}\n"
        "SQL: {sql}\n"
        "Records found: {count}\n\n"
        "Results:\n{results}\n\n"
        "Formulate a concise and clear answer in English."
    ),

    # Summary
    "summary.title": "📋 Daily Summary",
    "summary.no_messages": "No new messages today",
    "summary.prompt": (
        "Create a brief summary of the chat discussion in the last 24 hours.\n\n"
        "Requirements:\n"
        "- 3-5 key topics\n"
        "- Important decisions\n"
        "- Actions requiring attention\n\n"
        "Format: bulleted list with emoji for each section.\n\n"
        "Message history:\n{messages}"
    ),
    "summary.custom_prompt": (
        "Create a discussion summary.\n\n"
        "Custom instructions:\n{custom_prompt}\n\n"
        "Message history:\n{messages}"
    ),

    # Coach
    "coach.title": "🎓 Communication Analysis",
    "coach.prompt": (
        "Analyze the communication in the chat and provide constructive feedback.\n\n"
        "Evaluate:\n"
        "- Communication tone\n"
        "- Communication effectiveness\n"
        "- Potential conflicts\n"
        "- Improvement recommendations\n\n"
        "Format: 3-5 specific observations with recommendations.\n\n"
        "Message history:\n{messages}"
    ),
    "coach.conflict_prompt": (
        "Analyze the communication for potential conflicts.\n\n"
        "Look for:\n"
        "- Signs of tension in communication\n"
        "- Possible disagreements\n"
        "- Conflict communication style\n"
        "- Resolution recommendations\n\n"
        "Format: 2-4 specific observations with recommendations.\n\n"
        "Message history:\n{messages}"
    ),
    "coach.productivity_prompt": (
        "Analyze the communication from a productivity perspective.\n\n"
        "Evaluate:\n"
        "- Discussion effectiveness\n"
        "- Communication practicality\n"
        "- Wasted time\n"
        "- Improvement recommendations\n\n"
        "Format: 3-5 specific observations with recommendations.\n\n"
        "Message history:\n{messages}"
    ),

    # Thread summary
    "thread_summary.title": "📝 Discussion Summary",
    "thread_summary.prompt": (
        "Create a brief summary of this discussion in 3-5 points.\n\n"
        "Highlight:\n"
        "- Main topic\n"
        "- Key arguments\n"
        "- Agreements reached\n\n"
        "Discussion:\n{messages}"
    ),
    "thread_summary.no_thread": "Reply to a message to summarize the thread",
    "thread_summary.recent_messages": "Summarizing last {count} messages",

    # QA
    "qa.prompt": (
        "Answer the user's question based on chat context.\n\n"
        "Context (last {count} messages):\n{context}\n\n"
        "Question: {question}\n\n"
        "Answer briefly and to the point. If there's not enough information, say so."
    ),
    "qa.no_context": "Not enough context to answer the question",

    # Settings
    "settings.updated": "⚙️ Settings updated",
    "settings.summary_enabled": "Daily summary enabled",
    "settings.summary_disabled": "Daily summary disabled",
    "settings.coach_enabled": "AI coaching enabled",
    "settings.coach_disabled": "AI coaching disabled",

    # Export
    "export.started": "📤 Chat export started...",
    "export.completed": "✅ Export completed: {file_name}",
    "export.error": "❌ Export error",
    "export.empty_chat": "Chat contains no messages",

    # Admin
    "admin.stats": (
        "📊 Global Statistics:\n"
        "- Users: {total_users}\n"
        "- Chats: {total_chats}\n"
        "- Messages: {total_messages}\n"
        "- Tokens used: {total_tokens}"
    ),
    "admin.notify_sent": "📩 Notification sent to user {user_id}",
    "admin.notify_failed": "❌ Failed to send notification",

    # Common
    "common.yes": "Yes",
    "common.no": "No",
    "common.cancel": "Cancel",
    "common.back": "Back",
    "common.loading": "Loading...",
    "common.done": "Done",
}


# Available languages
LANGUAGES: Dict[str, TranslationSet] = {
    "ru": TranslationSet(
        code="ru",
        name="Русский",
        flag="🇷🇺",
        translations=RU_TRANSLATIONS
    ),
    "en": TranslationSet(
        code="en",
        name="English",
        flag="🇬🇧",
        translations=EN_TRANSLATIONS
    ),
}


def get_text(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Get translated text by key.

    Args:
        key: Translation key (supports dot notation, e.g., 'error.access_denied')
        lang: Language code ('ru' or 'en')
        **kwargs: Optional formatting arguments

    Returns:
        Translated string, or the key itself if not found

    Example:
        >>> get_text("error.access_denied", lang="ru")
        "🚫 Доступ запрещён"
        >>> get_text("bot.stats", lang="en", message_count=100)
        "📊 Chat Statistics:\\n- Total messages: 100..."
    """
    translation_set = LANGUAGES.get(lang, LANGUAGES["ru"])
    return translation_set.get(key, **kwargs)


def get_available_languages() -> Dict[str, TranslationSet]:
    """
    Get all available languages.

    Returns:
        Dictionary mapping language codes to TranslationSet objects
    """
    return LANGUAGES.copy()


def get_language_info(lang: str) -> Optional[TranslationSet]:
    """
    Get information about a specific language.

    Args:
        lang: Language code

    Returns:
        TranslationSet if language exists, None otherwise
    """
    return LANGUAGES.get(lang)


def is_supported_language(lang: str) -> bool:
    """
    Check if a language is supported.

    Args:
        lang: Language code

    Returns:
        True if supported, False otherwise
    """
    return lang in LANGUAGES


def get_translation_keys(lang: str = "ru") -> list:
    """
    Get all available translation keys for a language.

    Args:
        lang: Language code

    Returns:
        List of translation keys
    """
    translation_set = LANGUAGES.get(lang, LANGUAGES["ru"])
    return list(translation_set.translations.keys())


# Convenience functions for common translations
def t(key: str, **kwargs) -> str:
    """Shorthand for get_text with default language"""
    return get_text(key, lang="ru", **kwargs)


def t_en(key: str, **kwargs) -> str:
    """Shorthand for get_text with English language"""
    return get_text(key, lang="en", **kwargs)
