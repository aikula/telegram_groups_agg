"""
LLM Prompts - Prompt templates for various LLM operations
"""

from typing import List, Dict, Optional


# QA Prompt - for answering questions in chat
QA_PROMPT = """You are a helpful assistant in a group chat. Answer the user's question based on the chat context provided below.

Chat context (recent messages):
{context}

User's question: {question}

Provide a helpful, concise answer. If the context doesn't contain enough information to answer the question, say so. Keep your response friendly and professional.

Answer:"""

# Russian version of QA prompt
QA_PROMPT_RU = """Ты полезный ассистент в групповом чате. Ответь на вопрос пользователя на основе контекста чата.

Контекст чата (последние сообщения):
{context}

Вопрос пользователя: {question}

Дай полезный и лаконичный ответ. Если в контексте недостаточно информации для ответа, так и скажи. Будь дружелюбным и профессиональным.

Ответ:"""


# Summary Prompt - for generating daily summaries
SUMMARY_PROMPT = """You are a chat analyst. Analyze the messages from the past day and create a concise summary.

Messages from the chat:
{messages}

Create a summary that includes:
1. **Main topics discussed** - What were the primary themes?
2. **Key decisions made** - What decisions or agreements were reached?
3. **Active participants** - Who were the most active contributors?
4. **Action items** (if any) - What tasks or next steps were mentioned?

Format your response using Markdown. Keep it concise and focused.

Summary:"""

# Russian version of Summary prompt
SUMMARY_PROMPT_RU = """Ты аналитик чата. Проанализируй сообщения за прошедший день и создай краткую сводку.

Сообщения из чата:
{messages}

Создай сводку, которая включает:
1. **Основные темы обсуждения** - О чем преимущественно говорили?
2. **Ключевые решения** - Какие решения или договоренности были достигнуты?
3. **Активные участники** - Кто был наиболее активен?
4. **Пункты действий** (если есть) - Какие задачи или следующие шаги были упомянуты?

Оформи ответ в формате Markdown. Будь лаконичным и по существу.

Сводка:"""


# Coaching Recommendations Prompt
COACHING_PROMPT = """You are a communication coach analyzing a group chat. Review the messages and provide constructive feedback.

Messages from the chat:
{messages}

Provide coaching recommendations on:
1. **Communication tone** - Is the tone professional and constructive?
2. **Participation balance** - Is everyone contributing appropriately?
3. **Conflict resolution** - How well are disagreements handled?
4. **Collaboration quality** - How well is the team working together?
5. **Specific suggestions** - What specific improvements could be made?

Be constructive and supportive. Focus on actionable advice.

Recommendations:"""

# Russian version of Coaching prompt
COACHING_PROMPT_RU = """Ты коуч по коммуникации, анализирующий групповой чат. Просмотри сообщения и дай конструктивную обратную связь.

Сообщения из чата:
{messages}

Дай рекомендации по:
1. **Тон коммуникации** - Тон профессиональный и конструктивный?
2. **Баланс участия** - Все ли вносят соответствующий вклад?
3. **Разрешение конфликтов** - Как хорошо обрабатываются разногласия?
4. **Качество сотрудничества** - Как хорошо команда работает вместе?
5. **Конкретные предложения** - Какие конкретные улучшения можно сделать?

Будь конструктивным и поддерживающим. Сосредоточься на практических советах.

Рекомендации:"""


# Welcome message prompt
WELCOME_MESSAGE = """👋 Привет! Я добавлен в этот чат для аналитики.

Я буду:
- 📝 Сохранять историю сообщений
- 💬 Отвечать на вопросы (упомяни @bot)
- 📊 Присылать ежедневные сводки в 16:00 МСК
- 💡 Давать рекомендации по коммуникации

Для вопросов упомяни меня в сообщении: @{bot_username} вопрос"""


def format_qa_context(messages: List[Dict], question: str, language: str = "ru") -> str:
    """
    Format the QA prompt with context and question.

    Args:
        messages: List of message dictionaries for context
        question: User's question
        language: Language code ('ru' or 'en')

    Returns:
        Formatted prompt string
    """
    context = _format_messages_context(messages)

    template = QA_PROMPT_RU if language == "ru" else QA_PROMPT
    return template.format(context=context, question=question)


