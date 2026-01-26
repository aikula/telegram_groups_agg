# SECURITY_GUIDE.md

**Версия:** 1.0  
**Дата:** 2026-01-25  
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

---

## 1. Обзор безопасности

Этот проект разработан для корпоративного self-hosted использования с приватными данными чатов. Основные принципы безопасности:

- **Encryption at rest:** AES-256 per-chat шифрование всех сообщений
- **Access control:** RBAC - пользователь видит только свои чаты
- **Authentication:** Telegram OAuth + JWT для веб-интерфейса
- **SQL injection prevention:** Валидация и whitelist в SQL-агенте
- **Audit logging:** Все чувствительные операции логируются
- **Rate limiting:** Защита от abuse на уровне API и Telegram
- **No third-party data storage:** Все данные остаются на вашем сервере

---

## 2. Шифрование данных

### 2.1 Per-Chat Encryption

Каждый чат имеет уникальный ключ шифрования, производный от master key:

```python
# Генерация master key (делается ОДИН раз при развертывании)
import secrets
import base64

master_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
print(f"ENCRYPTION_MASTER_KEY={master_key}")
```

**Сохраните этот ключ в `.env` и НИКОГДА не коммитьте в git!**

### 2.2 Алгоритм шифрования

- **Алгоритм:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Библиотека:** `cryptography.fernet`
- **Ключ на чат:** `SHA256(master_key + chat_id)` → Base64

Пример:
```python
from cryptography.fernet import Fernet
from hashlib import sha256
import base64

def derive_chat_key(master_key: bytes, chat_id: int) -> bytes:
    key_material = sha256(master_key + str(chat_id).encode()).digest()
    return base64.urlsafe_b64encode(key_material)

# Шифрование
chat_key = derive_chat_key(master_key, -1001234567890)
f = Fernet(chat_key)
encrypted = f.encrypt(b"Hello world")

# Расшифровка
decrypted = f.decrypt(encrypted)
```

### 2.3 Что НЕ шифруется

- Метаданные: `user_id`, `chat_id`, `timestamp`, `message_id`
- Статистика: количество сообщений, членов чата
- Настройки чатов

Это необходимо для работы индексов и SQL-агента без расшифровки всей БД.

### 2.4 Ротация ключей (GDPR/удаление данных)

Для полного удаления данных чата:

```sql
-- 1. Удалить сообщения
DELETE FROM messages WHERE chat_id = ?;
DELETE FROM messages_fts WHERE chat_id = ?;

-- 2. Удалить связи
DELETE FROM chat_members WHERE chat_id = ?;
DELETE FROM chat_settings WHERE chat_id = ?;

-- 3. Soft delete чата
UPDATE chats SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?;

-- 4. Аудит
INSERT INTO audit_log (user_id, action, chat_id, details)
VALUES (NULL, 'gdpr_delete', ?, '{"reason": "user_request"}');
```

После этого ключ шифрования для чата становится бесполезным.

---

## 3. Аутентификация и авторизация

### 3.1 Telegram OAuth

Используется Telegram Login Widget для веб-интерфейса.

**Проверка подписи:**

```python
import hashlib
import hmac

def verify_telegram_auth(data: dict, bot_token: str) -> bool:
    # Verify Telegram OAuth signature
    check_hash = data.pop('hash')

    data_check_string = '\n'.join([
        f"{k}={v}" for k, v in sorted(data.items())
    ])

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return calculated_hash == check_hash
```

**ВАЖНО:** Всегда проверяйте `auth_date` (не старше 86400 секунд).

### 3.2 JWT Tokens

После успешной аутентификации выдаётся JWT токен:

```python
from jose import jwt
from datetime import datetime, timedelta

def create_jwt_token(user_id: int, is_superadmin: bool = False) -> str:
    payload = {
        "sub": str(user_id),
        "is_superadmin": is_superadmin,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
```

