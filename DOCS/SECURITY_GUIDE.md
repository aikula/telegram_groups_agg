# SECURITY_GUIDE.md

**Версия:** 2.0  
**Дата:** 2026-01-28  
**Статус:** Production-Ready

---

## 1. Обзор безопасности

Telegram Chat Analytics Bot обрабатывает чувствительные данные, поэтому безопасность критична.

### Основные принципы

🔐 **Defense in Depth** - многоуровневая защита  
🔑 **Principle of Least Privilege** - минимальные права  
📊 **Audit Everything** - логирование всех действий  
🛡️ **Encryption at Rest** - шифрование данных  
🚨 **Fail Secure** - безопасный отказ при ошибках  

---

## 2. Шифрование данных

### 2.1 Per-Chat Encryption

Каждый чат шифруется уникальным ключом, производным от мастер-ключа.

```python
from cryptography.fernet import Fernet
import hashlib
import base64

class ChatCrypto:
    def __init__(self, master_key: str):
        if not master_key:
            raise ValueError("MASTER_ENCRYPTION_KEY not set")

        self.master_key = base64.urlsafe_b64decode(master_key)

        if len(self.master_key) != 32:
            raise ValueError("Master key must be 32 bytes")

    def derive_chat_key(self, chat_id: int) -> bytes:
        data = self.master_key + str(chat_id).encode('utf-8')
        key_material = hashlib.sha256(data).digest()
        return base64.urlsafe_b64encode(key_material)

    def encrypt(self, chat_id: int, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")

        key = self.derive_chat_key(chat_id)
        f = Fernet(key)
        ciphertext = f.encrypt(plaintext.encode('utf-8'))
        return ciphertext.decode('ascii')

    def decrypt(self, chat_id: int, ciphertext: str) -> str:
        if not ciphertext:
            raise ValueError("Cannot decrypt empty string")

        try:
            key = self.derive_chat_key(chat_id)
            f = Fernet(key)
            plaintext = f.decrypt(ciphertext.encode('ascii'))
            return plaintext.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed for chat {chat_id}")
            raise
```

### 2.2 Генерация мастер-ключа

```bash
# Генерация нового ключа (выполнить ОДИН РАЗ)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Результат (пример):
# hN6p3RlK4Qm9Xw2Yv8Zt5Bf7Cg1Dj0Ek6Lh3Mn4Op2Qr==

# Добавить в .env:
MASTER_ENCRYPTION_KEY=hN6p3RlK4Qm9Xw2Yv8Zt5Bf7Cg1Dj0Ek6Lh3Mn4Op2Qr==
```

**⚠️ КРИТИЧНО:**
- Генерируйте ключ ОДИН РАЗ
- Храните в `.env` (добавьте в `.gitignore`)
- Backup в защищенном месте (1Password, Vault)
- При утере ключа данные НЕВОССТАНОВИМЫ

---

## 3. Аутентификация

### 3.1 Telegram 2FA (OTP)

```python
import secrets
import hashlib
from datetime import datetime, timedelta

class OTPManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.OTP_LENGTH = 6
        self.OTP_TTL = 300  # 5 минут
        self.MAX_ATTEMPTS = 3

    def generate_otp(self, telegram_id: int) -> str:
        otp = ''.join(secrets.choice('0123456789') for _ in range(self.OTP_LENGTH))

        # Хешируем перед сохранением
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()

        key = f"otp:{telegram_id}"
        self.redis.setex(key, self.OTP_TTL, otp_hash)

        attempts_key = f"otp_attempts:{telegram_id}"
        self.redis.setex(attempts_key, self.OTP_TTL, 0)

        return otp

    async def verify_otp(self, telegram_id: int, otp: str) -> bool:
        key = f"otp:{telegram_id}"
        attempts_key = f"otp_attempts:{telegram_id}"

        attempts = int(self.redis.get(attempts_key) or 0)
        if attempts >= self.MAX_ATTEMPTS:
            return False

        self.redis.incr(attempts_key)

        stored_hash = self.redis.get(key)
        if not stored_hash:
            return False

        otp_hash = hashlib.sha256(otp.encode()).hexdigest()

        if secrets.compare_digest(stored_hash.decode(), otp_hash):
            self.redis.delete(key)
            self.redis.delete(attempts_key)
            return True

        return False
```

