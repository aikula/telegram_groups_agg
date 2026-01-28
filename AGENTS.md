# AGENTS.md

**Версия:** 2.0  
**Дата:** 2026-01-28  
**Назначение:** Руководство по разработке AI-агентов, Skills и Tools

---

## 1. Введение в Agentic Architecture

Наша система использует **трехуровневую агентную архитектуру**, основанную на best practices от Anthropic:

```
┌────────────────────────────────────┐
│   Level 1: Router Agent            │
│   Задача: Классификация запроса    │
│   Выход: Выбор Skill                │
└────────────────┬───────────────────┘
                 │
┌────────────────▼───────────────────┐
│   Level 2: Skill Agent             │
│   Задача: Исполнение навыка        │
│   Выход: Вызовы Tools               │
└────────────────┬───────────────────┘
                 │
┌────────────────▼───────────────────┐
│   Level 3: Tools Execution         │
│   Задача: Низкоуровневые операции  │
│   Выход: Данные для агента          │
└────────────────────────────────────┘
```

### Почему именно эта архитектура?

1. **Разделение ответственности:** Каждый уровень решает свою задачу
2. **Тестируемость:** Skills и Tools можно тестировать изолированно
3. **Расширяемость:** Добавление нового Skill не влияет на Router
4. **Безопасность:** Tools контролируют доступ к данным
5. **Экономия токенов:** Router использует минимальный промпт

---

## 2. Router Agent

### 2.1 Назначение

**Router Agent** - это легковесный классификатор, который определяет **намерение пользователя** и выбирает подходящий **Skill**.

### 2.2 Принцип работы

```python
# Входные данные
user_query = "Сколько сообщений написал Витя вчера?"

# Router анализирует запрос
skill = router.route(user_query, chat_id)
# skill = "analytics"

# Skill выполняется
result = skill_agent.execute(skill, user_query)
```

### 2.3 Реализация Router Agent

Файл: `app/core/router.py`

Ключевые методы:
- `route(query, chat_id)` - выбор Skill
- `_build_router_prompt()` - формирование промпта
- `_get_available_skills()` - проверка enabled skills

**Пример кода:**

```python
class RouterAgent:
    def __init__(self, llm_client, database):
        self.llm = llm_client
        self.db = database

    async def route(self, user_query: str, chat_id: int) -> str:
        # Получаем enabled skills для чата
        enabled = await self.db.get_enabled_skills(chat_id)

        # Формируем промпт
        prompt = self._build_prompt(user_query, enabled)

        # LLM выбирает skill
        response = await self.llm.chat(prompt, temperature=0.1)

        skill_name = response.strip().lower()

        # Fallback на QA если skill не найден
        if skill_name not in enabled:
            return "qa"

        return skill_name
```

**Router Prompt Template:**

```
You are a routing agent.
User query: "{query}"

Available skills:
- summary: Create summaries
- coach: Communication advice
- qa: Answer questions
- analytics: Statistics

Return ONE skill name only.
```

### 2.4 Best Practices для Router

✅ **DO:**
- Минимальный промпт (50-100 токенов)
- Температура 0.1 для стабильности
- Всегда имейте fallback
- Проверяйте enabled_skills

❌ **DON'T:**
- Не передавайте весь контекст
- Не делайте Router сложным
- Не забывайте валидацию

---

## 3. Skills System

### 3.1 Что такое Skill?

**Skill (Навык)** - это специализированный агент со своим:
1. **System Prompt** - инструкция для LLM
2. **Allowed Tools** - список доступных инструментов
3. **Output Format** - формат ответа (text/markdown/json)
4. **Parameters** - настройки (температура, макс токены)

### 3.2 Структура Skill

```python
class MySkill:
    name = "my_skill"
    system_prompt = "..."
    allowed_tools = ["tool1", "tool2"]
    output_format = "text"
    temperature = 0.7
```

### 3.3 Пример: QA Skill

**Назначение:** Отвечает на вопросы с контекстом чата.

**Allowed Tools:**
- `get_chat_history()` - последние сообщения
- `sql_analytics()` - статистика
- `general_answer()` - общие знания LLM

**System Prompt:**

```
You are a chat assistant.

Tools available:
1. get_chat_history(limit, days) - retrieve messages
2. sql_analytics(query) - execute SELECT queries
3. general_answer() - use your knowledge

Instructions:
- For chat history questions → use get_chat_history()
- For statistics → use sql_analytics()
- For general questions → use general_answer()
- Cite sources (usernames, dates)
- Be concise

Current context:
- Chat ID: {chat_id}
- User: {username}
- Date: {date}
```

**Пример кода:**

Файл: `app/skills/qa.py`

