# API_SPECIFICATION.md

**Версия:** 2.0  
**Дата:** 2026-01-28  
**Base URL:** `http://localhost:8000/api`  
**Формат:** JSON

---

## 1. Обзор

REST API для веб-интерфейса Telegram Chat Analytics Bot.

### Ключевые особенности

- 🔐 **Telegram-native 2FA** - аутентификация через OTP в Telegram
- 🔑 **JWT токены** - Bearer authentication
- 📊 **Статистика и аналитика** - данные чатов
- 🎛️ **Управление Skills** - включение/выключение навыков
- 📤 **Экспорт данных** - CSV формат
- ⚡ **Rate Limiting** - защита от злоупотреблений

---

## 2. Аутентификация

### 2.1 Flow диаграмма

```
┌──────────────────────────────────────────────┐
│ 1. POST /api/auth/request-otp                │
│    Body: {"telegram_id": 123456789}          │
│    ↓                                          │
│    Response: {"message": "OTP sent"}         │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ 2. Telegram Bot отправляет код в личку       │
│    "🔐 Код для входа: 123456"               │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ 3. POST /api/auth/verify-otp                 │
│    Body: {"telegram_id": 123456789,          │
│            "otp": "123456"}                  │
│    ↓                                          │
│    Response: {"access_token": "eyJ..."}      │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ 4. Все запросы с Header:                     │
│    Authorization: Bearer eyJ...              │
└──────────────────────────────────────────────┘
```

### 2.2 Request OTP

**Endpoint:** `POST /api/auth/request-otp`

**Описание:** Генерирует и отправляет OTP код пользователю в Telegram.

**Request:**

```json
{
  "telegram_id": 123456789
}
```

**Response (200 OK):**

```json
{
  "message": "OTP sent to your Telegram",
  "expires_in": 300
}
```

**Response (401 Unauthorized):**

```json
{
  "detail": "User not found or not authorized for web access"
}
```

**Response (429 Too Many Requests):**

```json
{
  "detail": "Too many requests. Try again in 60 seconds"
}
```

**Rate Limiting:** 3 запроса в минуту на один telegram_id

---

### 2.3 Verify OTP

**Endpoint:** `POST /api/auth/verify-otp`

**Описание:** Проверяет OTP код и возвращает JWT токен.

**Request:**

