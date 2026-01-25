# Инструкция по установке файлов

## 📂 Как организовать проект

После скачивания всех файлов, создай следующую структуру:

```
telegram-bot-project/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── TECHNICAL_SPECIFICATION.md
├── AGENTS.md
├── PROJECT_STRUCTURE.md
│
├── app/
│   ├── __init__.py                # (пусто)
│   ├── main.py                    # (из app-main-py)
│   ├── config.py                  # (из app-config-py)
│   ├── database.py                # (из app-database-py)
│   │
│   ├── bot/
│   │   ├── __init__.py            # (пусто)
│   │   ├── telegram_bot.py        # (будет создан агентом)
│   │   ├── handlers.py            # (будет создан агентом)
│   │   ├── scheduler.py           # (будет создан агентом)
│   │   └── utils.py               # (будет создан агентом)
│   │
│   ├── llm/
│   │   ├── __init__.py            # (пусто)
│   │   ├── openrouter.py          # (будет создан агентом)
│   │   └── prompts.py             # (будет создан агентом)
│   │
│   └── web/
│       ├── __init__.py            # (пусто)
│       ├── app.py                 # (будет создан агентом)
│       ├── auth.py                # (будет создан агентом)
│       ├── routes.py              # (будет создан агентом)
│       │
│       └── static/
│           ├── index.html         # (будет создан агентом)
│           ├── login.html         # (будет создан агентом)
│           ├── style.css          # (будет создан агентом)
│           └── script.js          # (будет создан агентом)
│
├── tests/
│   ├── __init__.py                # (пусто)
│   ├── test_bot.py                # (будет создан агентом)
│   ├── test_api.py                # (будет создан агентом)
│   └── test_llm.py                # (будет создан агентом)
│
├── data/
│   └── .gitkeep                   # (пусто, для git)
│
├── .gitignore                      # (из gitignore)
└── logs/
    └── .gitkeep                   # (пусто, для логов)
```

## 📥 Шаг за шагом

### 1. Создай корневую папку проекта
```bash
mkdir telegram-bot-project
cd telegram-bot-project
```

### 2. Скопируй корневые файлы
Скопируй эти файлы в корень проекта:
- `Dockerfile`
- `docker-compose.yml`
- `requirements.txt`
- `env-example` → переименуй в `.env.example`
- `README.md`
- `TECHNICAL_SPECIFICATION.md`
- `AGENTS.md`
- `PROJECT_STRUCTURE.md`
- `gitignore` → переименуй в `.gitignore`

### 3. Создай папку app с подпапками
```bash
mkdir -p app/bot
mkdir -p app/llm
mkdir -p app/web/static
mkdir -p tests
mkdir -p data
mkdir -p logs
```

### 4. Создай пустые файлы __init__.py
```bash
touch app/__init__.py
touch app/bot/__init__.py
touch app/llm/__init__.py
touch app/web/__init__.py
touch tests/__init__.py
```

### 5. Скопируй готовые Python файлы
- `app-main-py` → `app/main.py`
- `app-config-py` → `app/config.py`
- `app-database-py` → `app/database.py`

### 6. Создай .env файл
```bash
cp .env.example .env
```

Отредактируй `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
OPENROUTER_API_KEY=your_api_key_here
ADMIN_PASSWORD=your_secure_password
```

### 7. Инициализируй Git (опционально)
```bash
git init
git add .
git commit -m "Initial commit: bot structure"
```

## 🚀 Запуск разработки

### Вариант 1: Локально (с Python)
```bash
# Установить зависимости
pip install -r requirements.txt

# Запустить
python -m app.main
```

### Вариант 2: Docker (рекомендуется)
```bash
# Запустить контейнер
docker-compose up -d

# Проверить логи
docker-compose logs -f
```

## 🔧 Что дальше?

После инициализации проекта:

1. **Передай все файлы кодовому агенту (Claude Code / Codex):**
   - Загрузи все документы: TECHNICAL_SPECIFICATION.md, AGENTS.md, PROJECT_STRUCTURE.md
   - Скажи ему, что нужно реализовать оставшиеся файлы согласно инструкции в AGENTS.md

2. **Агент создаст:**
   - `app/bot/telegram_bot.py` — основной класс бота
   - `app/bot/handlers.py` — обработчики событий
   - `app/bot/scheduler.py` — расписание
   - `app/bot/utils.py` — утилиты
   - `app/llm/openrouter.py` — LLM интеграция
   - `app/llm/prompts.py` — шаблоны промптов
   - `app/web/app.py` — FastAPI приложение
   - `app/web/auth.py` — авторизация
   - `app/web/routes.py` — API endpoints
   - `app/web/static/*` — HTML/CSS/JS интерфейс
   - `tests/*` — тесты

3. **После создания:**
   - Проверь что все работает: `docker-compose up -d`
   - Открой http://localhost:8000 в браузере
   - Добавь бота в Telegram чат
   - Тестируй функциональность

## 📝 Обратная связь при проблемах

Если возникают ошибки:

1. **Проверь логи:**
   ```bash
   docker-compose logs telegram-bot
   ```

2. **Убедись что файлы на месте:**
   ```bash
   ls -la app/
   ls -la requirements.txt
   ```

3. **Проверь переменные окружения:**
   ```bash
   cat .env
   # Все значения должны быть заполнены
   ```

4. **Перезапусти контейнер:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

**Готово! Проект готов к разработке. 🚀**
