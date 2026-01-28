# DATABASE_SCHEMA.md

**Версия:** 1.0  
**Дата:** 2026-01-25  
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

***

## 1. Общие решения по БД

- **Движок по умолчанию:** SQLite 3, файл `data/chat_data.db`.  
- **FTS:** SQLite FTS5 с токенизатором `unicode61 remove_diacritics 2` для нормального поиска по кириллице и латинице без диакритик. [sqlite](https://www.sqlite.org/fts5.html)
- **Готовность к PostgreSQL:** SQL максимально стандартный, без SQLite‑специфичных типов; FTS и триггеры изолированы, чтобы можно было заменить FTS на PostgreSQL `tsvector`/GIN.  
- **Шифрование:** только поле `messages.content_encrypted` (ciphertext), расшифровка на уровне приложения.  
- **Soft delete:** для чатов и сообщений вместо физического удаления используются флаги и `deleted_at`, кроме случаев GDPR/полного дропа чата.  
- **Время:** все timestamps в UTC (`TIMESTAMP`), конвертация на таймзоны — в приложении.

***

## 2. Таблицы

### 2.1 `users`

Хранит Telegram‑пользователей, которые хоть раз пересекались с ботом.

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,          -- Telegram user_id
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT DEFAULT 'ru',
    is_superadmin BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Поле          | Тип      | Описание                                  |
|---------------|----------|-------------------------------------------|
| `id`          | INTEGER  | Telegram `user_id`, PK                    |
| `username`    | TEXT     | Telegram username                         |
| `first_name`  | TEXT     | Имя                                       |
| `last_name`   | TEXT     | Фамилия                                   |
| `language_code` | TEXT   | Предпочитаемый язык (`ru`/`en` и т.п.)    |
| `is_superadmin` | BOOLEAN| Флаг суперадмина веб‑панели               |
| `created_at`  | TIMESTAMP| Время первого появления пользователя      |

***

### 2.2 `chats`

Телеграм‑чаты (группы/супергруппы), куда добавлен бот.

```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY,          -- Telegram chat_id
    title TEXT NOT NULL,
    type TEXT NOT NULL,              -- 'group', 'supergroup'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP             -- Soft delete при удалении бота
);
```

| Поле        | Тип       | Описание                                      |
|-------------|-----------|-----------------------------------------------|
| `id`        | INTEGER   | Telegram `chat_id`, PK                        |
| `title`     | TEXT      | Название чата                                 |
| `type`      | TEXT      | Тип (`group`, `supergroup`)                   |
| `created_at`| TIMESTAMP | Когда чат впервые увиден ботом                |
| `deleted_at`| TIMESTAMP | Когда бот был удалён / чат деактивирован      |

***

### 2.3 `chat_members`

Связь пользователей и чатов, с ролями и историей входа/выхода.

```sql
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
```

| Поле       | Тип       | Описание                                        |
|------------|-----------|-------------------------------------------------|
| `chat_id`  | INTEGER   | FK → `chats.id`                                 |
| `user_id`  | INTEGER   | FK → `users.id`                                 |
| `role`     | TEXT      | Роль в чате (`admin`/`member`)                  |
| `joined_at`| TIMESTAMP | Когда пользователь присоединился к чату        |
| `left_at`  | TIMESTAMP | Когда вышел; `NULL` — ещё в чате                |

***

### 2.4 `messages`

Все сообщения чатов (шифрованный текст).

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,     -- Telegram message_id
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content_encrypted TEXT,          -- зашифрованный текст
    timestamp TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT 0,
    deleted_at TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (chat_id, message_id)
);
```

| Поле              | Тип       | Описание                                         |
|-------------------|-----------|--------------------------------------------------|
| `id`              | INTEGER   | Внутренний PK                                    |
| `message_id`      | INTEGER   | Оригинальный Telegram `message_id`              |
| `chat_id`         | INTEGER   | FK → `chats.id`                                  |
| `user_id`         | INTEGER   | FK → `users.id`                                  |
| `content_encrypted` | TEXT    | Зашифрованное содержимое сообщения              |
| `timestamp`       | TIMESTAMP | Время отправки сообщения                         |
| `is_deleted`      | BOOLEAN   | Пометка об удалении сообщения                   |
| `deleted_at`      | TIMESTAMP | Когда было удалено (если применимо)             |

***

### 2.5 `messages_fts` (FTS5)

FTS‑индекс по расшифрованному тексту сообщений.  
Хранит только denormalized копию `content` для поиска.

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    message_id UNINDEXED,
    chat_id UNINDEXED,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

| Поле        | Тип     | Описание                               |
|-------------|---------|----------------------------------------|
| `message_id`| INTEGER | FK логически → `messages.message_id`   |
| `chat_id`   | INTEGER | Логически → `messages.chat_id`         |
| `content`   | TEXT    | Открытый текст сообщения для поиска    |

> **Синхронизация:** через триггеры (`AFTER INSERT/UPDATE/DELETE` на `messages`) FTS‑таблица поддерживается в актуальном состоянии.

***

### 2.6 `chat_settings`

Перс‑настройки для каждого чата: суммаризации, коучинг, язык.

```sql
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
```

| Поле                 | Тип      | Описание                                             |
|----------------------|----------|------------------------------------------------------|
| `chat_id`            | INTEGER  | FK → `chats.id`, PK                                  |
| `summary_enabled`    | BOOLEAN  | Включена ли ежедневная сводка                       |
| `summary_time_local` | TEXT     | Локальное время отправки (формат `HH:MM`)           |
| `summary_timezone`   | TEXT     | Таймзона чата (`Europe/Moscow` и т.п.)              |
| `summary_custom_prompt` | TEXT  | Кастомный промпт для суммаризации                   |
| `summary_target`     | TEXT     | Куда слать сводку (`chat`, `bot`, `disabled`)       |
| `coach_enabled`      | BOOLEAN  | Включен ли коучинг                                  |
| `coach_custom_prompt`| TEXT     | Кастомный промпт для коучинга                       |
| `coach_target`       | TEXT     | Куда слать коуч‑сообщения                           |
| `language`           | TEXT     | Язык для LLM/интерфейса (`ru`/`en` и т.п.)           |

***

### 2.7 `llm_usage`

Учёт токенов и стоимости по навыкам и пользователям.

```sql
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
```

| Поле              | Тип       | Описание                                 |
|-------------------|-----------|------------------------------------------|
| `id`              | INTEGER   | PK                                       |
| `user_id`         | INTEGER   | FK → `users.id` (инициатор запроса)     |
| `chat_id`         | INTEGER   | FK → `chats.id`                          |
| `skill`           | TEXT      | Имя скилла (`summary`, `sql_agent`, ...) |
| `tokens_prompt`   | INTEGER   | Токены промпта                           |
| `tokens_completion` | INTEGER | Токены ответа                            |
| `cost_usd`        | REAL      | Оценочная стоимость                      |
| `timestamp`       | TIMESTAMP | Когда вызван LLM                         |

***

### 2.8 `audit_log`

Аудит чувствительных операций (SQL‑агент, экспорт, настройки, админ‑уведомления).

```sql
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
```

| Поле       | Тип       | Описание                                      |
|------------|-----------|-----------------------------------------------|
| `id`       | INTEGER   | PK                                            |
| `user_id`  | INTEGER   | FK → `users.id` или `NULL` для системных     |
| `action`   | TEXT      | Тип действия                                  |
| `chat_id`  | INTEGER   | FK → `chats.id` (если применимо)             |
| `details`  | TEXT      | JSON с параметрами/контекстом                 |
| `timestamp`| TIMESTAMP | Время события                                 |

***

### 2.9 `task_queue`

Очередь фоновых задач (замена Celery/Redis, чисто на SQLite).

```sql
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
```

| Поле          | Тип       | Описание                                      |
|---------------|-----------|-----------------------------------------------|
| `id`          | INTEGER   | PK                                            |
| `task_type`   | TEXT      | Тип задачи (`send_summary`, `cleanup`, ...)  |
| `chat_id`     | INTEGER   | FK → `chats.id` (если задача привязана к чату) |
| `user_id`     | INTEGER   | FK → `users.id` (инициатор или получатель)   |
| `payload`     | TEXT      | JSON‑параметры задачи                         |
| `status`      | TEXT      | Статус (`pending`/`processing`/`completed`/`failed`) |
| `retry_count` | INTEGER   | Текущее число ретраев                         |
| `max_retries` | INTEGER   | Лимит ретраев                                 |
| `error_message` | TEXT    | Последняя ошибка                              |
| `created_at`  | TIMESTAMP | Когда задача поставлена                       |
| `started_at`  | TIMESTAMP | Когда обработка началась                      |
| `completed_at`| TIMESTAMP | Когда обработка завершилась                   |

***

## 3. Индексы

```sql
-- Messages
CREATE INDEX idx_messages_chat_time ON messages(chat_id, timestamp DESC);
CREATE INDEX idx_messages_user ON messages(user_id);
CREATE INDEX idx_messages_deleted ON messages(is_deleted, deleted_at);