```json
{
  "telegram_id": 123456789,
  "otp": "123456"
}
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

**Response (401 Unauthorized):**

```json
{
  "detail": "Invalid or expired OTP"
}
```

**Rate Limiting:** 5 попыток в минуту

---

### 2.4 Get Current User

**Endpoint:** `GET /api/auth/me`

**Описание:** Получить информацию о текущем пользователе.

**Headers:**

```
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "id": 123456789,
  "username": "vitya",
  "full_name": "Виктор",
  "is_web_admin": true,
  "language_code": "ru",
  "last_seen": "2026-01-28T09:30:00Z"
}
```

---

## 3. Статистика

### 3.1 Get Statistics

**Endpoint:** `GET /api/stats/messages`

**Описание:** Получить статистику сообщений.

**Headers:**

```
Authorization: Bearer <token>
```

**Query Parameters:**

| Параметр | Тип | Обязательный | Default | Описание |
|----------|-----|--------------|---------|----------|
| chat_id | integer | нет | null | ID чата (если null - все чаты) |
| days | integer | нет | 7 | За последние N дней |

**Request:**

```
GET /api/stats/messages?chat_id=1&days=30
```

**Response (200 OK):**

```json
{
  "total_messages": 1523,
  "total_users": 15,
  "period": {
    "start": "2025-12-29",
    "end": "2026-01-28",
    "days": 30
  },
  "top_users": [
    {
      "user_id": 123456789,
      "username": "vitya",
      "full_name": "Виктор",
      "message_count": 342,
      "percentage": 22.5
    },
    {
      "user_id": 987654321,
      "username": "admin",
      "full_name": "Администратор",
      "message_count": 218,
      "percentage": 14.3
    }
  ],
  "messages_per_day": [
    {"date": "2026-01-28", "count": 78},
    {"date": "2026-01-27", "count": 65},
    {"date": "2026-01-26", "count": 92}
  ],
  "messages_by_hour": {
    "0": 5, "1": 2, "2": 0, "3": 1,
    "9": 45, "10": 67, "11": 58,
    "14": 72, "15": 81, "16": 69
  }
}
```

---

## 4. Чаты

### 4.1 List Chats

**Endpoint:** `GET /api/chats`

**Описание:** Получить список всех чатов.

**Headers:**

```
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "chats": [
    {
      "id": 1,
      "chat_id": -1001234567890,
      "title": "Команда разработки",
      "chat_type": "supergroup",
      "member_count": 15,
      "is_active": true,
      "last_message_at": "2026-01-28T09:30:00Z",
      "total_messages": 1523
    },
    {
      "id": 2,
      "chat_id": -1009876543210,
      "title": "Менеджмент",
      "chat_type": "group",
      "member_count": 8,
      "is_active": true,
      "last_message_at": "2026-01-28T08:15:00Z",
      "total_messages": 892
    }
  ],
  "total": 2
}
```

---

### 4.2 Get Chat Details

**Endpoint:** `GET /api/chats/{chat_id}`

**Описание:** Подробная информация о чате.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| chat_id | integer | ID чата из таблицы chats |

**Response (200 OK):**

```json
{
  "id": 1,
  "chat_id": -1001234567890,
  "title": "Команда разработки",
  "chat_type": "supergroup",
  "description": "Основной чат команды",
  "member_count": 15,
  "is_active": true,
  "created_at": "2025-06-15T10:00:00Z",
  "settings": {
    "enabled_skills": ["summary", "coach", "qa", "analytics"],
    "summary_time": "16:00",
    "summary_timezone": "Europe/Moscow",
    "language": "ru"
  },
  "members": [
    {
      "user_id": 123456789,
      "username": "vitya",
      "full_name": "Виктор",
      "role": "admin"
    }
  ]
}
```

---

## 5. Сообщения

### 5.1 Get Messages

**Endpoint:** `GET /api/messages`

**Описание:** Получить сообщения чата.

**Query Parameters:**

| Параметр | Тип | Обязательный | Default | Описание |
|----------|-----|--------------|---------|----------|
| chat_id | integer | да | - | ID чата |
| days | integer | нет | 7 | За последние N дней |
| limit | integer | нет | 50 | Макс. сообщений (max: 100) |
| offset | integer | нет | 0 | Смещение для пагинации |

**Request:**

```
GET /api/messages?chat_id=1&days=7&limit=20&offset=0
```

**Response (200 OK):**

```json
{
  "messages": [
    {
      "id": 1523,
      "message_id": 45678,
      "timestamp": "2026-01-28T09:30:15Z",
      "user": {
        "id": 123456789,
        "username": "vitya",
        "full_name": "Виктор"
      },
      "content": "Давайте обсудим дедлайн проекта",
      "message_type": "text",
      "is_edited": false,
      "reply_to_message_id": null
    },
    {
      "id": 1522,
      "message_id": 45677,
      "timestamp": "2026-01-28T09:28:42Z",
      "user": {
        "id": 987654321,
        "username": "admin",
        "full_name": "Администратор"
      },
      "content": "Готов к деплою",
      "message_type": "text",
      "is_edited": false,
      "reply_to_message_id": 45670
    }
  ],
  "total": 156,
  "limit": 20,
  "offset": 0,
  "has_more": true
}
```

---

## 6. Сводки и Рекомендации

### 6.1 Manual Summary

**Endpoint:** `POST /api/summary/manual`

**Описание:** Создать сводку чата вручную.

**Query Parameters:**

| Параметр | Тип | Обязательный | Default |
|----------|-----|--------------|---------|
| chat_id | integer | да | - |
| days | integer | нет | 7 |

**Request:**

```
POST /api/summary/manual?chat_id=1&days=7
```

**Response (200 OK):**

```json
{
  "summary": "## 📊 Период\n2026-01-21 - 2026-01-28\n\n## 🔥 Основные темы\n1. **Дедлайн проекта** (45 сообщений)\n   - Обсуждение сроков\n   - Риски задержки\n\n2. **Деплой** (32 сообщения)\n   - Подготовка к релизу\n   - Тестирование\n\n## ✅ Принятые решения\n- Перенос дедлайна на 15 февраля (@vitya, 2026-01-27)\n- Freeze кода 10 февраля\n\n## 💬 Активные участники\n1. @vitya - 78 сообщений\n2. @admin - 52 сообщения",
  "recommendations": "✅ **Позитивное:**\n- Активное обсуждение проблем\n- Быстрое принятие решений\n\n⚠️ **Области улучшения:**\n- Много дублирования информации\n- Недостаточно документации решений\n\n💡 **Рекомендации:**\n1. Использовать pinned messages для важных решений\n2. Создать отдельный тред для технических вопросов\n3. Еженедельные статус-встречи",
  "generated_at": "2026-01-28T09:45:00Z"
}
```

---

### 6.2 Send Summary to Chat

**Endpoint:** `POST /api/summary/send`

**Описание:** Создать и отправить сводку в Telegram чат.

**Query Parameters:**

| Параметр | Тип | Обязательный | Default |
|----------|-----|--------------|---------|
| chat_id | integer | да | - |
| days | integer | нет | 7 |

**Response (200 OK):**

```json
{
  "message": "Summary sent to chat",
  "chat_id": -1001234567890,
  "message_id": 45690
}
```

---

## 7. Управление Skills

### 7.1 Get Skills Status

**Endpoint:** `GET /api/skills/{chat_id}`

**Описание:** Получить статус Skills для чата.

**Response (200 OK):**

```json
{
  "chat_id": 1,
  "enabled_skills": [
    {
      "name": "summary",
      "display_name": "Ежедневные сводки",
      "description": "Автоматические сводки чата",
      "enabled": true
    },
    {
      "name": "coach",
      "display_name": "Коучинг",
      "description": "Рекомендации по коммуникации",
      "enabled": true
    },
    {
      "name": "qa",
      "display_name": "Вопрос-ответ",
      "description": "Ответы на вопросы с контекстом",
      "enabled": true
    },
    {
      "name": "analytics",
      "display_name": "Аналитика",
      "description": "SQL-запросы и статистика",
      "enabled": false
    }
  ]
}
```

---

### 7.2 Toggle Skill

**Endpoint:** `POST /api/skills/{chat_id}/toggle`

**Описание:** Включить/выключить Skill.

**Request:**

```json
{
  "skill_name": "analytics",
  "enabled": true
}
```

**Response (200 OK):**

```json
{
  "message": "Skill updated",
  "skill_name": "analytics",
  "enabled": true
}
```

**Audit Log:** Действие логируется в `audit_log`.

---

## 8. Экспорт данных

### 8.1 Export to CSV

**Endpoint:** `GET /api/export/csv`

**Описание:** Экспорт сообщений чата в CSV.

**Query Parameters:**

| Параметр | Тип | Обязательный | Default |
|----------|-----|--------------|---------|
| chat_id | integer | да | - |
| days | integer | нет | 30 |

**Request:**

```
GET /api/export/csv?chat_id=1&days=30
```

**Response (200 OK):**

```
Headers:
  Content-Type: text/csv
  Content-Disposition: attachment; filename="chat_1_2026-01-28.csv"

