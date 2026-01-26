# 🤖 AGENTS.md - Инструкция для кодового агента

**Версия:** 2.0  
**Дата:** 2026-01-25  
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

---

## 🎯 Цель проекта

Корпоративный self-hosted Telegram бот с веб-интерфейсом для:
- Аналитики приватных чатов с шифрованием
- AI-коучинга коммуникаций
- SQL-агента для разговора с данными чатов
- Многопользовательского режима с авторизацией через Telegram

**Целевая аудитория:** Корпоративный сектор (self-hosted решение).

---

## ⚡ Принципы разработки

### KISS (Keep It Simple, Stupid)
- Минимум зависимостей
- **SQLite с асинхронным доступом (aiosqlite)**
- Один процесс для бота + API (asyncio)
- **Очередь задач как таблица в БД (не Celery, не Redis)**
- Нет Redis, Celery - все в памяти через asyncio.Queue

### DRY (Don't Repeat Yourself)
- Базовые классы для Skills (`core/skills/base.py`)
- Единый LLM client для всех модулей
- Переиспользуемые middleware (auth, chat access)
- Общие утилиты шифрования

### Готовность к миграции
- **SQLite now, PostgreSQL ready**
- Код не зависит от конкретной БД (abstraction layer)
- SQLAlchemy async для будущей миграции

### Безопасность
- **Шифрование at rest:** AES-256 per-chat encryption
- **Авторизация:** Telegram OAuth + JWT
- **Доступ:** RBAC - пользователь видит только свои чаты
- **SQL-агент:** Только SELECT, обязательный WHERE chat_id=X
- **Audit log:** Все действия админов и пользователей

---

## 📁 Структура проекта

```
telegram_chanel_agg/
├── main.py                    # Entry point (FastAPI + Bot startup)
├── config.py                  # Pydantic settings
├── requirements.txt           # Dependencies
├── Dockerfile                 # Docker config
├── docker-compose.yml         # Deployment
├── .env.example              # Template
│
├── core/                      # 🔧 Core functionality
│   ├── __init__.py
│   ├── db.py                 # Database + FTS setup + queue table
│   ├── crypto.py             # Encryption/decryption
│   ├── llm.py                # OpenAI-compatible LLM client
│   ├── sql_agent.py          # Safe SQL generation + execution
│   ├── i18n.py               # Multilang support (ru/en)
│   └── rate_limiter.py       # Telegram rate limit handler (asyncio.Queue)
│
├── bot/                       # 🤖 Telegram Bot
│   ├── __init__.py
│   ├── handlers.py           # Message handlers
│   ├── commands.py           # Bot commands (/stats, /export, etc)
│   ├── auth.py               # Telegram OAuth for web
│   ├── scheduler.py          # APScheduler tasks (summary, retention)
│   └── private_chat.py       # Private chat handlers (SQL-agent mode)
│
├── web/                       # 🌐 FastAPI Web Interface
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── middleware.py         # Auth, CORS, rate limiting
│   ├── routes/
│   │   ├── auth.py           # Login endpoints
│   │   ├── admin.py          # Superadmin panel
│   │   ├── chat.py           # SQL-agent chat interface
│   │   ├── settings.py       # Chat settings (summary/coach config)
│   │   └── export.py         # Export chat history
│   └── models.py             # Pydantic request/response models
│
├── skills/                    # 🎓 Bot Skills (extensible)
│   ├── __init__.py
│   ├── base.py               # Abstract Skill class
│   ├── summary.py            # Daily summary skill
│   ├── coach.py              # Communication coach skill
│   └── thread_summary.py     # Thread summarization skill
│
├── tests/                     # 🧪 Tests
│   ├── test_crypto.py
│   ├── test_sql_agent.py
│   └── test_api.py
│
└── docs/                      # 📚 Documentation
    ├── TECHNICAL_SPEC.md
    ├── DATABASE_SCHEMA.md
    ├── API_SPECIFICATION.md
    ├── SECURITY_GUIDE.md
    └── CHANGELOG.md
```

---

## 🛠️ Технологический стек

### Обязательные библиотеки