### 3.2 JWT Tokens

```python
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

class JWTManager:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.ACCESS_TOKEN_EXPIRE = timedelta(days=7)

    def create_access_token(self, telegram_id: int) -> str:
        expire = datetime.utcnow() + self.ACCESS_TOKEN_EXPIRE

        payload = {
            "sub": str(telegram_id),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> int:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            telegram_id = int(payload.get("sub"))

            if not telegram_id:
                raise JWTError("Invalid payload")

            return telegram_id
        except JWTError as e:
            raise HTTPException(401, f"Invalid token: {e}")
```

### 3.3 Rate Limiting на Auth

```python
from fastapi import HTTPException

@app.post("/api/auth/request-otp")
async def request_otp(telegram_id: int):
    # Rate limiting: 3 запроса в минуту
    rate_key = f"otp_rate:{telegram_id}"
    count = redis.get(rate_key)

    if count and int(count) >= 3:
        raise HTTPException(429, "Too many requests. Wait 1 minute.")

    redis.incr(rate_key)
    redis.expire(rate_key, 60)

    otp = otp_manager.generate_otp(telegram_id)
    await send_otp_to_telegram(telegram_id, otp)

    return {"message": "OTP sent"}
```

---

## 4. Защита от атак

### 4.1 SQL Injection

**✅ ВСЕГДА параметризованные запросы:**

```python
# ✅ ПРАВИЛЬНО
chat_id = 123
rows = await db.execute(
    "SELECT * FROM messages WHERE chat_id = ?",
    (chat_id,)
)

# ❌ НЕПРАВИЛЬНО - SQL Injection!
rows = await db.execute(f"SELECT * FROM messages WHERE chat_id = {chat_id}")
```

**SQL Validator для Analytics Skill:**

```python
import sqlparse

class SQLValidator:
    ALLOWED_COMMANDS = {'SELECT'}
    FORBIDDEN_KEYWORDS = {
        'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 
        'CREATE', 'TRUNCATE', 'REPLACE'
    }

    def validate(self, query: str) -> tuple[bool, str]:
        parsed = sqlparse.parse(query)

        if not parsed:
            return False, "Empty query"

        query_upper = query.upper()
        for forbidden in self.FORBIDDEN_KEYWORDS:
            if forbidden in query_upper:
                return False, f"Forbidden: {forbidden}"

        if '--' in query or '/*' in query:
            return False, "Comments not allowed"

        return True, "Valid"

validator = SQLValidator()

async def execute_user_query(query: str, chat_id: int):
    is_valid, error = validator.validate(query)
    if not is_valid:
        raise ValueError(f"Invalid query: {error}")

    if 'LIMIT' not in query.upper():
        query += ' LIMIT 100'

    result = await db.execute(query)
    return await result.fetchall()
```

### 4.2 Command Injection

```python
import re
import subprocess

def sanitize_filename(filename: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', filename)

    if not safe:
        raise ValueError("Invalid filename")

    return safe[:100]

# ✅ ПРАВИЛЬНО
filename = sanitize_filename(user_input)
subprocess.run(
    ['tar', '-czf', f'{filename}.tar.gz', 'data/'],
    check=True,
    timeout=30
)

# ❌ НЕПРАВИЛЬНО
os.system(f"tar -czf {user_input}.tar.gz data/")
```

### 4.3 XSS Protection