**Безопасность JWT:**
- Используйте длинный случайный `JWT_SECRET_KEY` (минимум 32 байта)
- Срок жизни: 7 дней по умолчанию
- Токен нельзя отозвать до истечения (для revocation нужен Redis/DB blacklist)

### 3.3 RBAC (Role-Based Access Control)

Три роли:

1. **User** - доступ только к своим чатам
2. **Chat Admin** - может экспортировать и настраивать чат
3. **Superadmin** - глобальная статистика без доступа к контенту

**Проверка доступа:**

```python
async def check_chat_access(user_id: int, chat_id: int) -> bool:
    # User must be a member of the chat
    result = await db.execute(
        "SELECT 1 FROM chat_members WHERE user_id = ? AND chat_id = ? AND left_at IS NULL",
        (user_id, chat_id)
    )
    return result.fetchone() is not None
```

### 3.4 Superadmin

Superadmin НЕ имеет доступа к содержимому чатов, только к:
- Агрегированной статистике (количество сообщений, токенов)
- Отправке уведомлений пользователям
- Audit log (но без содержимого сообщений)

**Создание superadmin пароля:**

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password_hash = pwd_context.hash("your_secure_password")
print(f"SUPERADMIN_PASSWORD_HASH={password_hash}")
```

Добавьте hash в `.env`.

---

## 4. SQL Injection Prevention

### 4.1 SQL-агент: многоуровневая защита

```python
class SafeSQLAgent:
    FORBIDDEN = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE", "EXEC", "PRAGMA"]

    def _is_safe(self, sql: str, chat_id: int) -> bool:
        sql_upper = sql.upper()

        # 1. Только SELECT
        if not sql_upper.strip().startswith("SELECT"):
            return False

        # 2. Запрещённые ключевые слова
        if any(kw in sql_upper for kw in self.FORBIDDEN):
            return False

        # 3. ОБЯЗАТЕЛЬНЫЙ WHERE chat_id = X
        chat_id_filter = f"chat_id = {chat_id}"
        if chat_id_filter not in sql.replace(" ", ""):
            return False

        # 4. Нет подстрок вида "; DROP" или "-- comment"
        if ";" in sql or "--" in sql:
            return False

        return True
```

### 4.2 Read-only соединение

Для SQL-агента используется отдельное read-only соединение к БД:

```python
import aiosqlite

async def execute_read_only(sql: str) -> list:
    # Execute SELECT with read-only connection
    async with aiosqlite.connect(
        settings.database_path,
        uri=True,
        timeout=5.0
    ) as db:
        # Read-only mode
        await db.execute("PRAGMA query_only = ON")

        cursor = await db.execute(sql)
        return await cursor.fetchall()
```

### 4.3 Примеры БЛОКИРУЕМЫХ запросов

```sql
-- ❌ Нет WHERE chat_id
SELECT * FROM messages LIMIT 10

-- ❌ UPDATE вместо SELECT
UPDATE messages SET content_encrypted = 'hacked' WHERE chat_id = 123

-- ❌ SQL injection попытка
SELECT * FROM messages WHERE chat_id = 123; DROP TABLE users; --

-- ❌ Доступ к другим чатам
SELECT * FROM messages WHERE chat_id IN (123, 456)
```

### 4.4 Примеры РАЗРЕШЁННЫХ запросов

```sql
-- ✅ Простой SELECT
SELECT COUNT(*) FROM messages WHERE chat_id = 123

-- ✅ С JOIN
SELECT u.username, COUNT(*) as msg_count 
FROM messages m 
JOIN users u ON m.user_id = u.id 
WHERE m.chat_id = 123 
GROUP BY u.username

-- ✅ С подзапросом (если нужен)
SELECT AVG(msg_count) FROM (
  SELECT COUNT(*) as msg_count 
  FROM messages 
  WHERE chat_id = 123 
  GROUP BY DATE(timestamp)
)
```

---

## 5. Rate Limiting

### 5.1 API Rate Limits

Реализация через `slowapi`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/chat/query")
@limiter.limit("30/minute")
async def sql_agent_query(request: Request, ...):
    ...
```

