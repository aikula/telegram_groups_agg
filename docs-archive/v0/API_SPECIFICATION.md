# API_SPECIFICATION.md

**Версия:** 1.0  
**Дата:** 2026-01-25  
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

---

## 1. Обзор API

FastAPI REST API для веб-интерфейса бота:
- **Base URL:** `http://localhost:8000` (dev), `https://yourdomain.com` (prod)
- **Формат данных:** JSON
- **Авторизация:** JWT Bearer token (после Telegram OAuth)
- **Rate limiting:** 10 req/min для обычных эндпоинтов, 30 req/min для SQL-агента
- **CORS:** Настраивается в `web/middleware.py`

---

## 2. Аутентификация

### 2.1 Telegram OAuth Login

**POST** `/api/v1/auth/telegram`

Вход через Telegram Login Widget.

**Request Body:**
```json
{
  "id": 123456789,
  "first_name": "Ivan",
  "username": "ivan_user",
  "auth_date": 1706198400,
  "hash": "abc123def456..."
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": 123456789,
  "username": "ivan_user"
}
```

**Errors:**
- `401 Unauthorized` - неверная подпись hash
- `500 Internal Server Error` - ошибка создания токена

---

### 2.2 Superadmin Login

**POST** `/api/v1/auth/superadmin`

Вход суперадмина по паролю.