```txt
# requirements.txt

# === Web Framework ===
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.6
pydantic>=2.5.0
pydantic-settings>=2.1.0

# === Telegram Bot ===
aiogram>=3.4.0              # Async Telegram bot framework
python-telegram-bot>=20.7   # Alternative (optional)

# === Database ===
aiosqlite>=0.19.0           # Async SQLite
sqlalchemy>=2.0.0           # ORM (ready for PostgreSQL migration)

# === Encryption ===
cryptography>=42.0.0        # Fernet for AES-256

# === HTTP Client ===
httpx>=0.26.0               # Async HTTP (for LLM API calls)

# === Scheduling ===
apscheduler>=3.10.0         # Scheduled tasks

# === Security ===
slowapi>=0.1.9              # Rate limiting
python-jose[cryptography]   # JWT tokens
passlib[bcrypt]             # Password hashing

# === Templates (for web interface) ===
jinja2>=3.1.3               # HTML templates

# === Utilities ===
python-dotenv>=1.0.0        # .env support
pytz>=2024.1                # Timezone support
```

**ВАЖНО:** Нет Redis, нет Celery, нет pgvector (пока). Очередь = таблица в SQLite.

---

## 🔑 Конфигурация (config.py)

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # === Telegram ===
    telegram_bot_token: str
    telegram_webhook_url: Optional[str] = None  # Для webhook (опционально)
    
    # === LLM (OpenAI-compatible API) ===
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str
    llm_model_name: str = "anthropic/claude-3.5-sonnet"
    llm_max_tokens: int = 4000
    llm_temperature: float = 0.7
    llm_timeout: int = 60  # seconds
    
    # === Security ===
    encryption_master_key: str  # Base64-encoded 32 bytes
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 дней
    superadmin_password_hash: str  # Bcrypt hash
    
    # === Database ===
    database_url: str = "sqlite+aiosqlite:///./data/chat_data.db"
    database_path: str = "data/chat_data.db"  # Для чистого SQLite
    
    # === Features ===
    retention_days: int = 90
    summary_time_utc: str = "13:00"  # 16:00 MSK
    default_language: str = "ru"
    context_messages: int = 20  # Для QA контекста
    
    # === Rate Limiting ===
    telegram_global_rate: int = 30  # msg/sec глобально
    telegram_per_chat_rate: float = 1.0  # msg/sec per chat
    api_rate_limit: str = "10/minute"
    
    # === Server ===
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

---

## 🗄️ База данных (SQLite + FTS)

### Основные таблицы

```sql
-- === USERS ===
CREATE TABLE users (
    id INTEGER PRIMARY KEY,          -- Telegram user_id
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT DEFAULT 'ru',
    is_superadmin BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === CHATS ===
CREATE TABLE chats (
    id INTEGER PRIMARY KEY,          -- Telegram chat_id
    title TEXT NOT NULL,
    type TEXT NOT NULL,              -- 'group', 'supergroup'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP             -- Soft delete при удалении бота
);

-- === CHAT MEMBERS ===
CREATE TABLE chat_members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member',      -- 'admin', 'member'
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMP,               -- NULL если активен
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- === MESSAGES (зашифрованы) ===
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,     -- Telegram message_id
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT,          -- AES-256 encrypted
    timestamp TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT 0,
    deleted_at TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (chat_id, message_id)
);

-- === FULL-TEXT SEARCH (FTS5 для русского текста) ===
CREATE VIRTUAL TABLE messages_fts USING fts5(
    message_id UNINDEXED,
    chat_id UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 2'
);

-- === CHAT SETTINGS ===
CREATE TABLE chat_settings (
    chat_id INTEGER PRIMARY KEY,
    summary_enabled BOOLEAN DEFAULT 1,
    summary_time_local TEXT DEFAULT '16:00',
    summary_timezone TEXT DEFAULT 'Europe/Moscow',
    summary_custom_prompt TEXT,
    summary_target TEXT DEFAULT 'chat',  -- 'chat', 'bot', 'disabled'
    
    coach_enabled BOOLEAN DEFAULT 1,
    coach_custom_prompt TEXT,
    coach_target TEXT DEFAULT 'chat',
    
    language TEXT DEFAULT 'ru',
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

-- === LLM USAGE TRACKING ===
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    skill TEXT NOT NULL,             -- 'summary', 'coach', 'sql_agent', 'thread_summary', 'qa'
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    cost_usd REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- === AUDIT LOG ===
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                 -- NULL для system actions
    action TEXT NOT NULL,            -- 'sql_query', 'export_chat', 'change_settings', 'admin_notify', etc
    chat_id INTEGER,
    details TEXT,                    -- JSON string
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

-- === TASK QUEUE (для асинхронных задач вместо Celery) ===
CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,         -- 'send_summary', 'export_chat', 'cleanup', etc
    chat_id INTEGER,
    user_id INTEGER,
    payload TEXT,                    -- JSON string с параметрами
    status TEXT DEFAULT 'pending',   -- 'pending', 'processing', 'completed', 'failed'
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- === INDEXES ===
CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
CREATE INDEX idx_messages_user ON messages(user_id);
CREATE INDEX idx_messages_deleted ON messages(is_deleted, deleted_at);
CREATE INDEX idx_chat_members_user ON chat_members(user_id);
CREATE INDEX idx_chat_members_active ON chat_members(user_id, left_at);
CREATE INDEX idx_llm_usage_chat ON llm_usage(chat_id, timestamp);
CREATE INDEX idx_llm_usage_user ON llm_usage(user_id, timestamp);
CREATE INDEX idx_audit_log_user ON audit_log(user_id, timestamp);
CREATE INDEX idx_audit_log_chat ON audit_log(chat_id, timestamp);
CREATE INDEX idx_task_queue_status ON task_queue(status, created_at);
```

