# Lessons Learned & Key Decisions

## Project: Telegram Chat Analytics Bot v2.0
**Date:** 2026-01-26
**Status:** Production Ready

---

## 1. КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ

### 1.1 Handler Priority (Aiogram 3.x)

**Проблема:**
```python
# ДВА хендлера с одинаковым фильтром - выполняется только ПЕРВЫЙ!

@message_router.message()
async def handle_bot_mention(message, db, bot):  # Первый
    # Проверяет упоминание, возвращает early если нет
    pass

@message_router.message()
async def handle_message(message, db):  # Второй - НИКОГДА НЕ ВЫПОЛНЯЕТСЯ!
    # Сохраняет в базу
    pass
```

**Решение:**
Объединить логику в один хендлер:
```python
@message_router.message()
async def handle_message(message, db, bot):
    # 1. Сохранить в базу
    await save_message(message)

    # 2. Проверить упоминание и ответить
    if bot_mention in message.text:
        await generate_qa_response(message)
```

**Урок:** В aiogram 3.x при нескольких одинаковых фильтрах выполняется ТОЛЬКО ПЕРВЫЙ. Используй magic_filter `F` для специфических фильтров или объединяй логику.

---

### 1.2 Поле `date` вместо `fromtimestamp()`

**Проблема:**
```python
# ОШИБКА в aiogram 3.x!
timestamp = datetime.fromtimestamp(message.date)
# TypeError: 'datetime.datetime' object cannot be interpreted as an integer
```

**Решение:**
```python
# В aiogram 3.x message.date УЖЕ datetime объект!
timestamp = message.date
```

**Урок:** В aiogram 3.x все временные поля (`date`, `edit_date`) уже `datetime` объекты, не timestamp.

---

### 1.3 `content_encrypted` vs `content` в SQL запросах

**Проблема:**
```python
# База содержит ОБА поля:
# - content (незашифрованный)
# - content_encrypted (зашифрованный)

# Но код читал content_encrypted и пытался расшифровать!
SELECT m.content_encrypted FROM messages m
# Затем: msg["content"] = decrypt(chat_id, msg["content_encrypted"])
```

**Решение:**
Читать `content` напрямую - он уже заполнен:
```python
SELECT m.content FROM messages m
msg["content"] = row["content"]  # Готово!
```

**Урок:** Если база хранит и зашифрованную и незашифрованную версию, читайте незашифрованную. Избегайте избыточного шифрования/дешифрования.

---

### 1.4 Несоответствие полей API vs Frontend

**Проблема:**
```python
# API возвращает:
class MessageInfo:
    content: str  # <-- Поле называется 'content'

# Но frontend ожидает:
const text = msg.message_text  # <-- Ожидал 'message_text'!
```

**Решение:**
```javascript
// Исправить frontend
const text = msg.content || '[медиа]';
```

**Урок:** При рефакторинге v1.0 → v2.0 проверяйте ВСЕ места использования API: Pydantic models, frontend, мобильные приложения.

---

## 2. АРХИТЕКТУРНЫЕ РЕШЕНИЯ

### 2.1 Webhook vs Polling

**Решение:** Использовать webhook mode, НЕ polling.

**Причины:**
- Мгновенная доставка сообщений
- Меньше нагрузки на API Telegram
- Поддержка Scale (несколько инстансов бота)

**Требования:**
- Публичный HTTPS URL с валидным SSL сертификатом
- Traefik/Nginx для проксирования

---

### 2.2 Role-Based Access Control (RBAC)

**Решение:** Два уровня доступа:
- **Superadmin** (`is_superadmin=True`) - полный доступ ко всем чатам
- **Regular User** - доступ только к своим чатам

**Реализация:**
```python
# API endpoint
@router.get("/my-chats")
async def get_my_chats():
    if user.is_superadmin:
        chats = await db.get_all_chats()
    else:
        chats = await db.get_user_chats(user.user_id)
```

