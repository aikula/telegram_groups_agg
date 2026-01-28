# TECHNICAL_SPEC.md

**Версия:** 2.0  
**Дата:** 2026-01-27  
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0  
**Статус:** Production Ready with Agentic Architecture

---

## 1. Обзор проекта

**Telegram Chat Analytics & Coaching Bot** — корпоративный self-hosted бот с AI-агентной архитектурой для аналитики и улучшения коммуникации в командных чатах.

### Ключевые возможности

- 🤖 **Agentic AI Architecture** — Router Agent + Skills + Tools
- 💬 **Умный чат-бот** — Понимает контекст, вызывает нужные инструменты
- 📊 **Аналитика** — SQL-запросы через natural language
- 📝 **Автоматические сводки** — Ежедневные summary с рекомендациями коуча
- 🔐 **Telegram-native 2FA** — Вход по Telegram ID + OTP код
- 🎛️ **Per-chat Skills** — Админы могут включать/выключать навыки
- 🔒 **Шифрование** — Per-chat AES-256 шифрование сообщений
- 🌐 **Web Dashboard** — FastAPI + современный UI

---

## 2. Архитектура системы

### 2.1 High-Level Architecture

```
User (Telegram)
      ↓
Aiogram 3.x Bot (Polling)
  • Message Handler
  • Command Handler
  • Middleware
      ↓
Router Agent
  (Выбор Skill)
      ↓
Skill Agent
  • Summary
  • Coach
  • QA
  • Analytics
      ↓
Tools Layer
  • sql_analytics()
  • get_chat_history()
  • general_answer()
      ↓
SQLite Database
```

---

### 2.2 Agentic Workflow

#### Этап 1: Router Agent

**Задача:** Понять намерение пользователя и выбрать подходящий Skill.

**Пример:**
```
User: "@bot сколько сообщений написал Витя вчера?"
Router → Analytics Skill
```

**Промпт:**
```
You are a routing agent.
User query: {query}

Available Skills:
- summary: Daily/weekly summaries
- coach: Communication recommendations
- qa: Answer questions with context
- analytics: SQL-based statistics

Choose ONE skill. Return only the skill name.
```

**Реализация:**
```python
class RouterAgent:
    async def route(self, query: str, chat_id: int) -> str:
        prompt = self._build_router_prompt(query)
        response = await llm_client.chat(prompt)
        skill_name = response.strip().lower()

        if not await db.is_skill_enabled(chat_id, skill_name):
            return "qa"

        return skill_name
```

---

#### Этап 2: Skill Agent

**Skill = System Prompt + Allowed Tools + Output Format**

**Пример: Analytics Skill**

```python
class AnalyticsSkill(BaseSkill):
    name = "analytics"

    system_prompt = '''
    You are an analytics assistant.

    Task:
    1. Use sql_analytics() to query database
    2. Answer with data
    3. Format numbers clearly

    Database:
    - users (id, username, full_name)
    - messages (chat_id, user_id, timestamp)

    ALWAYS filter by chat_id = {chat_id}
    '''

    allowed_tools = ["sql_analytics", "get_chat_history"]
    output_format = "text"
```

---

#### Этап 3: Tools Execution

```python
# app/core/tools.py

async def sql_analytics(query: str, chat_id: int) -> dict:
    # Execute safe SELECT query
    if not _is_safe_query(query, chat_id):
        raise SecurityError("Unsafe SQL")

    async with db.read_only_connection() as conn:
        result = await conn.execute(query)
        return {"rows": await result.fetchall()}


async def get_chat_history(chat_id: int, limit: int = 20) -> dict:
    # Get recent messages with user info
    messages = await db.get_recent_messages(chat_id, limit)

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

    return {"messages": result}
```

---

### 2.3 Skills System

**Available Skills:**

#### 1. Summary Skill

