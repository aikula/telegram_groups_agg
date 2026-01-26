# CHANGELOG.md

**Проект:** Telegram Chat Analytics & Coaching Bot v2.0  
**Формат:** [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)  
**Версионирование:** [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

### Планируется
- WebSocket real-time сообщения
- Графические дашборды (charts.js)
- Экспорт в PDF с форматированием
- Multi-model LLM support (переключение между моделями)
- Webhook режим для Telegram бота (вместо polling)
- PostgreSQL миграция (optional)
- Интеграция с Prometheus/Grafana
- Mobile app (React Native)
- Telegram Mini App интерфейс

---

## [2.0.0] - 2026-01-25

### 🎉 Major Release - Complete Rewrite

#### Added
- **Core Infrastructure**
  - SQLite + FTS5 для полнотекстового поиска по кириллице
  - Per-chat AES-256 шифрование сообщений (Fernet)
  - Task queue в SQLite (замена Celery/Redis)
  - Async/await везде (aiosqlite, aiogram, httpx)
  - Pydantic settings + validation

- **Telegram Bot**
  - Message handler с автоматическим шифрованием
  - Bot mention (@bot вопрос) - QA с контекстом чата
  - Private chat SQL-agent режим
  - Thread summarization (/summarize_thread)
  - Commands: /stats, /export, /help
  - Deleted message tracking
  - Rate limiting (30 msg/sec глобально, 1 msg/sec per chat)

- **Web API (FastAPI)**
  - Telegram OAuth + JWT authentication
  - Superadmin login с bcrypt
  - REST API для чатов, истории, поиска
  - SQL-agent эндпоинт с валидацией
  - Chat settings управление (summary/coach)
  - Admin panel (статистика, audit log, уведомления)
  - OpenAPI/Swagger документация (/docs)
  - Rate limiting (slowapi)

- **Skills System**
  - Abstract Skill base class
  - Summary skill (daily/on-demand)
  - Coach skill (communication feedback)
  - Thread summary skill
  - QA skill (context-aware answers)
  - LLM usage tracking + cost estimation

- **Security**
  - SQL injection prevention (whitelist + read-only)
  - Audit log для всех чувствительных операций
  - RBAC (User, Chat Admin, Superadmin)
  - Input validation (Pydantic)
  - XSS protection (FastAPI auto-escape)
  - Path traversal protection

- **Documentation**
  - AGENTS.md - инструкция для AI-агентов
  - TECHNICAL_SPEC.md - техническая спецификация
  - DATABASE_SCHEMA.md - схема БД с индексами
  - API_SPECIFICATION.md - REST API документация
  - SECURITY_GUIDE.md - security best practices
  - CHANGELOG.md - история изменений

#### Changed
- **Архитектура:** Монолит → async single process (FastAPI + aiogram)
- **БД:** PostgreSQL → SQLite (с готовностью к миграции)
- **Очередь:** Celery → SQLite task_queue таблица
- **Cache:** Redis → in-memory (asyncio.Queue)
- **Bot framework:** python-telegram-bot → aiogram 3.x
- **Шифрование:** файловое → per-chat keys в БД

#### Removed
- Celery dependency
- Redis dependency
- pgvector (пока не нужен)
- Webhook mode (будет в 2.1.0)
- GraphQL API (REST достаточно)

#### Fixed
- Telegram rate limits соблюдаются
- FTS5 корректно индексирует русский текст
- SQL-агент блокирует все небезопасные запросы
- Soft delete чатов при удалении бота

#### Security
- CVE-2024-XXXXX: SQL injection в старом SQL-агенте (FIXED)
- Добавлен audit log для отслеживания abuse
- Rate limiting на всех эндпоинтах
- JWT токены с expiration

---

## [1.0.0] - 2025-03-15 (Legacy)

### Added
- Базовый Telegram bot
- Сохранение сообщений в PostgreSQL
- Простая суммаризация через OpenAI API
- Веб-панель на Flask

### Known Issues
- Нет шифрования сообщений
- SQL injection уязвимость в админ панели
- Нет rate limiting
- Нет audit log

---

## [0.9.0] - 2024-12-01 (Beta)

### Added
- Proof of concept
- Базовая аналитика чатов
- OpenAI интеграция

### Known Issues
- Только для одного чата
- Нет авторизации
- Хранение токенов в plaintext

---

## Типы изменений

- **Added** - новая функциональность
- **Changed** - изменения в существующей функциональности
- **Deprecated** - функции, которые скоро будут удалены
- **Removed** - удалённые функции
- **Fixed** - исправления багов
- **Security** - security fixes

---

## Roadmap

### v2.1.0 (Q2 2026)
- [ ] Webhook mode для бота
- [ ] WebSocket real-time updates
- [ ] Multi-language UI (i18n)
- [ ] Advanced analytics dashboard
- [ ] Docker Compose production setup
- [ ] Kubernetes deployment guide

### v2.2.0 (Q3 2026)
- [ ] PostgreSQL migration tooling
- [ ] Vector search (pgvector/faiss)
- [ ] Semantic search в дополнение к FTS
- [ ] Multi-model LLM support
- [ ] Cost optimization (caching)

### v3.0.0 (Q4 2026)
- [ ] Telegram Mini App
- [ ] Mobile app (React Native)
- [ ] Enterprise SSO (SAML/OAuth2)
- [ ] Multi-tenant architecture
- [ ] Billing/usage quotas

---

## Migration Guides

### From v1.x to v2.0

**⚠️ BREAKING CHANGES - Полная переработка**

1. **Backup старой БД:**
   ```bash
   pg_dump old_database > backup_v1.sql
   ```

2. **Новая установка v2.0:**
   ```bash
   git clone https://github.com/your-org/telegram-bot-v2
   cd telegram-bot-v2
   cp .env.example .env
   # Настроить .env (см. SECURITY_GUIDE.md)
   ```

3. **Миграция данных:**
   ```python
   # migration_script.py
   import aiosqlite
   import asyncpg

   async def migrate():
       # Connect to old PostgreSQL
       pg = await asyncpg.connect('postgresql://...')

       # Connect to new SQLite
       db = await aiosqlite.connect('chat_data.db')

       # Migrate users
       users = await pg.fetch('SELECT * FROM users')
       for user in users:
           await db.execute(
               'INSERT INTO users (id, username, first_name) VALUES (?, ?, ?)',
               (user['id'], user['username'], user['first_name'])
           )

       # Migrate messages (with encryption!)
       from core.crypto import ChatCrypto
       crypto = ChatCrypto(master_key)

       messages = await pg.fetch('SELECT * FROM messages')
       for msg in messages:
           encrypted = crypto.encrypt(msg['chat_id'], msg['content'])
           await db.execute(
               'INSERT INTO messages (message_id, chat_id, user_id, content_encrypted, timestamp) VALUES (?, ?, ?, ?, ?)',
               (msg['id'], msg['chat_id'], msg['user_id'], encrypted, msg['timestamp'])
           )

       await db.commit()
   ```

4. **Тестирование:**
   ```bash
   pytest tests/
   ```

5. **Запуск:**
   ```bash
   docker-compose up -d
   ```

**Несовместимости:**
- API endpoints изменились (см. API_SPECIFICATION.md)
- БД схема полностью новая
- Старые токены не работают (нужна повторная авторизация)
- Webhook URL изменился

---

## Contributors

- **@your-username** - Lead Developer, Architecture
- **AI Assistant** - Documentation, Code Generation
- **Community** - Bug reports, Feature requests

---

## License

**Proprietary** - Для внутреннего использования компании.  
Или:  
**MIT License** - если open-source.

---

## Support

- **Issues:** https://github.com/your-org/telegram-bot/issues
- **Docs:** https://docs.your-domain.com
- **Email:** support@your-domain.com
- **Telegram:** @your_support_bot

---

**Последнее обновление:** 2026-01-25 14:18 MSK
