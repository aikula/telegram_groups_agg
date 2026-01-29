# Telegram Chat Analytics & Coaching Bot

> **AI-ассистент для анализа Telegram чатов** — отвечает на вопросы, создает сводки, дает рекомендации по коммуникации.

[**🤖 Попробовать бота**](https://t.me/WhyVasyabot) • [**🌐 Веб-интерфейс**](https://tghub.kulinich.ru/)

---

## 🎯 Что умеет бот

| Возможность | Описание |
|-------------|----------|
| **💬 Вопрос-ответ** | Упомяни бота в чате — он ответит на вопрос по содержанию обсуждения |
| **📊 Сводки** | Ежедневные/еженедельные отчеты с главными темами и решениями |
| **📈 Аналитика** | Статистика активности участников, графиков сообщений |
| **🎓 Коучинг** | Рекомендации по улучшению коммуникации в команде |
| **🔍 Поиск** | Найди конкретную информацию в истории чата |
| **🌐 Web Dashboard** | Админ-панель с экспортом данных и статистикой |

**Как это работает:**
```
@bot что решали вчера?
@bot покажи статистику за неделю
@bot summarize last 3 days
```

---

## 🏗️ Архитектура

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  Telegram   │─────▶│   Router    │─────▶│   Skills    │
│     Bot     │      │   Agent     │      │  (QA/Summ/) │
└─────────────┘      └─────────────┘      └─────────────┘
       │                     │                     │
       ▼                     ▼                     ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Handlers  │      │    Tools    │      │     LLM     │
│  (aiogram)  │      │  (DB/Logs/) │      │  (OpenAI)   │
└─────────────┘      └─────────────┘      └─────────────┘
```

**Технологии:**
- **aiogram 3.4+** — Telegram Bot API
- **FastAPI** — веб-интерфейс с JWT авторизацией
- **SQLite + aiosqlite** — асинхронная БД
- **OpenAI-compatible API** — LLM интеграция
- **Docker + Traefik** — деплой

---

## 🚀 Быстрый старт

### Требования
- Docker и Docker Compose
- Токен бота от [@BotFather](https://t.me/BotFather)
- API ключ для LLM (OpenRouter / OpenAI / совместимый)

### Установка

```bash
# 1. Клонировать репозиторий
git clone <repo>
cd <project>

# 2. Создать .env файл
cp .env.example .env

# 3. Заполнить обязательные переменные в .env:
#    TELEGRAM_BOT_TOKEN=your_token_here
#    LLM_API_KEY=your_llm_key_here
#    ENCRYPTION_MASTER_KEY=generated_with_python_c_secrets
#    JWT_SECRET_KEY=generated_with_secrets

# 4. Сгенерировать секреты (примеры в .env.example)

# 5. Запустить
docker-compose up -d

# 6. Проверить логи
docker-compose logs -f
```

### Настройка бота

1. **Добавить в Telegram чат** — пригласи бота в группу
2. **Выдать права админа** — бот должен читать сообщения
3. **Готово** — бот автоматически сохраняет сообщения

---

## 📚 Документация

| Документ | Описание |
|----------|----------|
| [AGENTS.md](AGENTS.md) | Архитектура agentic системы |
| [DOCS/TECHNICAL_SPEC.md](DOCS/TECHNICAL_SPEC.md) | Техническая спецификация |
| [DOCS/DATABASE_SCHEMA.md](DOCS/DATABASE_SCHEMA.md) | Схема базы данных |
| [DOCS/SECURITY_GUIDE.md](DOCS/SECURITY_GUIDE.md) | Руководство по безопасности |

---

## 🔧 Конфигурация

### Основные переменные (.env)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_token        # Токен от @BotFather
TELEGRAM_BOT_USERNAME=bot_name       # Имя бота (без @)

# LLM (OpenAI-compatible API)
LLM_API_KEY=your_key                 # OpenRouter / OpenAI / etc.
LLM_MODEL_NAME=anthropic/claude-3.5-sonnet
LLM_BASE_URL=https://openrouter.ai/api/v1

# Безопасность
ENCRYPTION_MASTER_KEY=base64_key     # AES-256 шифрование
JWT_SECRET_KEY=secret_key            # JWT токены

# Админка
SUPERADMIN_USERNAME=admin
SUPERADMIN_PASSWORD_HASH=$2b$12$hash # bcrypt hash
```

### Опциональные настройки

```bash
# База данных
DATABASE_URL=sqlite+aiosqlite:///./data/chat_data.db

# Функции
RETENTION_DAYS=90                    # Хранение сообщений
SUMMARY_TIME_UTC=13:00               # Время сводки
DEFAULT_LANGUAGE=ru                  # ru / en
CONTEXT_MESSAGES=20                  # Контекст для QA

# Сервер
HOST=0.0.0.0
PORT=8000
BASE_URL=https://yourdomain.com
```

---

## 🌐 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `GET` | `/api/health` | Проверка здоровья |
| `POST` | `/api/auth/login` | Вход в админку |
| `GET` | `/api/chats` | Список чатов |
| `GET` | `/api/messages` | Сообщения чата |
| `GET` | `/api/stats` | Статистика |
| `GET` | `/api/export/csv` | Экспорт в CSV |
| `POST` | `/api/summary/manual` | Ручная сводка |

---

## 🛠️ Разработка

### Установка локально

```bash
# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Запустить
python -m app.main
```

### Структура проекта

```
app/
├── main.py              # Точка входа
├── config.py            # Pydantic настройки
├── core/                # Ядро системы
│   ├── agent.py         # Skill executor
│   ├── router.py        # Router agent
│   ├── tools.py         # Tool definitions
│   ├── db.py            # Database operations
│   └── llm.py           # LLM client
├── skills/              # AI Skills
│   ├── qa.py            # Question answering
│   ├── summary.py       # Chat summaries
│   ├── analytics.py     # Statistics
│   ├── coach.py         # Communication coaching
│   └── about.py         # Bot information
├── bot/                 # Telegram bot (aiogram)
│   ├── bot.py           # Bot initialization
│   ├── handlers.py      # Message handlers
│   └── scheduler.py     # Scheduled tasks
└── web/                 # FastAPI interface
    ├── app.py           # FastAPI app
    ├── auth.py          # JWT authentication
    └── routes/          # API routes
```

---

## 🔐 Безопасность

- ✅ AES-256 шифрование чувствительных данных
- ✅ bcrypt хеширование паролей
- ✅ JWT токены с истечением срока
- ✅ Rate limiting для API
- ✅ .env в .gitignore
- ✅ Логи с санитизацией секретов

**Для продакшена:**
- Используй HTTPS
- Регулярно бэкапь БД
- Ограничь экспозицию портов
- Мониторь логи

---

## 🐛 Troubleshooting

| Проблема | Решение |
|----------|---------|
| Бот не отвечает | Проверь токен и права админа в чате |
| Ошибка LLM | Проверь API ключ и баланс |
| Веб недоступен | Проверь порт и firewall |
| Ошибка авторизации | Проверь JWT_SECRET_KEY |

```bash
# Логи
docker-compose logs -f

# Перезапуск
docker-compose restart

# Статус
docker-compose ps
```

---

## 📝 Лицензия

Open source — MIT License

---

**Попробуй бота:** [@WhyVasyabot](https://t.me/WhyVasyabot) • **Web:** [tghub.kulinich.ru](https://tghub.kulinich.ru/)