```python
from app.skills.base import BaseSkill

class QASkill(BaseSkill):
    def __init__(self):
        self.name = "qa"
        self.allowed_tools = [
            "get_chat_history",
            "sql_analytics", 
            "general_answer"
        ]
        self.output_format = "text"
        self.temperature = 0.7

    def get_system_prompt(self, context):
        return f"""You are a helpful assistant.

Chat ID: {context['chat_id']}
User: {context['username']}

Use tools to answer questions accurately."""

    async def format_output(self, text):
        # Обрезаем для Telegram
        if len(text) > 4000:
            return text[:3950] + "... (обрезано)"
        return text
```

---

### 3.4 Пример: Summary Skill

**Назначение:** Создание сводок чата за период.

**System Prompt:**

```
You are a summarization expert.

Task: Create structured summary of chat activity.

Tools:
- get_chat_history(days) - get messages
- sql_analytics(query) - get stats

Output format (Markdown):

## 📊 Период
{start} - {end}

## 🔥 Основные темы
1. Тема 1 (N сообщений)
   - Описание

## ✅ Решения
- Решение 1 (@user, date)

## 💬 Активные участники
1. @user1 - N msgs
2. @user2 - M msgs

## ❓ Открытые вопросы
- Вопрос 1

Rules:
- Use Russian
- Include dates and usernames
- Be concise
```

Файл: `app/skills/summary.py`

---

### 3.5 Пример: Analytics Skill

**Назначение:** SQL-запросы через natural language.

**Allowed Tools:**
- `sql_analytics()` только

**System Prompt:**

```
You are a data analyst.

Database schema:
- users (id, username, full_name)
- messages (chat_id, user_id, timestamp)

Task:
1. Translate question to SQL
2. Call sql_analytics(query)
3. Format results

CRITICAL: Always filter by chat_id = {chat_id}

Examples:
Q: "How many messages from @user?"
SQL: SELECT COUNT(*) FROM messages m
     JOIN users u ON m.user_id = u.id
     WHERE m.chat_id = {chat_id}
     AND u.username = 'user'

Q: "Top 5 active users"
SQL: SELECT u.username, COUNT(*) as cnt
     FROM messages m
     JOIN users u ON m.user_id = u.id
     WHERE m.chat_id = {chat_id}
     GROUP BY u.id
     ORDER BY cnt DESC
     LIMIT 5
```

Файл: `app/skills/analytics.py`

---

### 3.6 Пример: Coach Skill

**Назначение:** Анализ коммуникации и рекомендации.

**System Prompt:**

```
You are a team communication coach.

Task:
1. Analyze chat messages
2. Evaluate tone, constructiveness
3. Provide 3-5 recommendations

Format:
✅ Positive observations
⚠️ Areas to improve
💡 Recommendations:
1. ...
2. ...

Be constructive and friendly.
```

---

## 4. Tools Layer

### 4.1 Что такое Tool?

**Tool** - атомарная функция для выполнения конкретной задачи:
- Четкий input/output
- Одна ответственность
- Безопасность (валидация, rate limiting)
- Тестируемость

### 4.2 Tool Definition Format

Используем стандарт OpenAI Function Calling:

```python
{
    "type": "function",
    "function": {
        "name": "get_chat_history",
        "description": "Retrieve recent messages",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max messages (default 20)",
                    "default": 20
                },
                "days": {
                    "type": "integer", 
                    "description": "Last N days (default 7)",
                    "default": 7
                }
            }
        }
    }
}
```

### 4.3 Tool: get_chat_history()

**Назначение:** Получить последние сообщения с информацией о пользователях.

**Параметры:**
- `chat_id` (int) - ID чата
- `limit` (int) - макс. сообщений (default: 20, max: 100)
- `days` (int) - за последние N дней (default: 7)

**Возвращает:**

```json
{
    "messages": [
        {
            "timestamp": "2026-01-28 09:15",
            "user_id": 123,
            "username": "@vitya",
            "full_name": "Виктор",
            "content": "Текст сообщения"
        }
    ],
    "count": 15
}
```

**Код:**

Файл: `app/core/tools.py`

```python
async def get_chat_history(
    chat_id: int,
    limit: int = 20,
    days: int = 7
) -> dict:
    # Валидация
    limit = min(limit, 100)
    days = min(days, 365)

    # Получаем из БД
    since = datetime.now() - timedelta(days=days)
    messages = await db.get_messages(chat_id, since, limit)

    # Расшифровываем и добавляем user info
    result = []
    for msg in messages:
        user = await db.get_user(msg.user_id)
        result.append({
            "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M"),
            "user_id": msg.user_id,
            "username": user.username,
            "full_name": user.full_name,
            "content": crypto.decrypt(chat_id, msg.content_encrypted)
        })

    return {"messages": result, "count": len(result)}
```