**Лимиты по эндпоинтам:**

| Эндпоинт          | Лимит         | Причина                           |
|-------------------|---------------|-----------------------------------|
| `/auth/*`         | 5/min         | Защита от brute-force             |
| `/chat/query`     | 30/min        | Дорогие LLM вызовы                |
| `/chat/*/history` | 60/min        | Защита от data scraping           |
| `/settings/*`     | 10/min        | Редкие операции                   |
| `/admin/*`        | 100/min       | Superadmin, но всё равно limit    |

### 5.2 Telegram Rate Limits

Telegram API имеет жёсткие лимиты:
- **Глобально:** 30 сообщений/сек для всего бота
- **Per-chat:** 1 сообщение/сек в одном чате
- **Per-user (PM):** 1 сообщение/сек

**Реализация через asyncio.Queue:**

```python
import asyncio
from collections import defaultdict

class TelegramRateLimiter:
    def __init__(self, global_rate: int = 30, per_chat_rate: float = 1.0):
        self.global_queue = asyncio.Queue()
        self.chat_queues = defaultdict(asyncio.Queue)
        self.global_rate = global_rate
        self.per_chat_rate = per_chat_rate

    async def send_message(self, chat_id: int, text: str):
        # Add to chat-specific queue
        await self.chat_queues[chat_id].put((chat_id, text))

        # Process with rate limiting
        await asyncio.sleep(self.per_chat_rate)
        _, msg = await self.chat_queues[chat_id].get()

        # Send via bot API
        await bot.send_message(chat_id, msg)
```

---

## 6. Audit Logging

### 6.1 Что логируется

Все чувствительные операции записываются в `audit_log`:

```python
async def audit_log(
    user_id: int | None,  # None для system actions
    action: str,
    chat_id: int | None = None,
    details: dict | None = None
):
    await db.execute(
        "INSERT INTO audit_log (user_id, action, chat_id, details, timestamp) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (user_id, action, chat_id, json.dumps(details) if details else None)
    )
```

**Типы действий:**
- `sql_query` - выполнен SQL-агент запрос
- `sql_query_blocked` - заблокирован небезопасный SQL
- `export_chat` - экспорт истории чата
- `update_settings` - изменение настроек чата
- `admin_notify` - superadmin отправил уведомление
- `gdpr_delete` - удаление данных пользователя

### 6.2 Retention политика

Audit log хранится **бессрочно** (или согласно корпоративной политике).

Для очистки старых записей:

```sql
-- Удалить записи старше 1 года
DELETE FROM audit_log WHERE timestamp < datetime('now', '-1 year');
```

### 6.3 Мониторинг подозрительной активности

Примеры запросов для детекции:

```sql
-- Частые неудачные SQL-запросы одного пользователя
SELECT user_id, COUNT(*) as failed_count
FROM audit_log
WHERE action = 'sql_query_blocked'
  AND timestamp > datetime('now', '-1 hour')
GROUP BY user_id
HAVING failed_count > 10;

-- Массовый экспорт чатов
SELECT user_id, COUNT(DISTINCT chat_id) as exported_chats
FROM audit_log
WHERE action = 'export_chat'
  AND timestamp > datetime('now', '-1 day')
GROUP BY user_id
HAVING exported_chats > 5;
```

---

## 7. Input Validation

### 7.1 Pydantic Models

Все входные данные валидируются через Pydantic:

```python
from pydantic import BaseModel, validator, Field

class ChatQueryRequest(BaseModel):
    chat_id: int = Field(..., ge=-9999999999999, le=-1)
    question: str = Field(..., min_length=3, max_length=500)

    @validator('question')
    def question_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Question cannot be empty')
        return v.strip()
```

### 7.2 XSS Protection

FastAPI автоматически экранирует HTML в JSON responses.

Для Jinja2 templates:

```html
<!-- Автоматическое экранирование -->
<p>{{ user_message }}</p>

<!-- Явное экранирование (если нужно) -->
<p>{{ user_message | e }}</p>
```