```python
class SummarySkill(BaseSkill):
    name = "summary"

    system_prompt = '''
    You are a chat summarization assistant.

    Task:
    1. Use get_chat_history() to retrieve messages
    2. Group by topics
    3. Highlight key participants
    4. Format as Markdown

    Structure:
    ## Основные темы
    - Topic 1
    - Topic 2

    ## Ключевые решения
    - Decision 1

    ## Активные участники
    - @username (N messages)
    '''

    allowed_tools = ["get_chat_history", "sql_analytics"]
    output_format = "markdown"
```

#### 2. Coach Skill

```python
class CoachSkill(BaseSkill):
    name = "coach"

    system_prompt = '''
    You are a team communication coach.

    Task:
    1. Analyze communication patterns
    2. Evaluate tone, constructiveness
    3. Provide 3-5 recommendations

    Format:
    ✅ Positive: ...
    ⚠️ To improve: ...
    💡 Recommendations:
    1. ...
    '''

    allowed_tools = ["get_chat_history"]
    output_format = "text"
```

#### 3. QA Skill

```python
class QASkill(BaseSkill):
    name = "qa"

    system_prompt = '''
    You are a helpful chat assistant.

    Task:
    1. Answer questions about chat
    2. Use get_chat_history() for context
    3. Use sql_analytics() for stats
    4. Cite sources (usernames, dates)

    Be concise and accurate.
    '''

    allowed_tools = ["get_chat_history", "sql_analytics", "general_answer"]
    output_format = "text"
```

---

### 2.4 Per-Chat Skills Management

**Chat Settings:**

```sql
CREATE TABLE chat_settings (
    chat_id INTEGER PRIMARY KEY,
    enabled_skills TEXT DEFAULT '["summary","coach","qa","analytics"]',
    summary_time TEXT DEFAULT '16:00',
    summary_timezone TEXT DEFAULT 'Europe/Moscow',
    language TEXT DEFAULT 'ru'
);
```

**Commands:**

```
/skills list              - Показать навыки
/skills enable summary    - Включить навык
/skills disable analytics - Выключить навык
```

---

## 3. Аутентификация (Telegram-native 2FA)

### 3.1 Алгоритм входа

```
Web UI: "Ваш Telegram ID"
         ↓
Backend: Генерирует OTP (6 цифр)
         ↓
Telegram: "🔐 Код: 123456"
         ↓
Web UI: "Введите код"
         ↓
Backend: Проверяет → Выдает JWT
```

### 3.2 Реализация

```python
# app/web/auth.py
import secrets
from datetime import datetime, timedelta

otp_cache: dict[int, tuple[str, datetime]] = {}

async def request_otp(telegram_id: int) -> bool:
    # Check if user is admin
    user = await db.get_user(telegram_id)
    if not user or not user.is_web_admin:
        return False

    # Generate OTP
    otp = str(secrets.randbelow(1000000)).zfill(6)
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    otp_cache[telegram_id] = (otp, expires_at)

    # Send via Telegram
    await bot.send_message(
        chat_id=telegram_id,
        text=f"🔐 Код для входа: {otp}\nДействителен 5 минут."
    )

    return True


async def verify_otp(telegram_id: int, otp: str) -> str | None:
    if telegram_id not in otp_cache:
        return None

    stored_otp, expires_at = otp_cache[telegram_id]

    if datetime.utcnow() > expires_at:
        del otp_cache[telegram_id]
        return None

    if otp != stored_otp:
        return None

    del otp_cache[telegram_id]

    user = await db.get_user(telegram_id)
    token = create_jwt_token(user)

    return token
```

---

## 4. База данных

### 4.1 Нормализация

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    language_code TEXT DEFAULT 'ru',
    is_web_admin BOOLEAN DEFAULT 0,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT,
    timestamp TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT 0,
    FOREIGN KEY(chat_id) REFERENCES chats(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    UNIQUE(chat_id, message_id)
);

