# TECHNICAL_SPEC.md - Техническая спецификация

**Версия:** 2.0
**Дата:** 2026-01-25
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

---

## 📌 Обзор системы

### Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Users                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                   Bot API (aiogram)
                         │
┌────────────────────────┴────────────────┐
│                                            │
┌───▼────────────────┐        ┌──────────▼──────────┐
│  Telegram Bot      │        │    Group Chats      │
│   (aiogram)        │        │ (Save + Encrypt)    │
└────────────┬───────┘        └────────────────────┘
             │
┌────────────▼───────────────────┐
│      FastAPI Web Server        │
│  ┌─────────────────────────┐   │
│  │ /auth (Telegram OAuth)  │   │
│  │ /chat (SQL-agent)       │   │
│  │ /settings               │   │
│  │ /admin (superadmin)     │   │
│  └─────────────────────────┘   │
└────────────┬────────────────────┘
             │
┌────────────▼──────────────────────┐
│         Core Services             │
│  ┌──────────────────────────────┐ │
│  │ LLM Client (OpenRouter API)  │ │
│  │ SQL Agent (Safe queries)     │ │
│  │ Task Queue (asyncio.Queue)   │ │
│  │ Crypto (AES-256 per-chat)    │ │
│  └──────────────────────────────┘ │
└────────────┬───────────────────────┘
             │
┌────────────▼──────────────────────┐
│       SQLite Database             │
│  ┌──────────────────────────────┐ │
│  │ Messages (encrypted)         │ │
│  │ Users, Chats, Audit Log      │ │
│  │ Task Queue Table             │ │
│  │ FTS5 (Full-Text Search)      │ │
│  └──────────────────────────────┘ │
└──────────────────────────────────┘
```

---

## 🔧 Технологический стек (детально)

### Backend

| Компонент | Назначение | Технология |
|-----------|------------|------------|
| Telegram Bot | Сбор сообщений, команды, взаимодействие | aiogram 3.4+ |
| FastAPI Server | Web API, OAuth, SQL-агент | FastAPI 0.109+ |
| LLM Client | Интеграция с Claude/GPT | OpenRouter API |
| SQLite DB | Хранение сообщений, юзеров, очередь | aiosqlite + SQLAlchemy |
| Encryption | Шифрование сообщений per-chat | cryptography (Fernet) |
| Task Queue | Асинхронные задачи (summary, coach) | asyncio.Queue + DB table |
| FTS5 | Полнотекстовый поиск (русский язык) | SQLite FTS5 |

| Слой | Библиотека | Версия | Назначение |
|------|-----------|--------|------------|
| Web Framework | FastAPI | ≥0.109.0 | REST API, Pydantic validation |
| Bot Framework | aiogram | ≥3.4.0 | Async Telegram bot |
| HTTP Client | httpx | ≥0.26.0 | Async requests (LLM API) |
| Database (Async) | aiosqlite | ≥0.19.0 | Async SQLite driver |
| ORM | SQLAlchemy | ≥2.0.0 | Ready for PostgreSQL migration |
| Encryption | cryptography | ≥42.0.0 | Fernet (AES-256-CBC + HMAC) |
| Scheduling | APScheduler | ≥3.10.0 | Cron-like tasks (summary, coach) |
| Auth | python-jose | - | JWT tokens |
| Security | passlib | - | Password hashing (bcrypt) |
| Rate Limiting | slowapi | ≥0.1.9 | API rate limiter |
| Config | pydantic-settings | ≥2.1.0 | Environment-based config |

### Отсутствуют
- ❌ Redis - Очередь = таблица в SQLite
- ❌ Celery - Task worker = asyncio.Queue + background task
- ❌ pgvector - Нет embedding хранилища (пока)
- ❌ Kafka - Нет event streaming
- ❌ GraphQL - REST API достаточно для MVP

---

## 🗄️ Схема базы данных (полная)

### Таблица: users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,          -- Telegram user_id
    username TEXT UNIQUE,            -- @username или NULL
    first_name TEXT NOT NULL,
    last_name TEXT,
    language_code TEXT DEFAULT 'ru', -- ru, en, etc
    is_superadmin BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_username ON users(username);
```

> **Примечание:** `id = Telegram user_id`, уникален и не может меняться.

### Таблица: chats

