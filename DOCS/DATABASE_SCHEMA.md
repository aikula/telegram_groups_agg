# DATABASE_SCHEMA.md

**Версия:** 2.0  
**Дата:** 2026-01-28  
**СУБД:** SQLite 3.x (с миграцией на PostgreSQL в будущем)

---

## 1. Обзор

База данных хранит:
- **Пользователей** (нормализованная таблица)
- **Чаты** и их участников
- **Сообщения** (зашифрованные, per-chat encryption)
- **Настройки чатов** (enabled skills, расписание)
- **LLM usage** (мониторинг затрат)
- **Audit log** (безопасность)

### Ключевые принципы

1. **Нормализация:** Пользователи хранятся отдельно, messages ссылаются на user_id
2. **Шифрование:** Содержимое сообщений шифруется per-chat ключом
3. **Безопасность:** Audit log для всех чувствительных операций
4. **Производительность:** Индексы на частые запросы
5. **Без FTS5:** Полнотекстовый поиск отложен до миграции на PostgreSQL

---

## 2. ER-диаграмма

```
users (1) ──────── (*) chat_members (*) ──────── (1) chats
  │                                                   │
  │ (1)                                               │ (1)
  │                                                   │
  └──────────── (*) messages                          │
                      │                               │
                      └───────────────────────────────┘

                chats (1) ──────── (1) chat_settings

llm_usage, audit_log (отдельные таблицы с FK на users/chats)
```

---

## 3. Таблицы

### 3.1 users

**Назначение:** Хранение информации о пользователях Telegram.

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    language_code TEXT DEFAULT 'ru',
    is_web_admin BOOLEAN DEFAULT 0,
    is_bot BOOLEAN DEFAULT 0,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_last_seen ON users(last_seen DESC);
```

**Пример:**

| id | username | full_name | is_web_admin |
|----|----------|-----------|--------------|
| 123456789 | vitya | Виктор | 0 |
| 987654321 | admin | Админ | 1 |

---

### 3.2 chats

**Назначение:** Информация о Telegram чатах.

```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE NOT NULL,
    title TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    description TEXT,
    invite_link TEXT,
    member_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_chats_chat_id ON chats(chat_id);
```

---

### 3.3 chat_members

**Назначение:** Участники чатов с ролями.

```sql
CREATE TABLE chat_members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    can_manage_chat BOOLEAN DEFAULT 0,
    can_delete_messages BOOLEAN DEFAULT 0,
    can_restrict_members BOOLEAN DEFAULT 0,
    can_invite_users BOOLEAN DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_chat_members_chat ON chat_members(chat_id);
CREATE INDEX idx_chat_members_user ON chat_members(user_id);
```

---

### 3.4 messages

**Назначение:** Сообщения чатов (зашифрованные).

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    reply_to_message_id INTEGER,
    is_deleted BOOLEAN DEFAULT 0,
    is_edited BOOLEAN DEFAULT 0,
    timestamp TIMESTAMP NOT NULL,
    edited_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (chat_id, message_id)
);

CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
CREATE INDEX idx_messages_user_time ON messages(user_id, timestamp DESC);
CREATE INDEX idx_messages_chat_user ON messages(chat_id, user_id);
```

**Пример запроса (с расшифровкой):**

```sql
SELECT 
    m.id,
    m.timestamp,
    m.content_encrypted,
    u.username,
    u.full_name
FROM messages m
JOIN users u ON m.user_id = u.id
WHERE m.chat_id = ? 
    AND m.is_deleted = 0
ORDER BY m.timestamp DESC
LIMIT 20;
```

---

### 3.5 chat_settings

**Назначение:** Настройки чатов (включая Skills).

```sql
CREATE TABLE chat_settings (
    chat_id INTEGER PRIMARY KEY,
    enabled_skills TEXT DEFAULT '["summary","coach","qa","analytics"]',
    summary_time TEXT DEFAULT '16:00',
    summary_timezone TEXT DEFAULT 'Europe/Moscow',
    summary_days INTEGER DEFAULT 7,
    language TEXT DEFAULT 'ru',
    date_format TEXT DEFAULT '%Y-%m-%d',
    llm_model TEXT,
    llm_temperature REAL DEFAULT 0.7,
    auto_summary_enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

**Использование enabled_skills:**

```python
import json

settings = await db.fetchone(
    "SELECT enabled_skills FROM chat_settings WHERE chat_id = ?",
    (chat_id,)
)
skills = json.loads(settings['enabled_skills'])
is_analytics_enabled = 'analytics' in skills
```

---

### 3.6 llm_usage

**Назначение:** Мониторинг использования LLM.

```sql
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    skill TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_prompt INTEGER NOT NULL,
    tokens_completion INTEGER NOT NULL,
    cost_usd REAL,
    response_time_ms INTEGER,
    success BOOLEAN DEFAULT 1,
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
);

CREATE INDEX idx_llm_usage_chat ON llm_usage(chat_id, timestamp);
CREATE INDEX idx_llm_usage_timestamp ON llm_usage(timestamp DESC);
```

**Аналитика:**

```sql
-- Затраты по чатам за месяц
SELECT 
    c.title,
    COUNT(*) as requests,
    SUM(l.tokens_prompt + l.tokens_completion) as total_tokens,
    SUM(l.cost_usd) as total_cost