Body (CSV):
timestamp,user_id,username,full_name,message_type,content
2026-01-28 09:30:15,123456789,vitya,Виктор,text,"Давайте обсудим дедлайн"
2026-01-28 09:28:42,987654321,admin,Администратор,text,"Готов к деплою"
```

**Audit Log:** Экспорт логируется.

---

## 9. Health & Monitoring

### 9.1 Health Check

**Endpoint:** `GET /api/health`

**Описание:** Проверка здоровья сервиса.

**Response (200 OK):**

```json
{
  "status": "healthy",
  "timestamp": "2026-01-28T09:45:00Z",
  "version": "2.0.0",
  "components": {
    "database": "ok",
    "telegram_bot": "ok",
    "llm_api": "ok"
  },
  "uptime_seconds": 86400
}
```

**Response (503 Service Unavailable):**

```json
{
  "status": "unhealthy",
  "timestamp": "2026-01-28T09:45:00Z",
  "components": {
    "database": "ok",
    "telegram_bot": "error",
    "llm_api": "ok"
  },
  "error": "Telegram bot connection failed"
}
```

---

## 10. Модели данных (Pydantic)

### 10.1 User

```python
from pydantic import BaseModel
from datetime import datetime

class User(BaseModel):
    id: int
    username: str | None
    full_name: str
    language_code: str = "ru"
    is_web_admin: bool = False
    last_seen: datetime | None