**Frontend:**
```javascript
const endpoint = isSuperadmin ? '/api/chats' : '/api/my-chats';
```

---

### 2.3 Защита от дублирования QA запросов

**Проблема:** При долгом LLM ответе (>10 сек) Telegram может отправить webhook дважды.

**Решение:** In-memory tracking
```python
_processed_qa_requests: Set[tuple[int, int]] = set()

request_key = (message.message_id, current_time)
if request_key in _processed_qa_requests:
    return  # Skip duplicate
_processed_qa_requests.add(request_key)
```

---

## 3. КЛЮЧЕВЫЕ ОШИБКИ

### 3.1 "Bot cannot read all group messages"

**Симптом:** Бот добавлен в группу, но не видит сообщения.

**Причины:**
1. **Privacy Mode включен** в BotFather
   - Решение: `@BotFather` → `/setprivacy` → Disable

2. **Бот не админ** в группе
   - Решение: Сделать бота админом группы

**Проверка:**
```python
bot_info = await bot.get_me()
logger.info(f"Can read all group messages: {bot_info.can_read_all_group_messages}")
```

---

### 3.2 Webhook возвращает 404

**Симптом:** `getWebhookInfo` показывает: "Wrong response from the webhook: 404 Not Found"

**Причины:**
1. **Traefik маршрутизация** - проверь labels в docker-compose.yml
2. **Prefix mismatch** - `/webhook/telegram` vs `/telegram`
3. **FastAPI app not mounted** - проверь `app.include_router(webhook.router)`

**Проверка:**
```bash
# Локально
curl -X POST http://localhost:8000/webhook/telegram -d '{"update_id":1,...}'

# Через Traefik
curl -X POST https://yourdomain.com/webhook/telegram -d '{"update_id":1,...}'
```

---

### 3.3 "No module named app.main"

**Симптом:** Контейнер перезапускается с ошибкой импорта.

**Причина:** Volume mount `/workspace/app:/app/app` переопределяет скопированные файлы.

**Решение:**
- **Development:** Использовать volume mount для live reload
- **Production:** НЕ использовать volume mount для app директории

```yaml
# docker-compose.yml
services:
  bot:
    volumes:
      - ./app:/app/app  # Only for development!
      - ./data:/app/data  # Always mount data
```

---

### 3.4 FOREIGN KEY constraint failed

**Симптом:** Ошибка при сохранении сообщения через команду.

**Причина:** Попытка создать запись с `chat_id` которого нет в таблице `chats`.

**Решение:** Всегда сначала создавать chat:
```python
@command_router.message(Command("stats"))
async def cmd_stats(message, db):
    chat_id = message.chat.id

    # Сначала создать chat (fixes FK constraint)
    await db.get_or_create_chat(
        chat_id=chat_id,
        title=message.chat.title,
        chat_type=message.chat.type
    )

    # Затем использовать chat
    stats = await db.get_chat_stats(chat_id)
```

---

## 4. DATABASE DECISIONS

### 4.1 Двойное хранение контента

**Решение:** Хранить ОБА поля:
- `content` - незашифрованный текст (для быстрого чтения)
- `content_encrypted` - зашифрованный (для backup/requirements)

**Плюсы:**
- Быстрое чтение без расшифровки
- Шифрование для compliance
- FTS работает на `content`

**Минусы:**
- Двойное место на диске
- Риск утечки через `content`

---

### 4.2 Schema naming

**v1.0 → v2.0 изменения:**
```python
# v1.0 (legacy)
message_text, chat_name, user_login

# v2.0 (current)
content, title, username
```

**Почему:** Соответствие с Telegram API и стандартными naming conventions.

---

## 5. MONITORING & DIAGNOSTICS

### 5.1 Логирование изменений