```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY,          -- Telegram chat_id
    title TEXT NOT NULL,
    type TEXT NOT NULL,              -- 'private', 'group', 'supergroup'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,            -- Soft delete
    bot_left_at TIMESTAMP            -- Когда бот был удален из чата
);
CREATE INDEX idx_chats_deleted_at ON chats(deleted_at);
```

### Таблица: chat_members

```sql
CREATE TABLE chat_members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member',      -- 'admin', 'member'
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMP,               -- NULL если активный член
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_chat_members_user ON chat_members(user_id);
CREATE INDEX idx_chat_members_active ON chat_members(user_id, left_at);
```

### Таблица: messages

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,     -- Telegram message_id
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT NOT NULL, -- AES-256 Fernet encrypted
    timestamp TIMESTAMP NOT NULL,    -- Message send time
    is_deleted BOOLEAN DEFAULT 0,
    deleted_at TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (chat_id, message_id)     -- Одно сообщение = уникально per chat
);
CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
CREATE INDEX idx_messages_user ON messages(user_id);
CREATE INDEX idx_messages_deleted ON messages(is_deleted, deleted_at);
```

### Таблица: messages_fts (Full-Text Search)

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    message_id UNINDEXED,
    chat_id UNINDEXED,
    user_id UNINDEXED,
    content,
    timestamp UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'  -- Русский язык support
);
```

> **Синхронизация:** Триггер на INSERT/UPDATE/DELETE messages → обновляет FTS индекс.

### Таблица: chat_settings

```sql
CREATE TABLE chat_settings (
    chat_id INTEGER PRIMARY KEY,
    -- Summary skill settings
    summary_enabled BOOLEAN DEFAULT 1,
    summary_time_local TEXT DEFAULT '16:00',       -- HH:MM (local time)
    summary_timezone TEXT DEFAULT 'Europe/Moscow', -- IANA timezone
    summary_custom_prompt TEXT,                    -- Custom instructions
    summary_target TEXT DEFAULT 'chat',            -- 'chat', 'bot', 'disabled'

    -- Coach skill settings
    coach_enabled BOOLEAN DEFAULT 1,
    coach_custom_prompt TEXT,
    coach_target TEXT DEFAULT 'chat',              -- 'chat', 'bot', 'disabled'

    -- General
    language TEXT DEFAULT 'ru',                    -- ru, en

    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

### Таблица: llm_usage (Cost tracking)

```sql
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    skill TEXT NOT NULL,              -- 'summary', 'coach', 'sql_agent', 'thread_summary', 'qa'
    model TEXT,                       -- 'claude-3.5-sonnet', etc
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    cost_usd REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_llm_usage_chat ON llm_usage(chat_id, timestamp);
CREATE INDEX idx_llm_usage_user ON llm_usage(user_id, timestamp);
CREATE INDEX idx_llm_usage_skill ON llm_usage(skill, timestamp);
```

### Таблица: audit_log

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                  -- NULL для системных действий
    action TEXT NOT NULL,             -- 'sql_query', 'export_chat', 'change_settings', 'admin_notify'
    chat_id INTEGER,
    details TEXT,                     -- JSON string
    status TEXT DEFAULT 'success',    -- 'success', 'failed', 'blocked'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);
CREATE INDEX idx_audit_log_user ON audit_log(user_id, timestamp);
CREATE INDEX idx_audit_log_chat ON audit_log(chat_id, timestamp);
CREATE INDEX idx_audit_log_action ON audit_log(action, timestamp);
```

### Таблица: task_queue (Асинхронная очередь)

```sql
CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,          -- 'send_summary', 'send_coach', 'export_chat', 'cleanup'
    chat_id INTEGER,
    user_id INTEGER,
    payload TEXT,                     -- JSON string с параметрами

    status TEXT DEFAULT 'pending',    -- 'pending', 'processing', 'completed', 'failed'
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_task_queue_status ON task_queue(status, created_at);
CREATE INDEX idx_task_queue_chat ON task_queue(chat_id, status);
CREATE INDEX idx_task_queue_user ON task_queue(user_id, status);
```

---

## 🔐 Шифрование (подробно)

### Алгоритм

- **Метод:** Fernet (Symmetric encryption)
- **Algorithm:** AES-128-CBC
- **MAC:** HMAC-SHA256
- **Key derivation:** SHA-256(master_key + chat_id)

### Ключи

**Master Key** (32 bytes, base64):
```
ENCRYPTION_MASTER_KEY="V1Yt2wJ8...=="  (в .env)
```