---

### 4.4 Tool: sql_analytics()

**Назначение:** Безопасное выполнение SELECT запросов.

**Security Checks:**
1. Только SELECT
2. Обязательный `WHERE chat_id = X`
3. Нет запрещенных слов (DROP, DELETE, etc)
4. Нет `;` или `--`
5. Read-only connection

**Параметры:**
- `chat_id` (int)
- `query` (str) - SQL запрос

**Код:**

```python
async def sql_analytics(chat_id: int, query: str) -> dict:
    # Security check
    if not is_safe_query(query, chat_id):
        return {
            "error": "Unsafe query",
            "details": "Must be SELECT with chat_id filter"
        }

    try:
        async with db.read_only_connection() as conn:
            cursor = await conn.execute(query)
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description]

            data = [dict(zip(columns, row)) for row in rows]

            # Audit log
            await db.audit_log(
                action="sql_query",
                chat_id=chat_id,
                details={"query": query, "rows": len(data)}
            )

            return {
                "columns": columns,
                "data": data,
                "count": len(data)
            }
    except Exception as e:
        return {"error": str(e)}


def is_safe_query(query: str, chat_id: int) -> bool:
    q = query.upper().strip()

    FORBIDDEN = ["DELETE", "DROP", "UPDATE", "INSERT", 
                 "ALTER", "CREATE", "PRAGMA"]

    # 1. Только SELECT
    if not q.startswith("SELECT"):
        return False

    # 2. Нет запрещенных слов
    if any(kw in q for kw in FORBIDDEN):
        return False

    # 3. Обязательный chat_id filter
    if f"chat_id = {chat_id}" not in query.replace(" ", ""):
        return False

    # 4. Нет injection паттернов
    if ";" in query or "--" in query:
        return False

    return True
```

---

### 4.5 Tool: general_answer()

**Назначение:** Ответ LLM без доступа к БД.

**Параметры:** нет

**Возвращает:**

```json
{
    "message": "Use general knowledge"
}
```

Это placeholder - LLM просто использует свои знания.

---

## 5. Skill Agent Executor

### 5.1 Класс SkillAgent

**Назначение:** Выполнение Skills с поддержкой tool calling.

Файл: `app/core/agent.py`

```python
class SkillAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def execute(
        self,
        skill: BaseSkill,
        query: str,
        chat_id: int,
        user_id: int
    ) -> str:
        # 1. Подготовка контекста
        context = await skill.prepare_context(
            query, chat_id, user_id
        )

        # 2. System prompt
        system_prompt = skill.get_system_prompt(context)

        # 3. Messages для LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # 4. Tool definitions
        tools = skill.get_tool_definitions()

        # 5. LLM с tool calling
        raw_output = await self.llm.chat_with_tools(
            messages=messages,
            tools=tools,
            chat_id=chat_id,
            temperature=skill.temperature
        )

        # 6. Форматирование
        formatted = await skill.format_output(raw_output)

        # 7. Логирование
        await self._log_usage(skill, query, chat_id, user_id)

        return formatted
```

### 5.2 Tool Calling Flow

```
1. LLM получает messages + tool definitions
   ↓
2. LLM решает: нужно ли вызвать tool?
   ↓
3a. Если НЕТ → возвращает финальный ответ
3b. Если ДА → возвращает tool_call
   ↓
4. Backend выполняет tool_call
   ↓
5. Результат добавляется в messages
   ↓
6. Goto step 1 (max 5 итераций)
```

---

## 6. Integration с Aiogram

### 6.1 Bot Handler

Файл: `app/bot/handlers.py`

```python
from aiogram import Router, F
from aiogram.types import Message
from app.core.router import RouterAgent
from app.core.agent import SkillAgent
from app.skills import get_skill

router = Router()

@router.message(F.text.regexp(r"@bot"))
async def handle_mention(message: Message):
    # Извлекаем запрос
    query = message.text.replace("@bot", "").strip()

    # 1. Router выбирает skill
    router_agent = RouterAgent(llm, db)
    skill_name = await router_agent.route(
        query, message.chat.id
    )

    # 2. Загружаем skill
    skill = get_skill(skill_name)

    # 3. Выполняем
    agent = SkillAgent(llm)
    response = await agent.execute(
        skill, query,
        message.chat.id,
        message.from_user.id
    )

    # 4. Отправляем
    parse_mode = "Markdown" if skill.output_format == "markdown" else None
    await message.reply(response, parse_mode=parse_mode)
```