---

## 🔐 Шифрование (core/crypto.py)

### Требования
- **Per-chat encryption:** Каждый чат = уникальный ключ (derived от master key)
- **Алгоритм:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Master key:** 32 байта, base64-encoded в `ENCRYPTION_MASTER_KEY`

### Реализация

```python
# core/crypto.py
from cryptography.fernet import Fernet
import base64
from hashlib import sha256

class ChatCrypto:
    def __init__(self, master_key: str):
        """
        master_key - base64-encoded 32 bytes
        Генерация: python -c "import secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
        """
        self.master_key = base64.b64decode(master_key)
    
    def _derive_chat_key(self, chat_id: int) -> bytes:
        """Derive unique 32-byte key for chat from master key"""
        key_material = sha256(
            self.master_key + str(chat_id).encode()
        ).digest()
        return base64.urlsafe_b64encode(key_material)
    
    def encrypt(self, chat_id: int, text: str) -> str:
        """Encrypt message for specific chat"""
        f = Fernet(self._derive_chat_key(chat_id))
        return f.encrypt(text.encode()).decode()
    
    def decrypt(self, chat_id: int, encrypted: str) -> str:
        """Decrypt message from specific chat"""
        f = Fernet(self._derive_chat_key(chat_id))
        return f.decrypt(encrypted.encode()).decode()
    
    def get_key_hash(self, chat_id: int) -> str:
        """Hash для идентификации ключа (для GDPR удаления)"""
        return sha256(self._derive_chat_key(chat_id)).hexdigest()
```

---

## 🤖 Telegram Bot

### Основные handler'ы (bot/handlers.py)