```

### 10.2 Chat

```python
class Chat(BaseModel):
    id: int
    chat_id: int
    title: str
    chat_type: str
    member_count: int
    is_active: bool
    created_at: datetime
```

### 10.3 Message

```python
class Message(BaseModel):
    id: int
    message_id: int
    timestamp: datetime
    user: User
    content: str
    message_type: str = "text"
    is_edited: bool = False
    reply_to_message_id: int | None = None
```

### 10.4 Statistics

```python
class TopUser(BaseModel):
    user_id: int
    username: str | None
    full_name: str
    message_count: int
    percentage: float

class Statistics(BaseModel):
    total_messages: int
    total_users: int
    period: dict
    top_users: list[TopUser]
    messages_per_day: list[dict]
    messages_by_hour: dict
```

---

## 11. Error Handling

### 11.1 Стандартные коды ошибок

| Код | Название | Описание |
|-----|----------|----------|
| 400 | Bad Request | Неверные параметры запроса |
| 401 | Unauthorized | Отсутствует или невалидный токен |
| 403 | Forbidden | Недостаточно прав |
| 404 | Not Found | Ресурс не найден |
| 422 | Unprocessable Entity | Ошибка валидации |
| 429 | Too Many Requests | Превышен rate limit |
| 500 | Internal Server Error | Ошибка сервера |

### 11.2 Формат ошибки

```json
{
  "detail": "Human-readable error message",
  "error_code": "INVALID_OTP",
  "timestamp": "2026-01-28T09:45:00Z"
}
```

**Примеры:**

```json
{
  "detail": "Invalid or expired OTP",
  "error_code": "INVALID_OTP"
}
```

```json
{
  "detail": "Chat not found",
  "error_code": "CHAT_NOT_FOUND"
}
```

```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds",
  "error_code": "RATE_LIMIT_EXCEEDED"
}
```

---

## 12. Rate Limiting

### 12.1 Лимиты

| Endpoint | Лимит |
|----------|-------|
| `/auth/request-otp` | 3 req/min per telegram_id |
| `/auth/verify-otp` | 5 req/min per telegram_id |
| `/summary/manual` | 10 req/hour per user |
| `/summary/send` | 5 req/hour per user |
| `/export/csv` | 10 req/hour per user |
| Остальные | 100 req/min per user |

### 12.2 Headers

При приближении к лимиту API возвращает headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1706434800
```

---

## 13. Pagination

Endpoints, возвращающие списки, поддерживают пагинацию:

**Request:**

```
GET /api/messages?chat_id=1&limit=20&offset=40
```

**Response:**