-- Chat members
CREATE INDEX idx_chat_members_user ON chat_members(user_id);
CREATE INDEX idx_chat_members_active ON chat_members(user_id, left_at);

-- LLM usage
CREATE INDEX idx_llm_usage_chat ON llm_usage(chat_id, timestamp);
CREATE INDEX idx_llm_usage_user ON llm_usage(user_id, timestamp);

-- Audit log
CREATE INDEX idx_audit_log_user ON audit_log(user_id, timestamp);
CREATE INDEX idx_audit_log_chat ON audit_log(chat_id, timestamp);

-- Task queue
CREATE INDEX idx_task_queue_status ON task_queue(status, created_at);
```

***

## 4. FTS и триггеры

### 4.1 Создание FTS‑таблицы

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    message_id UNINDEXED,
    chat_id UNINDEXED,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

Опция `remove_diacritics 2` удаляет диакритики с латинских символов, делая поиск по акцентированным и неакцентированным формам эквивалентным. [sqlite](https://www.sqlite.org/fts5.html)

### 4.2 Триггеры синхронизации

```sql
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts (message_id, chat_id, content)
    VALUES (
        NEW.message_id,
        NEW.chat_id,
        -- сюда приложение подставляет уже расшифрованный текст
        NEW.content_decrypted_placeholder
    );
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts
    WHERE message_id = OLD.message_id AND chat_id = OLD.chat_id;
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts
    WHERE message_id = OLD.message_id AND chat_id = OLD.chat_id;
    INSERT INTO messages_fts (message_id, chat_id, content)
    VALUES (
        NEW.message_id,
        NEW.chat_id,
        NEW.content_decrypted_placeholder
    );
