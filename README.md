# Telegram Chat Analytics & Coaching Bot

**Версия:** 1.0  
**Статус:** Ready for Development  

---

## 📌 О проекте

Корпоративный Telegram бот с FastAPI веб-интерфейсом для аналитики чатов:

✅ Сохраняет историю сообщений в SQLite (с отслеживанием удаленных)  
✅ Отвечает на вопросы через OpenRouter API (LLM)  
✅ Публикует ежедневные сводки (16:00 МСК)  
✅ Дает рекомендации коуча по коммуникации  
✅ Веб-дашборд с статистикой и экспортом  

---

## 🚀 Быстрый старт

### 1. Подготовка
```bash
# Клонировать проект
git clone <repo>
cd telegram-bot-project

# Создать Docker сеть (если используется Traefik или несколько контейнеров)
docker network create telegram_chanel_agg_bot-network

# Создать .env файл
cp .env.example .env

# Заполнить переменные в .env:
# - TELEGRAM_BOT_TOKEN (получить у @BotFather в Telegram)
# - OPENROUTER_API_KEY (получить на openrouter.io)
# - ADMIN_PASSWORD (придумать свой пароль)
```

### 2. Запуск
```bash
# Запустить Docker Compose
docker-compose up -d

# Проверить логи
docker-compose logs -f telegram-bot

# Открыть веб-интерфейс
# http://localhost:8000
# Логин: admin
# Пароль: из переменной ADMIN_PASSWORD
```

### 3. Добавить бота в Telegram
- Открыть чат в Telegram
- Добавить бота (@your_bot_name) в группу
- Выдать ему права администратора
- Бот начнет автоматически сохранять сообщения

---

## 📚 Документация

- **TECHNICAL_SPECIFICATION.md** — полное ТЗ с требованиями
- **AGENTS.md** — инструкция для кодового агента
- **PROJECT_STRUCTURE.md** — архитектура и файлы проекта

---

## 🔧 Структура проекта

```
telegram-bot-project/
├── app/
│   ├── main.py              # Точка входа
│   ├── config.py            # Конфигурация
│   ├── database.py          # SQLite операции
│   ├── bot/                 # Telegram бот
│   ├── llm/                 # LLM интеграция
│   └── web/                 # FastAPI сервер
├── tests/                   # Тесты
├── data/                    # SQLite БД (git ignore)
├── Dockerfile               # Docker конфиг
├── docker-compose.yml       # Docker Compose
├── requirements.txt         # Python зависимости
└── .env                     # Переменные окружения (git ignore)
```

---

## 🔑 Ключевые возможности

### 1. Сохранение сообщений
- Бот автоматически сохраняет все сообщения в SQLite
- Отслеживает удаленные сообщения
- Сохраняет: текст, пользователя, время, чат

### 2. QA через упоминание
```
@bot вопрос в чате
```
Бот захватит контекст (последние 10 сообщений) и ответит через LLM

### 3. Ежедневная сводка (16:00 МСК)
Для каждого чата публикует:
- **Сводка** — главные темы, решения, активные участники
- **Рекомендации коуча** — анализ тона, активности, конструктивизма

### 4. Веб-интерфейс
- 📊 График активности с фильтрами по чатам и пользователям
- 📥 Экспорт данных в CSV
- 🔐 Авторизация (логин/пароль)
- 📈 Статистика по чатам

---

## 🌐 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|---------|
| POST | `/api/auth/login` | Авторизация |
| GET | `/api/stats/messages` | Статистика сообщений |
| GET | `/api/chats` | Список активных чатов |
| GET | `/api/export/csv` | Экспорт в CSV |
| POST | `/api/summary/manual?chat_id=X` | Ручная сводка |
| POST | `/api/recommendations/manual?chat_id=X` | Ручные рекомендации |

---

## 📖 Использованные технологии