```json
{
  "messages": [...],
  "total": 156,
  "limit": 20,
  "offset": 40,
  "has_more": true
}
```

---

## 14. CORS

**Разрешенные origins:**

```python
CORS_ORIGINS = [
    "http://localhost:3000",  # Dev frontend
    "http://localhost:8000",  # Production
    "https://your-domain.com"
]
```

**Разрешенные методы:**

```
GET, POST, PUT, DELETE, OPTIONS
```

**Разрешенные headers:**

```
Authorization, Content-Type
```

---

## 15. WebSocket (Roadmap v2.1)

**Планируется:**

```
WS /api/ws/chat/{chat_id}

Events:
- message.new
- message.edited
- message.deleted
- summary.generated
```

**Пример:**

```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws/chat/1');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'message.new') {
    console.log('New message:', data.message);
  }
};
```

---

## 16. Примеры использования

### 16.1 JavaScript/TypeScript

```typescript
// Аутентификация
async function login(telegramId: number) {
  // 1. Request OTP
  const otpResponse = await fetch('/api/auth/request-otp', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({telegram_id: telegramId})
  });

  // 2. Пользователь вводит код из Telegram
  const otp = prompt('Введите код из Telegram:');

  // 3. Verify OTP
  const tokenResponse = await fetch('/api/auth/verify-otp', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({telegram_id: telegramId, otp})
  });

  const {access_token} = await tokenResponse.json();
  localStorage.setItem('token', access_token);
}

// Получение статистики
async function getStats(chatId: number, days: number = 7) {
  const token = localStorage.getItem('token');

  const response = await fetch(
    `/api/stats/messages?chat_id=${chatId}&days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );

  return await response.json();
}
```

### 16.2 Python

```python
import httpx

class TelegramBotAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token = None

    async def login(self, telegram_id: int, otp: str):
        async with httpx.AsyncClient() as client:
            # Request OTP
            await client.post(
                f"{self.base_url}/auth/request-otp",
                json={"telegram_id": telegram_id}
            )

            # Verify OTP
            response = await client.post(
                f"{self.base_url}/auth/verify-otp",
                json={"telegram_id": telegram_id, "otp": otp}
            )
            data = response.json()
            self.token = data["access_token"]

    async def get_stats(self, chat_id: int, days: int = 7):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/stats/messages",
                params={"chat_id": chat_id, "days": days},
                headers={"Authorization": f"Bearer {self.token}"}
            )
            return response.json()

# Usage
api = TelegramBotAPI("http://localhost:8000/api")
await api.login(123456789, "123456")
stats = await api.get_stats(chat_id=1, days=30)
```

---

## 17. Testing

### 17.1 Pytest Examples

```python
import pytest
from fastapi.testclient import TestClient
from app.web.app import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_auth_flow(client, mocker):
    # Mock OTP sending
    mocker.patch("app.web.auth.send_otp_to_telegram")

    # Request OTP
    response = client.post(
        "/api/auth/request-otp",
        json={"telegram_id": 123456789}
    )
    assert response.status_code == 200

    # Verify OTP (with mocked OTP)
    response = client.post(
        "/api/auth/verify-otp",
        json={"telegram_id": 123456789, "otp": "123456"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
```

---

## 18. Заключение

### Основные особенности API

✅ **Простота** - RESTful дизайн  
✅ **Безопасность** - Telegram 2FA + JWT  
✅ **Производительность** - Rate limiting  
✅ **Документация** - OpenAPI/Swagger  
✅ **Мониторинг** - Health checks  
✅ **Расширяемость** - WebSocket в roadmap  

### Swagger UI

API автоматически документируется через FastAPI:

```
http://localhost:8000/docs      - Swagger UI
http://localhost:8000/redoc     - ReDoc
```

---

**Версия:** 2.0 | **Дата:** 2026-01-28 | **Framework:** FastAPI 0.115+