END;
```

> В реальном коде расшифровка и вставка в FTS выполняется приложением; здесь триггеры показаны как логическая схема.

***

## 5. Ограничения безопасности на уровне схемы

- Нет `ON DELETE CASCADE` на `users` для `messages`/`llm_usage`/`audit_log`, чтобы не потерять связность аудита; удаление реализуется логически.  
- SQL‑агент работает только через read‑only соединение и использует только `SELECT` по этой схеме; DML/DDL не предусмотрены.  
- FTS‑таблица не содержит персональных идентификаторов кроме `chat_id`/`message_id`, чтобы при необходимости можно было пересобрать индекс после смены ключей шифрования.

***

## 6. Готовность к миграции в PostgreSQL

Для перехода на PostgreSQL:

- Заменить `database_url` на PostgreSQL DSN, подключить async‑движок SQLAlchemy.  
- Реализовать FTS на базе `tsvector`/GIN, FTS‑таблицу вынести в отдельный модуль миграции.  
- Типы `BOOLEAN`/`TIMESTAMP` маппятся на стандартные PostgreSQL типы без изменений.  
- Триггеры FTS переписать на PL/pgSQL, но логика (INSERT/UPDATE/DELETE) остаётся той же.  

Эта схема — **единственный источник правды** по структуре БД; дубли в других файлах должны ссылаться сюда.