```python
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

# === 1. Сохранение сообщений ===
@router.message(F.chat.type.in_(['group', 'supergroup']))
async def save_message(message: Message):
    """Сохраняет все сообщения в чате"""
    
    # Проверка: зарегистрирован ли чат
    if not await db.is_chat_registered(message.chat.id):
        await db.register_chat(
            chat_id=message.chat.id,
            title=message.chat.title
        )
    
    # Убедиться что user есть в БД
    if not await db.user_exists(message.from_user.id):
        await db.create_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )
    
    # Добавить юзера в чат
    await db.add_chat_member(message.chat.id, message.from_user.id)
    
    # Шифрование + сохранение
    crypto = ChatCrypto(settings.encryption_master_key)
    encrypted = crypto.encrypt(message.chat.id, message.text or "")
    
    await db.save_message(
        chat_id=message.chat.id,
        message_id=message.message_id,
        user_id=message.from_user.id,
        content_encrypted=encrypted,
        timestamp=message.date
    )
    
    # FTS индексация (автоматическая через триггер)

# === 2. Упоминание бота (@bot вопрос) ===
@router.message(F.text.contains(f"@{bot.username}"))
async def bot_mention(message: Message):
    """Отвечает на вопросы через LLM с контекстом чата"""
    
    question = message.text.replace(f"@{bot.username}", "").strip()
    if not question:
        return
    
    # Получить контекст (последние 20 сообщений)
    context_messages = await db.get_recent_messages(
        message.chat.id,
        limit=settings.context_messages
    )
    
    # Расшифровка контекста
    crypto = ChatCrypto(settings.encryption_master_key)
    context = [
        {
            "user": msg['username'],
            "text": crypto.decrypt(message.chat.id, msg['content_encrypted']),
            "time": msg['timestamp']
        }
        for msg in context_messages
    ]
    
    # Получить язык и настройки чата
    settings_row = await db.get_chat_settings(message.chat.id)
    lang = settings_row['language'] if settings_row else 'ru'
    
    # LLM запрос
    answer = await llm.chat_qa(question, context, lang)
    
    # Логирование usage
    await db.log_llm_usage(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        skill='qa',
        tokens_prompt=answer['usage']['prompt_tokens'],
        tokens_completion=answer['usage']['completion_tokens']
    )
    
    await message.reply(answer['text'][:4096])  # Лимит Telegram

# === 3. Личное общение с ботом ===
@router.message(F.chat.type == 'private')
async def private_chat(message: Message, state: FSMContext):
    """Личный чат с ботом - выбор чата + SQL-агент"""
    
    # Получить все чаты пользователя
    user_chats = await db.get_user_chats(message.from_user.id)
    
    if not user_chats:
        await message.reply("You are not a member of any registered chats.")
        return
    
    # Если пользователь еще не выбрал чат - показать список
    state_data = await state.get_data()
    if 'selected_chat_id' not in state_data:
        # Показать inline keyboard с чатами
        await show_chat_selector(message, user_chats, state)
        return
    
    # SQL-агент для выбранного чата
    chat_id = state_data['selected_chat_id']
    lang = await db.get_user_language(message.from_user.id)
    
    # Валидация доступа
    if not await db.is_chat_member(message.from_user.id, chat_id):
        await message.reply("Access denied to this chat.")
        return
    
    # Выполнить SQL-агент запрос
    answer = await sql_agent.query(
        user_id=message.from_user.id,
        chat_id=chat_id,
        question=message.text,
        lang=lang
    )
    
    await message.reply(answer[:4096])

# === 4. Thread summary ===
@router.message(Command("summarize_thread"))
async def summarize_thread(message: Message):
    """Суммаризация треда или последних N сообщений"""
    
    # Определить границы треда
    if message.reply_to_message:
        # Get all messages in reply chain
        thread_messages = await db.get_reply_chain(
            message.chat.id,
            message.reply_to_message.message_id
        )
    else:
        # Last 50 messages
        thread_messages = await db.get_recent_messages(
            message.chat.id,
            limit=50
        )
    
    # Расшифровка
    crypto = ChatCrypto(settings.encryption_master_key)
    decrypted_messages = [
        {
            "user": msg['username'],
            "text": crypto.decrypt(message.chat.id, msg['content_encrypted'])
        }
        for msg in thread_messages
    ]
    
    # Skill: thread_summary
    from skills.thread_summary import ThreadSummarySkill
    skill = ThreadSummarySkill(llm_client)
    
    lang = await db.get_chat_language(message.chat.id)
    result = await skill.execute(decrypted_messages, language=lang)
    
    await message.reply(result.text[:4096])
    
    # Log usage
    await db.log_llm_usage(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        skill='thread_summary',
        tokens_prompt=result.tokens_used // 2,
        tokens_completion=result.tokens_used // 2
    )

# === 5. Удаление сообщения ===
@router.deleted_message()
async def handle_deleted_message(message: Message):
    """Отслеживание удаленных сообщений"""
    await db.mark_message_deleted(
        chat_id=message.chat.id,
        message_id=message.message_id
    )
```

### Команды бота (bot/commands.py)

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие в личном чате"""
    text = """
👋 Welcome to Chat Analytics Bot!