CREATE INDEX idx_messages_user_time ON messages(user_id, timestamp);
CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
```

**Middleware синхронизации:**

```python
class UserSyncMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user

        await db.upsert_user(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            last_seen=datetime.utcnow()
        )

        return await handler(event, data)
```

---

### 4.2 LLM Usage Tracking

```sql
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    skill TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    cost_usd REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 4.3 Audit Log

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    chat_id INTEGER,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. LLM Integration

### 5.1 Model: DeepSeek V3

**Выбор:**
- **Основная:** `deepseek/deepseek-v3`
- **Fallback:** `anthropic/claude-3-5-sonnet`

**Причины:**
- Качество для русского языка
- Низкая цена ($0.14 / 1M tokens)
- Tool calling support
- 64K context window

### 5.2 LLM Client

```python
class LLMClient:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.default_model = "deepseek/deepseek-v3"

    async def chat(self, messages: List[Dict]) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.default_model,
                    "messages": messages
                }
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        chat_id: int
    ) -> str:
        for iteration in range(5):
            response = await self._call_api(messages, tools)
            message = response["choices"][0]["message"]

            if not message.get("tool_calls"):
                return message["content"]

            messages.append(message)
            for tool_call in message["tool_calls"]:
                result = await self._execute_tool(tool_call, chat_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result)
                })

        return "Max iterations reached"
```

---

## 6. Технологический стек

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Language | Python | 3.11+ |
| Bot | Aiogram | 3.4.0+ |
| Web | FastAPI | 0.115.0+ |
| ASGI | Uvicorn | 0.30.0+ |
| Database | SQLite | 3.x |
| ORM | aiosqlite | 0.19.0+ |
| LLM | DeepSeek V3 | via OpenRouter |
| Encryption | Fernet | - |

---

## 7. Configuration

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token

# LLM
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-xxxxx
LLM_MODEL=deepseek/deepseek-v3

# Security
ENCRYPTION_MASTER_KEY=<base64_32_bytes>
JWT_SECRET_KEY=<random_string>
JWT_EXPIRE_DAYS=7

# Database
DATABASE_PATH=data/chat_data.db

# Web
WEB_HOST=0.0.0.0
WEB_PORT=8000
APP_URL=https://your-domain.com

# Features
RETENTION_DAYS=90
CONTEXT_MESSAGES=20
SUMMARY_TIME=16:00
```

---

## 8. Security

### Multi-layer Protection

1. **Authentication:** Telegram ID + OTP
2. **Authorization:** JWT (7 days)
3. **Encryption:** Per-chat AES-256
4. **SQL Injection:** Whitelist + read-only
5. **Rate Limiting:** slowapi
6. **Audit Log:** All sensitive ops

### SQL Agent Security

```python
FORBIDDEN = [
    "DELETE", "DROP", "UPDATE", "INSERT",
    "ALTER", "CREATE", "EXEC", "PRAGMA"
]

def is_safe_sql(query: str, chat_id: int) -> bool:
    q = query.upper().strip()

    if not q.startswith("SELECT"):
        return False

    if any(kw in q for kw in FORBIDDEN):
        return False

    if f"chat_id = {chat_id}" not in query.replace(" ", ""):
        return False

    if ";" in query or "--" in query:
        return False

    return True
```

---

## 9. Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ ./app/
CMD ["python", "-m", "app.main"]
```

### Docker Compose

```yaml
version: '3.8'
services:
  telegram-bot:
    build: .
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    ports:
      - "8000:8000"
```

---

## 10. Roadmap

### v2.1 (Q2 2026)
- WebSocket real-time
- Webhook mode
- Advanced analytics

### v2.2 (Q3 2026)
- PostgreSQL migration
- Vector search
- Multi-model LLM

### v3.0 (Q4 2026)
- Telegram Mini App
- Mobile app
- Enterprise SSO

---

**Версия:** 2.0 | **Дата:** 2026-01-27 | **Статус:** Production Ready