### 7.3 Path Traversal Protection

При экспорте файлов:

```python
import os
from pathlib import Path

def safe_export_path(chat_id: int) -> Path:
    # Generate safe file path for export
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)

    safe_filename = f"export_{abs(chat_id)}_{int(time.time())}.txt"

    full_path = (export_dir / safe_filename).resolve()
    if not str(full_path).startswith(str(export_dir.resolve())):
        raise ValueError("Path traversal attempt detected")

    return full_path
```

---

## 8. Secrets Management

### 8.1 .env файл

**НИКОГДА не коммитьте `.env` в git!**

Добавьте в `.gitignore`:
```
.env
.env.local
.env.production
*.key
*.pem
```

### 8.2 Генерация секретов

```bash
# Master encryption key (32 bytes)
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

# JWT secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Superadmin password hash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('YOUR_PASSWORD'))"
```

### 8.3 Пример .env

```env
# === Telegram ===
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# === LLM ===
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
LLM_MODEL_NAME=anthropic/claude-3.5-sonnet

# === Security (GENERATE NEW KEYS!) ===
ENCRYPTION_MASTER_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
JWT_SECRET_KEY=YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
SUPERADMIN_PASSWORD_HASH=$2b$12$ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ

# === Database ===
DATABASE_URL=sqlite+aiosqlite:///./data/chat_data.db
DATABASE_PATH=data/chat_data.db

# === Server ===
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

---

## 9. HTTPS и Network Security

### 9.1 Обязательно HTTPS в production

Используйте Let's Encrypt + Nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 9.2 CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 10. Backup и Recovery

### 10.1 Backup Strategy

**Ежедневный backup БД:**

```bash
#!/bin/bash
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_PATH="data/chat_data.db"

sqlite3 $DB_PATH ".backup $BACKUP_DIR/chat_data_$TIMESTAMP.db"
gzip $BACKUP_DIR/chat_data_$TIMESTAMP.db

# Encrypt backup
gpg --symmetric --cipher-algo AES256 --batch --yes --passphrase-file /root/.backup_passphrase $BACKUP_DIR/chat_data_$TIMESTAMP.db.gz

# Remove old backups (keep 30 days)
find $BACKUP_DIR -name "chat_data_*.db.gz.gpg" -mtime +30 -delete
```

---

## 11. Compliance

### 11.1 GDPR

**Права пользователя:**
- **Right to access:** экспорт своих данных через `/export`
- **Right to erasure:** полное удаление данных чата
- **Right to rectification:** изменение данных профиля

**Реализация "Right to be forgotten":**

```python
async def gdpr_delete_user_data(user_id: int):
    # Complete user data deletion

    chats = await db.get_user_chats(user_id)

    for chat in chats:
        await db.execute(
            "DELETE FROM messages WHERE user_id = ? AND chat_id = ?",
            (user_id, chat.id)
        )

    await db.execute("DELETE FROM chat_members WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    await audit_log(None, "gdpr_delete", None, {"deleted_user_id": user_id})
```

### 11.2 Data Retention

По умолчанию: **90 дней** (`RETENTION_DAYS=90`).

---

## 12. Security Checklist

### Перед деплоем в production:

- [ ] Сгенерированы уникальные секреты
- [ ] `.env` добавлен в `.gitignore`
- [ ] HTTPS настроен с валидным сертификатом
- [ ] Firewall разрешает только 443 и 22 порты
- [ ] SQLite файл не доступен через веб
- [ ] Superadmin пароль достаточно сложный (>16 символов)
- [ ] Rate limiting включен на всех эндпоинтах
- [ ] CORS настроен с конкретными origins (не `*`)
- [ ] Backup скрипт настроен и протестирован
- [ ] Audit log мониторится
- [ ] DEBUG=false в production
- [ ] SQL-агент протестирован на injection
- [ ] Dependencies обновлены
- [ ] Retention policy настроена

---

**Версия:** 1.0 | **Статус:** Ready for Production | **Дата:** 2026-01-25