**Request Body:**
```json
{
  "password": "your_secure_password"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**
- `401 Unauthorized` - неверный пароль

---

### 2.3 Использование токенов

Все защищённые эндпоинты требуют заголовок:

```http
Authorization: Bearer <access_token>
```

**Срок жизни токена:** 7 дней (настраивается в `JWT_EXPIRE_MINUTES`).

---

## 3. Чаты

### 3.1 Получить список чатов пользователя

**GET** `/api/v1/chats`

Возвращает список чатов, где пользователь является участником.

**Headers:**
```http
Authorization: Bearer <token>
```

**Response 200:**
```json
{
  "chats": [
    {
      "id": -1001234567890,
      "title": "Team Chat",
      "type": "supergroup",
      "member_count": 15,
      "message_count": 3420,
      "last_activity": "2026-01-25T10:30:00Z",
      "role": "admin"
    },
    {
      "id": -1009876543210,
      "title": "Project Alpha",
      "type": "group",
      "member_count": 8,
      "message_count": 1250,
      "last_activity": "2026-01-24T18:15:00Z",
      "role": "member"
    }
  ]
}
```

---

### 3.2 Получить историю чата

**GET** `/api/v1/chat/{chat_id}/history`

Получить сообщения чата с опциональным полнотекстовым поиском.

**Path Parameters:**
- `chat_id` (integer) - ID чата

**Query Parameters:**
- `limit` (integer, default=100, max=500) - кол-во сообщений
- `offset` (integer, default=0) - смещение для пагинации
- `search` (string, optional) - FTS-поиск по содержимому

**Headers:**
```http
Authorization: Bearer <token>
```

**Response 200:**
```json
{
  "messages": [
    {
      "id": 12345,
      "message_id": 67890,
      "user_id": 123456789,
      "username": "ivan_user",
      "content": "Расшифрованный текст сообщения",
      "timestamp": "2026-01-25T10:30:00Z",
      "is_deleted": false
    },
    {
      "id": 12346,
      "message_id": 67891,
      "user_id": 987654321,
      "username": "anna_user",
      "content": "Ответ на сообщение",
      "timestamp": "2026-01-25T10:31:00Z",
      "is_deleted": false
    }
  ],
  "total": 3420,
  "offset": 0,
  "limit": 100
}
```

**Errors:**
- `403 Forbidden` - пользователь не является членом чата
- `404 Not Found` - чат не существует

---

### 3.3 Полнотекстовый поиск

**GET** `/api/v1/chat/{chat_id}/search`

FTS5-поиск по сообщениям чата.

**Path Parameters:**
- `chat_id` (integer) - ID чата

**Query Parameters:**
- `query` (string, required) - поисковый запрос
- `limit` (integer, default=50, max=200)
- `offset` (integer, default=0)

**Headers:**
```http
Authorization: Bearer <token>
```

**Response 200:**
```json
{
  "results": [
    {
      "id": 12345,
      "message_id": 67890,
      "user_id": 123456789,
      "username": "ivan_user",
      "content": "Текст с выделенным совпадением",
      "timestamp": "2026-01-25T10:30:00Z",
      "rank": 0.85
    }
  ],
  "total": 42,
  "query": "проект дедлайн"
}
```

---

### 3.4 Экспорт чата

**POST** `/api/v1/chat/{chat_id}/export`

Экспорт истории чата в TXT файл.

**Path Parameters:**
- `chat_id` (integer) - ID чата

**Headers:**
```http
Authorization: Bearer <token>
```

**Response 200:**
```json
{
  "download_url": "/api/v1/download/export_12345_20260125.txt",
  "expires_at": "2026-01-25T15:00:00Z"
}
```

Ссылка действительна 1 час.

**Errors:**
- `403 Forbidden` - только админы чата могут экспортировать

---

## 4. SQL-агент

### 4.1 Задать вопрос к данным чата

**POST** `/api/v1/chat/query`

SQL-агент для NLP → SQL → результат.

**Headers:**
```http
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "chat_id": -1001234567890,
  "question": "Кто больше всех написал сообщений на этой неделе?"
}
```

**Response 200:**
```json
{
  "answer": "На этой неделе больше всех сообщений (42) написал пользователь @ivan_user.",
  "sql_query": "SELECT u.username, COUNT(*) as msg_count FROM messages m JOIN users u ON m.user_id = u.id WHERE m.chat_id = -1001234567890 AND m.timestamp >= date('now', '-7 days') GROUP BY u.username ORDER BY msg_count DESC LIMIT 1",
  "execution_time_ms": 145
}
```

**Errors:**
- `403 Forbidden` - нет доступа к чату
- `400 Bad Request` - небезопасный SQL или ошибка генерации
- `429 Too Many Requests` - превышен rate limit (30 req/min)

---

## 5. Настройки чата

### 5.1 Получить настройки

**GET** `/api/v1/settings/{chat_id}`

Получить настройки чата (summary, coach, язык).

**Headers:**
```http
Authorization: Bearer <token>
```

**Response 200:**
```json
{
  "summary_enabled": true,
  "summary_time_local": "16:00",
  "summary_timezone": "Europe/Moscow",
  "summary_custom_prompt": "",
  "summary_target": "chat",

  "coach_enabled": true,
  "coach_custom_prompt": "Анализируй тон сообщений",
  "coach_target": "chat",

  "language": "ru"
}
```

**Errors:**
- `403 Forbidden` - только админы чата могут просматривать настройки

---

### 5.2 Обновить настройки

**PUT** `/api/v1/settings/{chat_id}`

Обновить настройки чата (partial update).

**Headers:**
```http
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "summary_enabled": false,
  "coach_custom_prompt": "Фокусируйся на конструктивности"
}
```

**Response 200:**
```json
{
  "status": "ok",
  "updated_fields": ["summary_enabled", "coach_custom_prompt"]
}
```

**Errors:**
- `403 Forbidden` - только админы могут изменять настройки
- `400 Bad Request` - невалидные значения

---

## 6. Статистика (Superadmin)

### 6.1 Глобальная статистика

**GET** `/api/v1/admin/stats`

Статистика по всем чатам БЕЗ доступа к контенту.

**Headers:**
```http
Authorization: Bearer <superadmin_token>
```

**Response 200:**
```json
{
  "total_users": 142,
  "total_chats": 18,
  "total_messages": 45320,
  "tokens_by_skill": {
    "summary": 1250000,
    "coach": 340000,
    "sql_agent": 180000,
    "qa": 95000,
    "thread_summary": 45000
  },
  "cost_usd_total": 12.45,
  "per_user_stats": [
    {
      "user_id": 123456789,
      "username": "ivan_user",
      "total_messages": 3420,
      "chats_count": 3,
      "tokens_used": 25000
    }
  ]
}
```

**Errors:**
- `403 Forbidden` - требуется роль superadmin

---

### 6.2 Отправить уведомление пользователю

**POST** `/api/v1/admin/notify`

Отправить сообщение пользователю в Telegram.

**Headers:**
```http
Authorization: Bearer <superadmin_token>
```

**Request Body:**
```json
{
  "user_id": 123456789,
  "message": "Ваш аккаунт будет приостановлен завтра из-за превышения лимита"
}
```

**Response 200:**
```json
{
  "status": "sent",
  "timestamp": "2026-01-25T12:00:00Z"
}
```

**Errors:**
- `403 Forbidden` - требуется superadmin
- `500 Internal Server Error` - ошибка отправки (пользователь заблокировал бота)

---

### 6.3 Audit Log

**GET** `/api/v1/admin/audit`

Получить лог действий пользователей.

**Headers:**
```http
Authorization: Bearer <superadmin_token>
```

**Query Parameters:**
- `user_id` (integer, optional) - фильтр по пользователю
- `action` (string, optional) - фильтр по типу действия
- `limit` (integer, default=100, max=1000)
- `offset` (integer, default=0)

**Response 200:**
```json
{
  "logs": [
    {
      "id": 12345,
      "user_id": 123456789,
      "action": "sql_query",
      "chat_id": -1001234567890,
      "details": {
        "sql": "SELECT COUNT(*) FROM messages WHERE chat_id = -1001234567890",
        "rows_returned": 1
      },
      "timestamp": "2026-01-25T11:30:00Z"
    },
    {
      "id": 12346,
      "user_id": 987654321,
      "action": "export_chat",
      "chat_id": -1009876543210,
      "details": {},
      "timestamp": "2026-01-25T10:15:00Z"
    }
  ],
  "total": 4532
}
```

---

## 7. Health Check

### 7.1 Health

**GET** `/health`

Проверка состояния API.

**Response 200:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "database": "connected",
  "llm_service": "available"
}
```