### 6.2 Scheduled Summary

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=16, minute=0)
async def daily_summary():
    # Получаем все чаты с enabled summary
    chats = await db.get_chats_with_summary_enabled()

    for chat in chats:
        # Выполняем summary skill
        skill = get_skill("summary")
        agent = SkillAgent(llm)

        summary = await agent.execute(
            skill,
            query="Создай сводку за день",
            chat_id=chat.id,
            user_id=None  # System
        )

        # Отправляем в чат
        await bot.send_message(
            chat_id=chat.id,
            text=summary,
            parse_mode="Markdown"
        )
```

---

## 7. Best Practices

### 7.1 Для Skills

✅ **DO:**
- Специализация (один навык = одна задача)
- Четкие system prompts с примерами
- Явный output format
- Валидация параметров
- Логирование LLM usage

❌ **DON'T:**
- Универсальные skills
- Смешение задач
- Превышение Telegram лимитов
- Избыточный контекст

### 7.2 Для Tools

✅ **DO:**
- Атомарность (одна функция = одна задача)
- Type hints
- Error handling
- Input validation
- Audit logging
- Rate limiting

❌ **DON'T:**
- "Swiss army knife" tools
- Игнорирование security
- Забывать про permissions

### 7.3 Security Checklist

Перед production:

- [ ] Валидация всех inputs
- [ ] Rate limiting настроен
- [ ] SQL injection защита
- [ ] Audit logging
- [ ] Unit tests написаны
- [ ] Integration tests
- [ ] Code review

---

## 8. Testing

### 8.1 Unit Tests для Skills

```python
# tests/test_skills.py
import pytest
from app.skills.qa import QASkill

@pytest.mark.asyncio
async def test_qa_skill_output_truncation():
    skill = QASkill()

    long_text = "A" * 5000
    formatted = await skill.format_output(long_text)

    assert len(formatted) <= 4000
    assert "обрезано" in formatted
```

### 8.2 Integration Tests

```python
# tests/test_integration.py
import pytest
from app.core.router import RouterAgent
from app.core.agent import SkillAgent

@pytest.mark.asyncio
async def test_full_qa_flow():
    # Router выбирает skill
    router = RouterAgent(llm, db)
    skill_name = await router.route(
        "Сколько сообщений у Вити?",
        chat_id=123
    )

    assert skill_name == "analytics"

    # Skill выполняется
    skill = get_skill(skill_name)
    agent = SkillAgent(llm)

    result = await agent.execute(
        skill, "Сколько сообщений у Вити?",
        chat_id=123, user_id=456
    )

    assert result is not None
    assert len(result) > 0
```

---

## 9. Monitoring & Debugging

### 9.1 Логирование

```python
import logging

logger = logging.getLogger(__name__)

# В Router
logger.info(f"Routing query to skill: {skill_name}")

# В SkillAgent
logger.debug(f"Executing {skill.name} with {len(tools)} tools")

# В Tools
logger.info(f"SQL query executed: {query[:100]}")
```

### 9.2 Metrics

Отслеживаем:
- Частота использования Skills
- Средние токены на запрос
- Время выполнения
- Error rate

```python
# В llm_usage таблице
await db.log_llm_usage(
    user_id=user_id,
    chat_id=chat_id,
    skill=skill_name,
    model=model_name,
    tokens_prompt=tokens_in,
    tokens_completion=tokens_out,
    cost_usd=cost
)
```

---

## 10. Troubleshooting

### Частые проблемы

**1. Router выбирает неправильный Skill**
- Решение: Улучшить Router prompt
- Добавить примеры в промпт
- Снизить температуру до 0.0

**2. Tool не вызывается**
- Проверить tool definition format
- Убедиться, что tool в allowed_tools
- Проверить LLM модель (поддержка tool calling)

**3. Превышен Telegram лимит (4000 символов)**
- Добавить truncation в format_output()
- Разбить на несколько сообщений

**4. SQL injection блокирует запрос**
- Проверить is_safe_query()
- Убедиться в наличии WHERE chat_id

---

## 11. Roadmap

### v2.1
- Multi-turn conversations
- Streaming responses
- Cost optimization (caching)

### v2.2
- Custom skills per chat
- Skill marketplace
- A/B testing промптов

### v3.0
- Multi-modal skills (images)
- Voice skills (Whisper)
- Autonomous agents

---

## 12. Заключение

Следуйте этой архитектуре для:

✅ **Модульности** - легко добавлять Skills  
✅ **Безопасности** - контроль через Tools  
✅ **Тестируемости** - изолированные тесты  
✅ **Масштабируемости** - независимая оптимизация  
✅ **Поддерживаемости** - четкая структура  

---

**Версия:** 2.0 | **Дата:** 2026-01-28