```typescript
// React автоматически экранирует
function MessageComponent({ message }) {
  return <div>{message.content}</div>;  // Безопасно
}

// Если нужен HTML - используйте DOMPurify
import DOMPurify from 'dompurify';

function MessageComponent({ message }) {
  const clean = DOMPurify.sanitize(message.content);
  return <div dangerouslySetInnerHTML={{__html: clean}} />;
}
```

### 4.4 CSRF Protection

```python
from starlette.middleware.base import BaseHTTPMiddleware

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in ['POST', 'PUT', 'DELETE']:
            origin = request.headers.get('origin')

            if origin not in settings.CORS_ORIGINS:
                raise HTTPException(403, "Invalid origin")

        return await call_next(request)

app.add_middleware(CSRFMiddleware)
```

---

## 5. Rate Limiting

### 5.1 Per-Endpoint Limits

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/stats/messages")
@limiter.limit("100/minute")
async def get_stats():
    pass

@app.post("/api/summary/manual")
@limiter.limit("10/hour")
async def manual_summary():
    pass

@app.get("/api/export/csv")
@limiter.limit("5/hour")
async def export_csv():
    pass
```

### 5.2 Redis Rate Limiter

```python
class RedisRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_limit(self, key: str, limit: int, window: int) -> bool:
        current = int(datetime.now().timestamp())
        window_start = current - window

        await self.redis.zremrangebyscore(key, 0, window_start)

        count = await self.redis.zcard(key)

        if count >= limit:
            return False

        await self.redis.zadd(key, {str(current): current})
        await self.redis.expire(key, window)

        return True
```

---

## 6. Audit Logging

### 6.1 Что логировать

**✅ Логировать:**
- Аутентификацию (успех/неудача)
- SQL запросы пользователей
- Изменения настроек
- Экспорт данных
- Включение/выключение Skills

**❌ НЕ логировать:**
- Пароли, токены, API ключи
- Содержимое сообщений (если не требуется)
- Персональные данные без необходимости

### 6.2 Реализация

```python
import json