**Response 503:**
```json
{
  "status": "error",
  "database": "connection_failed",
  "llm_service": "timeout"
}
```

---

## 8. WebSocket (опционально, будущая фича)

### 8.1 Подписка на новые сообщения

**WebSocket** `/ws/chat/{chat_id}`

Real-time поток новых сообщений чата.

**Headers:**
```http
Authorization: Bearer <token>
```

**Incoming messages:**
```json
{
  "type": "message",
  "data": {
    "id": 12347,
    "message_id": 67892,
    "user_id": 123456789,
    "username": "ivan_user",
    "content": "Новое сообщение",
    "timestamp": "2026-01-25T12:00:00Z"
  }
}
```

**Outgoing (ping):**
```json
{
  "type": "ping"
}
```

---

## 9. Rate Limiting

| Эндпоинт              | Лимит           |
|-----------------------|-----------------|
| `/api/v1/auth/*`      | 5 req/min       |
| `/api/v1/chat/query`  | 30 req/min      |
| `/api/v1/chat/*` (GET)| 60 req/min      |
| `/api/v1/settings/*`  | 10 req/min      |
| `/api/v1/admin/*`     | 100 req/min     |
| WebSocket connections | 3 одновременно  |

**Response при превышении:**
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 45
}
```

HTTP Status: `429 Too Many Requests`

---

## 10. Ошибки

### Общие коды

| Код | Описание                  |
|-----|---------------------------|
| 200 | OK                        |
| 201 | Created                   |
| 400 | Bad Request               |
| 401 | Unauthorized              |
| 403 | Forbidden                 |
| 404 | Not Found                 |
| 429 | Too Many Requests         |
| 500 | Internal Server Error     |
| 503 | Service Unavailable       |

### Формат ошибок

```json
{
  "error": "Forbidden",
  "message": "You are not a member of this chat",
  "code": "CHAT_ACCESS_DENIED",
  "timestamp": "2026-01-25T12:00:00Z"
}
```

---

## 11. Примеры использования

### 11.1 Python (httpx)

```python
import httpx

# Login
auth_response = httpx.post(
    "http://localhost:8000/api/v1/auth/telegram",
    json={
        "id": 123456789,
        "first_name": "Ivan",
        "username": "ivan_user",
        "auth_date": 1706198400,
        "hash": "abc123..."
    }
)
token = auth_response.json()["access_token"]

# Query SQL agent
headers = {"Authorization": f"Bearer {token}"}
query_response = httpx.post(
    "http://localhost:8000/api/v1/chat/query",
    headers=headers,
    json={
        "chat_id": -1001234567890,
        "question": "Сколько сообщений было вчера?"
    }
)
print(query_response.json()["answer"])
```

### 11.2 JavaScript (fetch)

```javascript
// Login
const authResponse = await fetch('http://localhost:8000/api/v1/auth/telegram', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    id: 123456789,
    first_name: 'Ivan',
    username: 'ivan_user',
    auth_date: 1706198400,
    hash: 'abc123...'
  })
});
const { access_token } = await authResponse.json();

// Get chats
const chatsResponse = await fetch('http://localhost:8000/api/v1/chats', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});
const { chats } = await chatsResponse.json();
console.log(chats);
```

---

## 12. OpenAPI Specification

Полная OpenAPI 3.0 спецификация доступна по адресу:

**GET** `/openapi.json`

Swagger UI:

**GET** `/docs`

ReDoc:

**GET** `/redoc`

---

**Версия:** 1.0 | **Статус:** Ready for Development | **Дата:** 2026-01-25