**Per-Chat Key derivation** (32 bytes):
```
key = SHA256(master_key + str(chat_id))
fernet_key = base64(key)
```

### Реализация (pseudocode)

```python
from cryptography.fernet import Fernet
from hashlib import sha256
import base64

class ChatCrypto:
    def __init__(self, master_key: str):
        self.master_key = base64.b64decode(master_key)

    def encrypt(self, chat_id: int, plaintext: str) -> str:
        """Encrypt message for chat"""
        key = self._derive_key(chat_id)
        f = Fernet(key)
        encrypted = f.encrypt(plaintext.encode())
        return encrypted.decode()  # Store as string

    def decrypt(self, chat_id: int, ciphertext: str) -> str:
        """Decrypt message from chat"""
        key = self._derive_key(chat_id)
        f = Fernet(key)
        decrypted = f.decrypt(ciphertext.encode())
        return decrypted.decode()

    def _derive_key(self, chat_id: int) -> bytes:
        """Derive per-chat encryption key"""
        key_material = sha256(
            self.master_key + str(chat_id).encode()
        ).digest()
        return base64.urlsafe_b64encode(key_material)
```

### Генерация Master Key

```bash
# Generate 32-byte base64 key
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Пример вывода:
```
V1Yt2wJ8K9pL5mN3_QrS7vX8zAb2cD9eF0gH1iJ2kL3mN4oP5=
```

### GDPR: Удаление сообщений

Когда пользователь или чат удаляется:

```sql
-- Soft delete (mark as deleted)
UPDATE messages SET is_deleted=1, deleted_at=NOW() WHERE chat_id=X;

-- После 90 дней (по retention_days) → hard delete
DELETE FROM messages WHERE is_deleted=1 AND deleted_at < NOW() - INTERVAL '90 days';
```

---

## 🛠️ Основные API endpoints

### Авторизация

**POST** `/api/v1/auth/telegram`
- Payload: `{id, first_name, username, auth_date, hash}`
- Response: `{access_token, token_type, user_id, username}`

**POST** `/api/v1/auth/superadmin`
- Payload: `{password}`
- Response: `{access_token, token_type}`

### Chat API (SQL-agent)

**POST** `/api/v1/chat/query`
- Headers: `Authorization: Bearer {jwt_token}`
- Payload: `{chat_id, question}`
- Response: `{answer}`

**GET** `/api/v1/chat/{chat_id}/history?limit=100&offset=0&search=query`
- Headers: `Authorization: Bearer {jwt_token}`
- Response: `{messages: [...], total: 1234}`

### Settings

**GET** `/api/v1/settings/{chat_id}`
- Headers: `Authorization: Bearer {jwt_token}`
- Response: `{summary_enabled, coach_enabled, language, ...}`

**PUT** `/api/v1/settings/{chat_id}`
- Headers: `Authorization: Bearer {jwt_token}`
- Payload: `{summary_enabled, coach_custom_prompt, ...}`
- Response: `{status}`

### Admin

**GET** `/api/v1/admin/stats`
- Headers: `Authorization: Bearer {jwt_token}` (superadmin)
- Response: `{total_users, total_chats, total_messages, tokens_by_skill, ...}`

**POST** `/api/v1/admin/notify`
- Headers: `Authorization: Bearer {jwt_token}` (superadmin)
- Payload: `{user_id, message}`
- Response: `{status}`

---

## 🤖 Bot commands

### Public Commands (любой пользователь в чате)

- `/start` - Приветствие (в личном чате)
- `/stats` - Статистика чата
- `/export` - Экспортировать историю TXT
- `/summarize_thread` - Суммаризировать тред
- `/help` - Список команд

### Features

- `@bot question` - Вопрос о чате (QA с контекстом)
- (в личном чате) - SQL-agent режим выбора чата

---

## 📊 Skills (расширяемые модули)

### 1. Summary Skill
- **Триггер:** APScheduler (daily, по расписанию)
- **Input:** Messages за день, Custom prompt (если задан), Language
- **Output:** Summary text (300-500 слов), Tokens used
- **Target:** Chat (сообщение в чат), Bot PM (в личный чат), Disabled

### 2. Coach Skill
- **Триггер:** Ручной (по команде, или можно авто)
- **Input:** Recent messages, Custom prompt
- **Output:** Communication feedback
- **Target:** Chat или Bot PM

### 3. Thread Summary
- **Триггер:** Команда `/summarize_thread`
- **Input:** Messages в треде (reply chain или last 50)
- **Output:** 3-5 key points, Consensus (если есть)

### 4. SQL-Agent
- **Триггер:** User question в web interface или PM
- **Input:** Natural language question
- **Process:** LLM generates safe SQL → Validate → Execute readonly → Format results
- **Output:** Answer in natural language

### 5. Q&A Skill
- **Триггер:** `@bot question` в чате
- **Input:** User question, Chat context (last 20 messages)
- **Output:** Answer based on context

---

## ⚙️ Task Queue (asyncio-based)

### Архитектура

```
┌─────────────────┐
│  API Endpoint   │
│   Bot Command   │
│    Scheduler    │
└────────┬────────┘
         │
      add_task()
         │