def format_summary_prompt(messages: List[Dict], language: str = "ru") -> str:
    """
    Format the summary prompt with messages.

    Args:
        messages: List of message dictionaries
        language: Language code ('ru' or 'en')

    Returns:
        Formatted prompt string
    """
    messages_text = _format_messages_context(messages)

    template = SUMMARY_PROMPT_RU if language == "ru" else SUMMARY_PROMPT
    return template.format(messages=messages_text)


def format_coaching_prompt(messages: List[Dict], language: str = "ru") -> str:
    """
    Format the coaching prompt with messages.

    Args:
        messages: List of message dictionaries
        language: Language code ('ru' or 'en')

    Returns:
        Formatted prompt string
    """
    messages_text = _format_messages_context(messages)

    template = COACHING_PROMPT_RU if language == "ru" else COACHING_PROMPT
    return template.format(messages=messages_text)


def _format_messages_context(messages: List[Dict]) -> str:
    """
    Format a list of messages into a readable context string.

    Args:
        messages: List of message dictionaries

    Returns:
        Formatted context string
    """
    if not messages:
        return "Нет сообщений."

    lines = []
    for msg in messages:
        username = msg.get('username') or msg.get('first_name', 'Unknown')
        text = msg.get('message_text', '') or '[медиа/файл]'
        timestamp = msg.get('timestamp', '')

        if isinstance(timestamp, str):
            timestamp_str = timestamp[:16] if len(timestamp) > 16 else timestamp
        else:
            timestamp_str = str(timestamp)[:16]

        lines.append(f"{timestamp_str} | {username}: {text}")

    return "\n".join(lines)


def get_welcome_message(bot_username: str) -> str:
    """
    Get the welcome message for when bot joins a chat.

    Args:
        bot_username: Bot's username

    Returns:
        Welcome message string
    """
    return WELCOME_MESSAGE.format(bot_username=bot_username)


def format_statistics_summary(stats: Dict) -> str:
    """
    Format statistics into a readable summary.

    Args:
        stats: Statistics dictionary with keys like total_messages, active_users, etc.

    Returns:
        Formatted statistics string
    """
    lines = [
        "📊 *Статистика чата*",
        "",
        f"📝 Всего сообщений: {stats.get('total_messages', 0)}",
        f"👥 Активных участников: {stats.get('active_users', 0)}",
        f"📅 Период: последние {stats.get('days', 7)} дней",
        f"💬 Среднее сообщений/день: {stats.get('avg_per_day', 0):.1f}",
    ]

    # Top contributors if available
    if stats.get('top_contributors'):
        lines.append("")
        lines.append("*🏆 Самые активные:*")
        for user, count in stats['top_contributors'][:5]:
            lines.append(f"  • {user}: {count} сообщений")

    # Most active hour if available
    if stats.get('most_active_hour'):
        lines.append("")
        lines.append(f"⏰ Пик активности: {stats['most_active_hour']}:00")

    return "\n".join(lines)


# System prompts for different modes
SYSTEM_PROMPTS = {
    "qa": "You are a helpful chat assistant. Answer questions based on chat context.",
    "qa_ru": "Ты полезный ассистент чата. Отвечай на вопросы основываясь на контексте чата.",
    "analyst": "You are a chat analyst. Provide objective summaries of group discussions.",
    "analyst_ru": "Ты аналитик чата. Предоставляй объективные сводки групповых обсуждений.",
    "coach": "You are a communication coach. Provide constructive feedback on group dynamics.",
    "coach_ru": "Ты коуч по коммуникации. Давай конструктивную обратную связь о групповой динамике.",
}


def get_system_prompt(mode: str = "analyst_ru") -> str:
    """
    Get a system prompt for the specified mode.

    Args:
        mode: Prompt mode (qa, qa_ru, analyst, analyst_ru, coach, coach_ru)

    Returns:
        System prompt string
    """
    return SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["analyst_ru"])