**Добавить DEBUG логи для трассировки:**
```python
logger.info(f"📨 Message received: chat_id={chat_id}, from={user_id}")
logger.info(f"🤖 Bot mention detected: {question}")
logger.debug(f"Saved message {message_id} from chat {chat_id}")
```

---

### 5.2 Health check endpoint

```python
@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "database": "connected",
        "bot": "ready"
    }
```

---

### 5.3 Diagnostics command

```python
@command_router.message(Command("diagnostics"))
async def cmd_diagnostics(message):
    bot_info = await bot.get_me()
    lines = [
        f"👤 Бот: @{bot_info.username}",
        f"📛 Читает группы: {'✅' if bot_info.can_read_all_group_messages else '❌'}",
    ]
    await message.answer("\n".join(lines))
```

---

## 6. DEPLOYMENT CHECKLIST

### 6.1 Перед первым запуском

- [ ] Создать Docker сеть: `docker network create telegram_chanel_agg_bot-network`
- [ ] Настроить `.env` (токены, ключи API)
- [ ] Отключить Privacy Mode в `@BotFather`
- [ ] Добавить бота в группы как админа
- [ ] Проверить SSL сертификат (Let's Encrypt/Traefik)

---

### 6.2 После первого запуска

- [ ] Проверить webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- [ ] Отправить тестовое сообщение в группу
- [ ] Проверить логи: `docker logs chat-analytics-bot`
- [ ] Проверить базу: сообщения должны появляться в SQLite
- [ ] Проверить веб-интерфейс: логин и отображение данных

---

### 6.3 Troubleshooting команды

```bash
# Логи бота
docker logs -f chat-analytics-bot

# Проверить webhook статус
curl -s "https://api.telegram.org/bot$TOKEN/getWebhookInfo" | jq

# Проверить базу
docker exec chat-analytics-bot python -c "
import aiosqlite
import asyncio
async def check():
    db = await aiosqlite.connect('/app/data/chat_data.db')
    cursor = await db.execute('SELECT COUNT(*) FROM messages')
    print(f'Messages: {(await cursor.fetchone())[0]}')
    await db.close()
asyncio.run(check())
"

# Тест webhook endpoint
curl -X POST http://localhost:8000/webhook/telegram \
  -H "Content-Type: application/json" \
  -d '{"update_id":1,"message":{"message_id":1,"from":{"id":123},"chat":{"id":-100},"text":"test"}}'
```

---

## 7. КАЧЕСТВЕННЫЕ ПРАКТИКИ

### 7.1 Error Handling

```python
# Webhook всегда должен возвращать 200 OK
@router.post("/telegram")
async def telegram_webhook(request):
    try:
        await dispatcher.feed_webhook_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"status": "ok"}  # Важно! Чтобы Telegram не ретраил
```

---

### 7.2 Database Migrations

```python
async def init_database(self):
    # Создать таблицы IF NOT EXISTS
    # Добавить колонки IF NOT EXISTS
    # Вносить изменения backwards-compatible
```

---

### 7.3 Rate Limiting

```python
# Использовать middleware для rate limiting
@dispatcher.update.middleware(RateLimitMiddleware(limiter))
```

---

## 8. БУДУЩЕЕ УЛУЧШЕНИЯ

### 8.1 Performance

- [ ] Добавить индексы на `messages(timestamp)`, `messages(chat_id, timestamp)`
- [ ] Кэшировать `get_chats()` для superadmin
- [ ] Пагинация для больших чатов

---

### 8.2 Features

- [ ] WebSocket для real-time обновлений
- [ ] Выгрузка в Excel
- [ ] Графики активности (Chart.js)
- [ ] Мультисессионный чат (analyze thread)

---

### 8.3 Security

- [ ] CSRF protection для API mutations
- [ ] Rate limiting per user
- [ ] Audit логирование действий superadmin
- [ ] Backup базы данных с шифрованием

---

**Документ обновлен:** 2026-01-26
**Версия:** 2.0
**Статус:** Production Ready ✅