- **Python 3.10+** — язык
- **python-telegram-bot** — Telegram API
- **FastAPI** — веб-фреймворк
- **SQLite** — база данных
- **OpenAI** — интеграция с OpenRouter
- **APScheduler** — расписание задач
- **Docker** — контейнеризация

---

## 🛠️ Переменные окружения

```env
TELEGRAM_BOT_TOKEN=your_token        # Токен Telegram бота
OPENROUTER_API_KEY=your_key          # API ключ OpenRouter
ADMIN_USERNAME=admin                 # Логин в веб-интерфейсе
ADMIN_PASSWORD=password              # Пароль в веб-интерфейсе
TIMEZONE=Europe/Moscow               # Временная зона
CONTEXT_MESSAGES=10                  # Сообщений контекста для QA
SUMMARY_TIME=16:00                   # Время отправки сводки
SUMMARY_DAYS=7                       # Дней для анализа сводки
```

---

## 📝 Примеры использования

### Получить статистику сообщений
```bash
curl -H "Authorization: Bearer token" \
  "http://localhost:8000/api/stats/messages?chat_id=123"
```

### Экспортировать данные
```bash
curl -H "Authorization: Bearer token" \
  "http://localhost:8000/api/export/csv" > messages.csv
```

### Запросить ручную сводку
```bash
curl -X POST -H "Authorization: Bearer token" \
  "http://localhost:8000/api/summary/manual?chat_id=123"
```

---

## 🐛 Troubleshooting

### Бот не отвечает на упоминания
- Проверь, что бот добавлен в чат с правами админа
- Убедись, что TELEGRAM_BOT_TOKEN корректный
- Проверь логи: `docker-compose logs telegram-bot`

### Ошибка подключения к OpenRouter
- Проверь OPENROUTER_API_KEY в .env
- Убедись, что у тебя есть баланс в OpenRouter
- Проверь интернет соединение

### Веб-интерфейс недоступен
- Убедись, что порт 8000 не занят
- Проверь логи: `docker-compose logs telegram-bot`
- Попробуй перезапустить контейнер: `docker-compose restart`

### Ошибка авторизации
- Убедись, что ADMIN_PASSWORD установлен в .env
- Логин: `admin`, Пароль: значение из ADMIN_PASSWORD
- Проверь, что .env файл загружен в контейнер

---

## 🚀 Развертывание на сервере

### Linux VPS (через Docker)
```bash
# 1. Клонировать проект
git clone <repo>
cd telegram-bot-project

# 2. Создать Docker сеть (если ещё не создана)
docker network create telegram_chanel_agg_bot-network

# 3. Создать .env
cp .env.example .env
# Заполнить значения

# 4. Запустить
docker-compose up -d

# 4. Проверить статус
docker-compose ps
docker-compose logs -f
```

### Остановка и обновление
```bash
# Остановить
docker-compose down

# Обновить код
git pull

# Перезапустить
docker-compose up -d
```

---

## 📊 Мониторинг

### Проверить работу бота
```bash
# Логи в реал-тайм
docker-compose logs -f telegram-bot

# Проверить контейнер
docker-compose ps

# Размер БД
du -sh data/messages.db
```

### Резервная копия БД
```bash
# Скопировать БД
cp data/messages.db data/messages_backup_$(date +%Y%m%d).db

# Или экспортировать в CSV через веб-интерфейс
```

---

## 🔐 Безопасность

✅ Пароли хешируются через bcrypt  
✅ API требует авторизацию  
✅ .env файл в git ignore  
✅ SQLite БД локальная (не в облаке)  

**⚠️ Для production:**
- Использовать https для веб-интерфейса
- Раскрыть только необходимые порты
- Регулярно создавать резервные копии БД
- Настроить логирование и мониторинг

---

## 📞 Поддержка

При проблемах:
1. Проверь логи контейнера
2. Убедись что все переменные окружения установлены
3. Проверь права доступа боту в Telegram
4. Перезапусти контейнер: `docker-compose restart`

---

## 📄 Лицензия

Проект создан для внутреннего использования.

---

**Готово к использованию! 🎉**