┌────▼──────────────┐
│ task_queue table  │ (SQLite)
│  status='pending' │
└────┬──────────────┘
         │
┌────▼────────────────────┐
│  Background Worker      │
│   (get_next_pending)    │
│  status='processing'    │
└────┬────────────────────┘
         │
┌────▼────────────────────┐
│    Execute Task         │
│  (send_summary, etc)    │
└────┬────────────────────┘
         │
┌────▼────────────────────┐
│  status='completed'     │
│     or 'failed'         │
└─────────────────────────┘
```

### Task Types

| Type | Input | Output | Retry |
|------|-------|--------|-------|
| send_summary | {chat_id, date} | Message in chat/PM | 3x |
| send_coach | {chat_id, last_N_msgs} | Feedback message | 3x |
| export_chat | {chat_id, user_id, format} | TXT file → send | 1x |
| cleanup | {retention_days} | Deleted old messages | 1x |

### Worker Loop

```python
async def process_forever():
    while True:
        task = await db.get_next_pending_task()

        if not task:
            await asyncio.sleep(5)
            continue

        try:
            await db.update_task_status(task['id'], 'processing')

            if task['task_type'] == 'send_summary':
                await send_summary_task(task)
            elif task['task_type'] == 'send_coach':
                await send_coach_task(task)
            # ... etc

            await db.update_task_status(task['id'], 'completed')

        except Exception as e:
            if task['retry_count'] < task['max_retries']:
                await db.update_task_retry(task['id'])
            else:
                await db.update_task_status(task['id'], 'failed', str(e))
```

---

## 🔒 Безопасность (детально)

### Authentication

**Telegram OAuth (для web)**
- Клиент: Telegram Login Widget
- Verify hash by: HMAC-SHA256(token, {id, first_name, ...})
- Issue JWT token (7 дней TTL)

**Superadmin (password-based)**
- Hash: bcrypt ($2b...)
- Token: JWT с `is_superadmin=True`

### Authorization (RBAC)

| Role | Permissions |
|------|-------------|
| User | View own chats, QA search, SQL-agent (own chat only) |
| Chat Admin | Modify chat settings (summary, coach) |
| Superadmin | Global stats, send notifications, view audit |

### SQL-Agent Safety

```python
class SafeSQLValidator:
    FORBIDDEN = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE", "EXEC", "PRAGMA"]

    def validate(sql: str, chat_id: int) -> bool:
        # 1. No forbidden keywords
        if any(kw in sql.upper() for kw in FORBIDDEN):
            return False

        # 2. Must have WHERE chat_id = chat_id
        if f"chat_id = {chat_id}" not in sql:
            return False

        # 3. Only SELECT allowed
        if not sql.upper().startswith("SELECT"):
            return False

        return True