FROM llm_usage l
JOIN chats c ON l.chat_id = c.id
WHERE l.timestamp > datetime('now', '-30 days')
GROUP BY l.chat_id
ORDER BY total_cost DESC;
```

---

### 3.7 audit_log

**Назначение:** Логирование чувствительных операций.

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    chat_id INTEGER,
    details TEXT,
    success BOOLEAN DEFAULT 1,
    error_message TEXT,
    ip_address TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_log_user ON audit_log(user_id, timestamp);
CREATE INDEX idx_audit_log_action ON audit_log(action, timestamp);
```

**Типы action:**
- `sql_query_executed`
- `skill_toggled`
- `chat_exported`
- `web_login`
- `settings_changed`

---

## 4. Шифрование

### 4.1 Per-Chat Encryption

```python
from cryptography.fernet import Fernet
import hashlib
import base64

class ChatCrypto:
    def __init__(self, master_key: str):
        self.master_key = base64.urlsafe_b64decode(master_key)

    def derive_chat_key(self, chat_id: int) -> bytes:
        data = self.master_key + str(chat_id).encode()
        key_material = hashlib.sha256(data).digest()
        return base64.urlsafe_b64encode(key_material)

    def encrypt(self, chat_id: int, plaintext: str) -> str:
        key = self.derive_chat_key(chat_id)
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode('ascii')

    def decrypt(self, chat_id: int, ciphertext: str) -> str:
        key = self.derive_chat_key(chat_id)
        f = Fernet(key)
        return f.decrypt(ciphertext.encode('ascii')).decode('utf-8')
```

---

## 5. Миграции

### 5.1 Версионирование

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES (1);
```

### 5.2 Пример миграции

```python
async def migrate_v1_to_v2(db):
    version = await db.fetchone("SELECT MAX(version) FROM schema_version")

    if version['MAX(version)'] < 2:
        await db.execute(
            "ALTER TABLE chat_settings ADD COLUMN llm_model TEXT"
        )
        await db.execute("INSERT INTO schema_version (version) VALUES (2)")
        await db.commit()
```

---

## 6. Индексы

### Ключевые индексы для производительности

```sql
-- Messages (самая большая таблица)
CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
CREATE INDEX idx_messages_user_time ON messages(user_id, timestamp DESC);
CREATE INDEX idx_messages_chat_user ON messages(chat_id, user_id);

-- LLM Usage
CREATE INDEX idx_llm_usage_chat ON llm_usage(chat_id, timestamp);
CREATE INDEX idx_llm_usage_timestamp ON llm_usage(timestamp DESC);

-- Audit Log
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
```

---

## 7. Data Retention

```python
async def cleanup_old_data():
    retention_days = settings.RETENTION_DAYS
    cutoff_date = datetime.now() - timedelta(days=retention_days)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff_date,)
        )

        audit_cutoff = datetime.now() - timedelta(days=365)
        await db.execute(
            "DELETE FROM audit_log WHERE timestamp < ?",
            (audit_cutoff,)
        )

        await db.commit()
        await db.execute("VACUUM")
```

**Scheduled:**

```python
@scheduler.scheduled_job('cron', hour=3, minute=0)
async def daily_cleanup():
    await cleanup_old_data()
```

---

## 8. Backup & Restore

### Backup

```bash
#!/bin/bash
DB_PATH="data/chat_data.db"
BACKUP_DIR="backups"
DATE=$(date +%Y%m%d_%H%M%S)

sqlite3 $DB_PATH ".backup ${BACKUP_DIR}/chat_data_${DATE}.db"
gzip ${BACKUP_DIR}/chat_data_${DATE}.db

find ${BACKUP_DIR} -name "*.db.gz" -mtime +30 -delete
```

### Restore

```bash
#!/bin/bash
BACKUP_FILE=$1

gunzip -c $BACKUP_FILE > /tmp/restore.db
docker-compose stop
mv data/chat_data.db data/chat_data.db.old
mv /tmp/restore.db data/chat_data.db
docker-compose start
```

---

## 9. Миграция на PostgreSQL (v2.2)

### FTS в PostgreSQL

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT NOT NULL,
    content_fts TSVECTOR,
    timestamp TIMESTAMP NOT NULL
);

CREATE INDEX idx_messages_fts ON messages USING GIN(content_fts);

-- Автоматическое обновление FTS
CREATE TRIGGER messages_fts_update 
BEFORE INSERT OR UPDATE ON messages
FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(content_fts, 'pg_catalog.russian', content_encrypted);

-- Поиск
SELECT * FROM messages 
WHERE chat_id = 1 
    AND content_fts @@ to_tsquery('russian', 'дедлайн & проект');
```

---

## 10. Заключение

### Основные характеристики

- **Таблицы:** 7 основных
- **Индексы:** 20+ для производительности
- **Шифрование:** AES-256 per-chat
- **Retention:** 90 дней по умолчанию
- **Backup:** Ежедневно

### Что обеспечивает схема

✅ **Нормализацию** - users отдельно от messages  
✅ **Безопасность** - шифрование + audit log  
✅ **Производительность** - правильные индексы  
✅ **Масштабируемость** - готовность к PostgreSQL  
✅ **Мониторинг** - LLM usage tracking  
✅ **Гибкость** - JSON для skills настроек  

---

**Версия:** 2.0 | **Дата:** 2026-01-28 | **СУБД:** SQLite 3.x