Commands:
/stats - Chat statistics
/export - Export chat history
/help - Show all commands
/summarize_thread - Summarize discussion
    """
    await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика чата"""
    if message.chat.type == 'private':
        await message.reply("Use this command in a group chat")
        return
    
    stats = await db.get_chat_stats(message.chat.id)
    text = f"""
📊 Chat Statistics:
- Total messages: {stats['message_count']}
- Active members: {stats['member_count']}
- Messages today: {stats['messages_today']}
- Last activity: {stats['last_activity']}
    """
    await message.reply(text)

@router.message(Command("export"))
async def cmd_export(message: Message):
    """Экспорт истории чата в TXT"""
    if message.chat.type == 'private':
        await message.reply("Use this command in a group chat")
        return
    
    # Проверка прав (только админ чата или юзер может экспортировать свой чат)
    if not await db.is_chat_admin(message.from_user.id, message.chat.id):
        # Но юзеры в личном чате могут запросить экспорт
        await message.reply("Only chat admins can export. Request export in bot PM.")
        return
    
    # Генерация TXT файла
    file_path = await export_chat_history(
        chat_id=message.chat.id,
        crypto=ChatCrypto(settings.encryption_master_key)
    )
    
    with open(file_path, 'rb') as f:
        await message.reply_document(f)
    
    # Audit log
    await db.audit_log(
        user_id=message.from_user.id,
        action="export_chat",
        chat_id=message.chat.id
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Список команд"""
    text = """
Commands:
/start - Show welcome message
/stats - Chat statistics
/export - Export chat as TXT
/summarize_thread - Summarize discussion or thread
/help - Show this message

Features:
- @bot question - Ask question about chat
- In personal chat - SQL agent mode to query chat data
    """
    await message.reply(text)
```

---

## 🌐 Web API

### Авторизация (web/routes/auth.py)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    username: str | None = None
    auth_date: int
    hash: str

@router.post("/auth/telegram")
async def telegram_login(data: TelegramAuthData):
    """
    Telegram Login Widget authentication
    Клиент отправляет данные с фронтенда после Telegram Login Widget
    """
    
    # Verify hash (Telegram OAuth signature)
    if not verify_telegram_auth(data, settings.telegram_bot_token):
        raise HTTPException(401, "Invalid auth hash")
    
    # Create or update user
    await db.get_or_create_user(
        user_id=data.id,
        username=data.username,
        first_name=data.first_name
    )
    
    # Generate JWT
    token = create_jwt_token(user_id=data.id)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": data.id,
        "username": data.username
    }

@router.post("/auth/superadmin")
async def superadmin_login(password: str):
    """Superadmin login with password"""
    if not verify_password(password, settings.superadmin_password_hash):
        raise HTTPException(401, "Invalid password")
    
    token = create_jwt_token(user_id=0, is_superadmin=True)
    return {
        "access_token": token,
        "token_type": "bearer"
    }
```

### SQL-агент чат (web/routes/chat.py)

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class ChatQueryRequest(BaseModel):
    chat_id: int
    question: str

@router.post("/chat/query")
async def sql_agent_query(
    req: ChatQueryRequest,
    user: dict = Depends(get_current_user)
):
    """SQL-агент для разговора с данными чата"""
    
    # Проверка доступа
    if not await db.is_chat_member(user['id'], req.chat_id):
        raise HTTPException(403, "Access denied")
    
    # SQL-агент
    answer = await sql_agent.query(
        user_id=user['id'],
        chat_id=req.chat_id,
        question=req.question,
        lang=user.get('language', 'ru')
    )
    
    return {"answer": answer}

@router.get("/chat/{chat_id}/history")
async def get_chat_history(
    chat_id: int,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
    user: dict = Depends(get_current_user)
):
    """Получить историю чата с полнотекстовым поиском"""
    
    if not await db.is_chat_member(user['id'], chat_id):
        raise HTTPException(403)
    
    # FTS поиск
    if search:
        messages = await db.fts_search(chat_id, search, limit, offset)
    else:
        messages = await db.get_messages(chat_id, limit, offset)
    
    # Расшифровка
    crypto = ChatCrypto(settings.encryption_master_key)
    decrypted = [
        {
            "id": msg['id'],
            "user_id": msg['user_id'],
            "username": msg['username'],
            "content": crypto.decrypt(chat_id, msg['content_encrypted']),
            "timestamp": msg['timestamp']
        }
        for msg in messages
    ]
    
    return {
        "messages": decrypted,
        "total": await db.count_messages(chat_id)
    }
```

### Настройки чата (web/routes/settings.py)

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()

class ChatSettingsUpdate(BaseModel):
    summary_enabled: bool | None = None
    summary_time_local: str | None = None
    summary_custom_prompt: str | None = None
    summary_target: str | None = None  # 'chat', 'bot', 'disabled'
    
    coach_enabled: bool | None = None
    coach_custom_prompt: str | None = None
    coach_target: str | None = None
    
    language: str | None = None

@router.get("/settings/{chat_id}")
async def get_chat_settings(
    chat_id: int,
    user: dict = Depends(get_current_user)
):
    """Получить настройки чата"""
    
    if not await db.is_chat_admin(user['id'], chat_id):
        raise HTTPException(403, "Only admins can view settings")
    
    settings = await db.get_chat_settings(chat_id)
    return settings or {}

@router.put("/settings/{chat_id}")
async def update_chat_settings(
    chat_id: int,
    updates: ChatSettingsUpdate,
    user: dict = Depends(get_current_user)
):
    """Обновить настройки чата"""
    
    if not await db.is_chat_admin(user['id'], chat_id):
        raise HTTPException(403)
    
    update_data = updates.dict(exclude_none=True)
    await db.update_chat_settings(chat_id, update_data)
    
    # Audit log
    await db.audit_log(
        user_id=user['id'],
        action="update_settings",
        chat_id=chat_id,
        details=update_data
    )
    
    return {"status": "ok"}
```

### Суперадмин панель (web/routes/admin.py)

```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

@router.get("/admin/stats")
async def get_global_stats(user: dict = Depends(require_superadmin)):
    """Глобальная статистика БЕЗ доступа к контенту чатов"""
    
    stats = {
        "total_users": await db.count_users(),
        "total_chats": await db.count_chats(),
        "total_messages": await db.count_messages(),
        
        "tokens_by_skill": await db.get_tokens_by_skill(),
        
        "per_user_stats": await db.get_per_user_stats()
    }
    
    return stats

@router.post("/admin/notify")
async def notify_user(
    user_id: int,
    message: str,
    user: dict = Depends(require_superadmin)
):
    """Отправить уведомление пользователю в Telegram"""
    
    try:
        await bot.send_message(user_id, f"⚠️ Admin notification:\n{message}")
    except Exception as e:
        raise HTTPException(500, f"Failed to send: {str(e)}")
    
    await db.audit_log(
        user_id=0,  # System action
        action="admin_notify",
        chat_id=None,
        details={"target_user_id": user_id, "message": message}
    )
    
    return {"status": "sent"}
```

---

## 🎓 Skills (расширяемые модули)

### Базовый класс (skills/base.py)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class SkillResult:
    text: str
    tokens_used: int
    metadata: dict[str, Any] | None = None

class Skill(ABC):
    """Base class for all bot skills"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Skill name for logging"""
        pass
    
    @abstractmethod
    async def execute(self, context: Any, language: str = "ru") -> SkillResult:
        """Execute skill with given context"""
        pass
```

### Summary Skill (skills/summary.py)

```python
from .base import Skill, SkillResult
from core.llm import LLMClient

class SummarySkill(Skill):
    @property
    def name(self) -> str:
        return "summary"
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
    
    async def execute(
        self,
        messages: list,
        language: str = "ru",
        custom_prompt: str = ""
    ) -> SkillResult:
        """Generate daily summary of chat"""
        
        # Формирование промпта
        base_prompt = get_summary_prompt(language)
        if custom_prompt:
            base_prompt += f"\n\nAdditional instructions:\n{custom_prompt}"
        
        # Подготовка контекста
        context_text = "\n".join([
            f"[{msg['timestamp']}] {msg['username']}: {msg['text']}"
            for msg in messages
        ])
        
        # LLM генерация
        response = await self.llm.generate(
            prompt=f"{base_prompt}\n\nChat history:\n{context_text}",
            max_tokens=1000
        )
        
        return SkillResult(
            text=response['text'],
            tokens_used=response['usage']['total_tokens'],
            metadata={"messages_count": len(messages)}
        )
```

### Thread Summary Skill (skills/thread_summary.py)

```python
from .base import Skill, SkillResult

class ThreadSummarySkill(Skill):
    @property
    def name(self) -> str:
        return "thread_summary"
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def execute(
        self,
        messages: list,
        language: str = "ru"
    ) -> SkillResult:
        """Summarize thread/discussion in 3-5 points"""
        
        prompt = get_thread_summary_prompt(language)
        
        context = "\n".join([
            f"{msg['username']}: {msg['text']}"
            for msg in messages
        ])
        
        response = await self.llm.generate(
            prompt=f"{prompt}\n\nDiscussion:\n{context}",
            max_tokens=500
        )
        
        return SkillResult(
            text=response['text'],
            tokens_used=response['usage']['total_tokens']
        )
```

---

## 🔒 SQL-агент (core/sql_agent.py)

```python
import re
from typing import Optional

class SafeSQLAgent:
    FORBIDDEN = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE", "EXEC", "PRAGMA"]
    
    def __init__(self, llm_client, schema: str):
        self.llm = llm_client
        self.schema = schema
    
    async def query(
        self,
        user_id: int,
        chat_id: int,
        question: str,
        lang: str = "ru"
    ) -> str:
        """Safe SQL generation and execution with audit"""
        
        # 1. Check access
        if not await db.is_chat_member(user_id, chat_id):
            return get_i18n("access_denied", lang)
        
        # 2. Generate SQL
        prompt = self._build_prompt(chat_id, question, lang)
        response = await self.llm.generate(prompt, max_tokens=500)
        sql = self._extract_sql(response['text'])
        
        # 3. Validate safety
        if not self._is_safe(sql, chat_id):
            await db.audit_log(user_id, "sql_query_blocked", chat_id, {"sql": sql})
            return get_i18n("unsafe_query", lang)
        
        # 4. Execute
        try:
            results = await db.execute_read_only(sql)
        except Exception as e:
            await db.audit_log(user_id, "sql_query_error", chat_id, {
                "sql": sql,
                "error": str(e)
            })
            return get_i18n("query_error", lang)
        
        # 5. Format results with LLM
        answer = await self.llm.format_results(question, results, lang)
        
        # 6. Log success
        await db.log_llm_usage(
            user_id=user_id,
            chat_id=chat_id,
            skill='sql_agent',
            tokens_prompt=response['usage']['prompt_tokens'],
            tokens_completion=response['usage']['completion_tokens']
        )
        
        await db.audit_log(user_id, "sql_query", chat_id, {
            "sql": sql,
            "rows_returned": len(results)
        })
        
        return answer['text']
    
    def _is_safe(self, sql: str, chat_id: int) -> bool:
        """Validate SQL safety"""
        sql_upper = sql.upper()
        
        # No forbidden keywords
        if any(kw in sql_upper for kw in self.FORBIDDEN):
            return False
        
        # Must filter by chat_id
        chat_id_pattern = f"chat_id = {chat_id}"
        if chat_id_pattern not in sql and chat_id_pattern.replace(" ", "") not in sql:
            return False
        
        # Only SELECT allowed
        if not sql_upper.strip().startswith("SELECT"):
            return False
        
        return True
    
    def _build_prompt(self, chat_id: int, question: str, lang: str) -> str:
        """Build LLM prompt"""
        return f"""You are a SQL expert. Generate READ-ONLY SQL query ONLY.

Database schema:
{self.schema}

CRITICAL RULES:
1. ONLY SELECT queries allowed
2. MUST include: WHERE chat_id = {chat_id}
3. NEVER use DELETE, UPDATE, INSERT, DROP, ALTER, CREATE

User question: {question}
Language: {lang}

Return ONLY SQL query, no explanation:"""

    def _extract_sql(self, text: str) -> str:
        """Extract SQL from markdown"""
        text = re.sub(r'```sql\n?', '', text)
        text = re.sub(r'```\n?', '', text)
        return text.strip()
```

---

## 🔄 Task Queue (вместо Celery)

**Очередь задач как таблица в SQLite.** Простой background worker:

```python
# core/task_queue.py
import asyncio
import json
from datetime import datetime

class TaskQueueWorker:
    def __init__(self, db, llm_client, bot):
        self.db = db
        self.llm = llm_client
        self.bot = bot
    
    async def start(self):
        """Start background worker"""
        asyncio.create_task(self._process_forever())
    
    async def _process_forever(self):
        """Process pending tasks"""
        while True:
            # Get next pending task
            task = await self.db.get_next_pending_task()
            
            if not task:
                await asyncio.sleep(5)  # Wait before retry
                continue
            
            try:
                # Mark as processing
                await self.db.update_task_status(task['id'], 'processing')
                
                # Execute
                if task['task_type'] == 'send_summary':
                    await self._send_summary(task)
                elif task['task_type'] == 'send_coach':
                    await self._send_coach(task)
                elif task['task_type'] == 'export_chat':
                    await self._export_chat(task)
                
                # Mark complete
                await self.db.update_task_status(task['id'], 'completed')
            
            except Exception as e:
                # Increment retry
                retry_count = task['retry_count'] + 1
                if retry_count >= task['max_retries']:
                    await self.db.update_task_status(task['id'], 'failed', str(e))
                else:
                    await self.db.update_task_retry(task['id'], retry_count)
    
    async def enqueue_summary(self, chat_id: int, user_id: int = None):
        """Add summary task to queue"""
        await self.db.add_task(
            task_type='send_summary',
            chat_id=chat_id,
            user_id=user_id,
            payload={"chat_id": chat_id}
        )
```

---

## 📋 Приоритезация (MVP roadmap)

### Phase 1: Core Infrastructure (Priority 1)
- [ ] `config.py` - Pydantic settings
- [ ] `core/db.py` - SQLite + FTS + task queue table
- [ ] `core/crypto.py` - AES-256 per-chat
- [ ] `core/llm.py` - OpenAI-compatible client
- [ ] `main.py` - FastAPI + Bot startup
- [ ] Database migrations

### Phase 2: Telegram Bot (Priority 1)
- [ ] `bot/handlers.py` - Message save, mention, private chat, delete tracking
- [ ] `bot/commands.py` - /stats, /export, /summarize_thread, /help
- [ ] `bot/scheduler.py` - APScheduler summary/coach/cleanup
- [ ] `core/rate_limiter.py` - asyncio.Queue with priorities

### Phase 3: Web API (Priority 1)
- [ ] `web/main.py` - FastAPI app + health check
- [ ] `web/middleware.py` - Auth, CORS, rate limiting
- [ ] `web/routes/auth.py` - Telegram OAuth + JWT
- [ ] `web/routes/chat.py` - SQL-agent + history search
- [ ] `web/routes/settings.py` - Chat settings modal
- [ ] `web/routes/admin.py` - Superadmin stats

### Phase 4: Skills (Priority 2)
- [ ] `skills/base.py` - Abstract Skill class
- [ ] `skills/summary.py` - Daily summary
- [ ] `skills/coach.py` - Communication coach
- [ ] `skills/thread_summary.py` - Thread summarization

### Phase 5: Security & Audit (Priority 1)
- [ ] `core/sql_agent.py` - Safe SQL validation
- [ ] Audit log implementation
- [ ] Input validation (Pydantic models)
- [ ] Rate limiting tests

### Phase 6: Polish & Deploy (Priority 2)
- [ ] `core/i18n.py` - Russian + English
- [ ] Error handling & logging
- [ ] Docker + docker-compose
- [ ] Tests

---

## ✅ Definition of Done

Каждый компонент должен иметь:
- ✅ Полная реализация (нет TODO, нет placeholders)
- ✅ Type hints (все функции)
- ✅ Docstrings (публичные функции)
- ✅ Error handling (try/except с логированием)
- ✅ Async/await везде (нет блокировок)
- ✅ Tests (базовые unit tests)
- ✅ Audit log (если действие требует)

---

## 🚀 Быстрый старт для агента

1. **Начни с Phase 1** - config, db, crypto
2. **Потом Phase 2** - bot handlers и scheduler
3. **Параллельно Phase 3** - web API endpoints
4. **Phase 4** - добавь skills
5. **Phase 5** - security + audit
6. **Phase 6** - polish + deploy

**Каждый файл должен быть полностью функциональным и готовым к использованию!**

---

**Версия:** 2.0 | **Статус:** Ready for Development | **Дата:** 2026-01-25