async def audit_log(
    user_id: int,
    action: str,
    chat_id: int = None,
    details: dict = None,
    success: bool = True,
    error: str = None
):
    if details:
        details = sanitize_audit_details(details)

    await db.execute('''
        INSERT INTO audit_log 
        (user_id, action, chat_id, details, success, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        action,
        chat_id,
        json.dumps(details) if details else None,
        success,
        error
    ))

def sanitize_audit_details(details: dict) -> dict:
    sensitive_keys = {'password', 'token', 'api_key', 'secret', 'otp'}

    return {
        k: '***REDACTED***' if k.lower() in sensitive_keys else v
        for k, v in details.items()
    }
```

---

## 7. Secrets Management

### 7.1 Environment Variables

```bash
# .env (добавить в .gitignore!)

MASTER_ENCRYPTION_KEY=hN6p3RlK4Qm9Xw2Yv8Zt5Bf7Cg1Dj0Ek6Lh3Mn4Op2Qr==
JWT_SECRET_KEY=super-secret-jwt-key-change-me
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

DATABASE_URL=postgresql://user:password@localhost/dbname
REDIS_URL=redis://localhost:6379/0

CORS_ORIGINS=http://localhost:3000,https://your-domain.com
```

**⚠️ НИКОГДА:**
- НЕ коммитьте `.env` в Git
- НЕ храните секреты в коде
- НЕ логируйте секреты

### 7.2 Docker Secrets

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    image: telegram-bot:latest
    secrets:
      - master_encryption_key
      - jwt_secret
    environment:
      MASTER_ENCRYPTION_KEY_FILE: /run/secrets/master_encryption_key
      JWT_SECRET_FILE: /run/secrets/jwt_secret

secrets:
  master_encryption_key:
    file: ./secrets/master_encryption_key.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
```

---

## 8. GDPR и конфиденциальность

### 8.1 Data Retention

```python
async def enforce_retention_policy():
    retention_days = settings.RETENTION_DAYS
    cutoff = datetime.now() - timedelta(days=retention_days)

    result = await db.execute(
        "DELETE FROM messages WHERE timestamp < ?",
        (cutoff,)
    )

    audit_cutoff = datetime.now() - timedelta(days=365)
    await db.execute(
        "DELETE FROM audit_log WHERE timestamp < ?",
        (audit_cutoff,)
    )

    await db.execute("VACUUM")

@scheduler.scheduled_job('cron', hour=3, minute=0)
async def daily_cleanup():
    await enforce_retention_policy()
```

### 8.2 Right to be Forgotten

```python
async def delete_user_data(user_id: int):
    async with db.transaction():
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM llm_usage WHERE user_id = ?", (user_id,))
        await db.execute("UPDATE audit_log SET user_id = NULL WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM chat_members WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
```

---

## 9. Deployment Security

### 9.1 Production Checklist

**Secrets:**
- [ ] Все ключи в `.env` или Docker secrets
- [ ] `.env` в `.gitignore`
- [ ] Backup ключей в защищенном месте

**Database:**
- [ ] Шифрование включено
- [ ] Регулярные backups
- [ ] Минимальные права доступа

**API:**
- [ ] HTTPS (Let's Encrypt)
- [ ] CORS настроен
- [ ] Rate limiting активен

**Monitoring:**
- [ ] Audit logging работает
- [ ] Alerts на критические события

### 9.2 Docker Security

```dockerfile
FROM python:3.11-slim

# Не запускаем от root
RUN useradd -m -u 1000 botuser
USER botuser

COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=botuser:botuser app/ /app/

HEALTHCHECK --interval=30s --timeout=3s   CMD python -c "import requests; requests.get('http://localhost:8000/api/health')"

CMD ["python", "-m", "app.main"]
```

---

## 10. Incident Response

### 10.1 При утечке

**Немедленные действия:**

```bash
# 1. Остановить сервис
docker-compose down

# 2. Сохранить логи
docker-compose logs > incident_logs.txt

# 3. Уведомить пользователей (GDPR)
```

**Анализ:**

```python
async def analyze_incident(start_time: datetime):
    failed_logins = await db.execute('''
        SELECT user_id, COUNT(*) as attempts
        FROM audit_log
        WHERE action = 'web_login' 
          AND success = 0
          AND timestamp > ?
        GROUP BY user_id
        HAVING attempts > 5
    ''', (start_time,))

    return {"failed_logins": list(failed_logins)}
```

**Восстановление:**

```bash
# Смена ключей
python scripts/rotate_keys.py

# Восстановление из backup
./scripts/restore.sh backups/chat_data.db.gz

# Перезапуск
docker-compose up -d
```

---

## 11. Security Checklist

### Перед деплоем

- [ ] Все секреты в environment variables
- [ ] `.env` в `.gitignore`
- [ ] HTTPS настроен
- [ ] CORS сконфигурирован
- [ ] Rate limiting активен
- [ ] Audit logging работает
- [ ] Database backups настроены
- [ ] Encryption keys созданы
- [ ] Docker security применен
- [ ] Health checks работают

### Регулярно (ежемесячно)

- [ ] Анализ audit log
- [ ] Проверка failed logins
- [ ] Обновление зависимостей
- [ ] Тест backup/restore
- [ ] Review прав доступа

---

## 12. Заключение

### Основные принципы безопасности

🔐 **Шифрование** - per-chat AES-256  
🔑 **Аутентификация** - Telegram 2FA + JWT  
🛡️ **Защита** - SQL/XSS/CSRF prevention  
📊 **Мониторинг** - audit logging  
⚡ **Rate Limiting** - защита от abuse  
🔒 **Secrets** - только в env  
📜 **GDPR** - compliance  

### Ресурсы

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity](https://www.nist.gov/cyberframework)
- [CIS Docker Benchmarks](https://www.cisecurity.org/benchmark/docker)

---

**Версия:** 2.0 | **Дата:** 2026-01-28 | **Статус:** Production-Ready