```

### Rate Limiting

- **Telegram global:** 30 msg/sec
- **Per-chat:** 1 msg/sec (избежать abuse)
- **API:** 10 req/min per user (slowapi)

### Input Validation

- Все Pydantic models с type hints
- Максимальная длина текста: 4096 (Telegram limit)
- SQL query: max 1000 chars

### Audit Log

Все чувствительные действия логируются:

```json
{
  "user_id": 123,
  "action": "sql_query",
  "chat_id": 456,
  "status": "success",
  "details": {
    "sql": "SELECT * FROM messages WHERE chat_id = 456",
    "rows_returned": 42
  },
  "timestamp": "2026-01-25T10:30:00Z"
}
```

---

## 📈 Performance & Scalability

### Current (SQLite)

| Metric | Value |
|--------|-------|
| Concurrent users | ~100 |
| Messages per chat | 1M (с indexes) |
| FTS latency | <500ms (1M docs) |
| Async workers | 10-20 |

### Future (PostgreSQL)

**Upgrade:** Change `DATABASE_URL` in config
- SQLAlchemy: No code changes needed
- Performance: 10x+ improvement
- Features: pgvector (embeddings), JSON operators

### Optimizations

- **Database indexes** - ON (chat_id, timestamp)
- **FTS5** - UNINDEXED columns для больших полей
- **Async I/O** - aiosqlite, httpx, no blocking
- **Task batching** - группировка message saves
- **Message caching** - LRU cache для recent messages

---

## 🚀 Развертывание

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### Docker-compose

```yaml
version: '3.8'
services:
  bot:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN={LLM_API_KEY}
      - JWT_SECRET_KEY={ENCRYPTION_MASTER_KEY}
    volumes:
      - ./data:/app/data
    ports:
      - "8000:8000"
```

### .env Template

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_WEBHOOK_URL=https://example.com/webhook
LLM_BASE_URL=https://openrouter.io/api/v1
LLM_API_KEY=sk-or-v1-...
LLM_MODEL_NAME=anthropic/claude-3.5-sonnet
ENCRYPTION_MASTER_KEY=V1Yt2wJ8K9pL5mN3_QrS7vX8zAb2cD9eF0gH1iJ2kL3mN4oP5=
JWT_SECRET_KEY=your-super-secret-key-change-in-production
SUPERADMIN_PASSWORD_HASH=$2b...
DATABASE_URL=sqlite+aiosqlite:///./data/chat_data.db
RETENTION_DAYS=90
SUMMARY_TIME_UTC=13:00
DEFAULT_LANGUAGE=ru
HOST=0.0.0.0
PORT=8000
DEBUG=False
```

---

## 🧪 Тестирование

### Unit Tests

**tests/test_crypto.py**
```python
def test_encrypt_decrypt():
    crypto = ChatCrypto(master_key)
    encrypted = crypto.encrypt(chat_id=123, plaintext="hello")
    decrypted = crypto.decrypt(chat_id=123, ciphertext=encrypted)
    assert decrypted == "hello"
```

**tests/test_sql_agent.py**
```python
def test_sql_validation_safe():
    agent = SafeSQLAgent(...)
    assert agent._is_safe("SELECT * FROM messages WHERE chat_id=123", 123)

def test_sql_validation_unsafe():
    agent = SafeSQLAgent(...)
    assert not agent._is_safe("DELETE FROM messages", 123)
```

**tests/test_api.py**
```python
@pytest.mark.asyncio
async def test_telegram_auth():
    response = await client.post("/api/v1/auth/telegram", json=auth_data)
    assert response.status_code == 200
    assert "access_token" in response.json()
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_workflow():
    # 1. Save message
    await db.save_message(...)

    # 2. Generate summary
    summary = await summary_skill.execute(...)

    # 3. Verify FTS works
    results = await db.fts_search(...)
    assert results
```

---

## 📚 Документация структуры

Каждый файл должен содержать:

**Module docstring**
```python
"""
Core database operations.
Handles:
- SQLite/PostgreSQL abstraction
- Message encryption/decryption
- FTS5 indexing
"""
```

**Type hints везде**
```python
async def save_message(
    chat_id: int,
    user_id: int,
    content_encrypted: str,
    timestamp: datetime
) -> int:
    ...
```

**Docstrings для публичных функций**
```python
async def get_chat_stats(chat_id: int) -> dict:
    """
    Get comprehensive chat statistics.

    Returns:
        {
            "message_count": 1234,
            "member_count": 45,
            "messages_today": 67,
            "last_activity": "2026-01-25T10:30:00Z"
        }
    """
```

**Error handling**
```python
try:
    await db.execute(sql)
except DatabaseError as e:
    logger.error(f"DB error: {e}", extra={"sql": sql})
    raise
```

---

## 📋 Миграция на PostgreSQL

### Шаг 1: Обновить config.py
```python
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/chat_db"
```

### Шаг 2: Использовать Alembic (в будущем)
```bash
alembic init migrations
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

### Шаг 3: Код не меняется
- SQLAlchemy abstraction
- aiosqlite → asyncpg (просто меняем driver)

---

**Версия:** 2.0 | **Статус:** Ready for Implementation | **Дата:** 2026-01-25
