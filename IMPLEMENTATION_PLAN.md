# IMPLEMENTATION_PLAN.md

**Версия:** 2.0
**Дата:** 2026-01-25
**Проект:** Telegram Chat Analytics & Coaching Bot v2.0

---

## Executive Summary

**Current State (v1.0):**
- Basic message saving to SQLite (plaintext)
- Simple web dashboard with admin auth
- python-telegram-bot framework
- OpenRouter LLM integration for QA
- Daily summaries via scheduler

**Target State (v2.0):**
- Complete architectural rewrite with aiogram 3.4+
- Per-chat AES-256 encryption
- SQL-agent with safety validation
- Skills system (summary, coach, thread_summary)
- Multi-user support with RBAC
- Task queue in SQLite (no Celery/Redis)
- FTS5 full-text search
- Comprehensive audit logging
- Telegram OAuth + JWT authentication

---

## Implementation Roadmap

### Batch 1: Core Foundation (Parallel Development)

**No dependencies - can be started immediately**

#### 1. `/workspace/app/config.py`
- **Purpose**: Centralized configuration with Pydantic validation
- **Key Changes**:
  - Add encryption settings (master key)
  - Add JWT settings (secret, algorithm, expiration)
  - Add LLM settings (base URL, model, timeout)
  - Add rate limiting settings
  - Add retention settings
- **Dependencies**: None
- **Priority**: CRITICAL

#### 2. `/workspace/app/core/crypto.py` (NEW)
- **Purpose**: Per-chat AES-256 encryption/decryption
- **Key Classes**:
  - `ChatCrypto`: Main encryption class
    - `encrypt(chat_id, text) -> str`
    - `decrypt(chat_id, encrypted) -> str`
    - `_derive_chat_key(chat_id) -> bytes`
- **Algorithm**: Fernet (AES-128-CBC + HMAC-SHA256)
- **Key Derivation**: `SHA256(master_key + chat_id)`
- **Dependencies**: `cryptography.fernet`, `config.py`
- **Priority**: CRITICAL

#### 3. `/workspace/app/core/i18n.py` (NEW)
- **Purpose**: Internationalization support (ru/en)
- **Key Functions**:
  - `get_text(key, lang) -> str`
  - `get_available_languages() -> list`
- **Data Structure**: Dictionary with translations
- **Dependencies**: None
- **Priority**: MEDIUM

---

### Batch 2: Database & LLM (Depends on Batch 1)

#### 4. `/workspace/app/core/db.py` (COMPLETE REWRITE)
- **Purpose**: Async database operations with v2.0 schema
- **Key Changes**:
  - Switch to `aiosqlite` for async operations
  - Implement all 9 tables from DATABASE_SCHEMA.md
  - Add FTS5 triggers for automatic search indexing
  - Add migration support from v1.0 schema
- **Tables**:
  - `users`, `chats`, `chat_members`
  - `messages` (with `content_encrypted`)
  - `messages_fts` (FTS5 virtual table)
  - `chat_settings`, `llm_usage`, `audit_log`, `task_queue`
- **Key Methods**:
  - `init_database()` - Create all tables
  - `save_encrypted_message()` - Save with auto-FTS
  - `get_messages_with_decryption()` - Retrieve and decrypt
  - `fts_search()` - Full-text search
  - `log_llm_usage()` - Track token usage
  - `audit_log()` - Record sensitive operations
- **Dependencies**: `config.py`, `crypto.py`
- **Priority**: CRITICAL

#### 5. `/workspace/app/core/llm.py` (REWRITE)
- **Purpose**: Unified OpenAI-compatible LLM client
- **Key Classes**:
  - `LLMClient`: Main client
    - `generate(prompt, max_tokens) -> dict`
    - `chat_qa(question, context, lang) -> dict`
    - `format_results(question, results, lang) -> dict`
- **Features**:
  - Token usage tracking
  - Cost estimation
  - Error handling with retries
- **Dependencies**: `config.py`, `httpx`
- **Priority**: HIGH

---

### Batch 3: Security Components (Depends on Batch 1, 2)

#### 6. `/workspace/app/core/sql_agent.py` (NEW)
- **Purpose**: Safe SQL generation and execution
- **Key Classes**:
  - `SafeSQLAgent`: SQL validation and execution
    - `query(user_id, chat_id, question, lang) -> str`
    - `_is_safe(sql, chat_id) -> bool`
    - `_build_prompt(chat_id, question, lang) -> str`
- **Safety Layers**:
  1. Only SELECT queries allowed
  2. Forbidden keywords whitelist
  3. Mandatory `WHERE chat_id = X` filter
  4. Read-only connection mode
  5. Audit logging for all queries
- **Dependencies**: `llm.py`, `db.py`, `i18n.py`
- **Priority**: CRITICAL

#### 7. `/workspace/app/core/rate_limiter.py` (NEW)
- **Purpose**: Telegram API rate limiting compliance
- **Key Classes**:
  - `TelegramRateLimiter`: Rate limiter with queues
    - `send_message(chat_id, text) -> await`
    - `_process_global_queue() -> task`
    - `_process_chat_queue(chat_id) -> task`
- **Limits**:
  - 30 msg/sec global
  - 1 msg/sec per chat
- **Dependencies**: `config.py`, `asyncio`
- **Priority**: HIGH

#### 8. `/workspace/app/web/models.py` (NEW)
- **Purpose**: Pydantic models for API validation
- **Key Models**:
  - `TelegramAuthData`: OAuth data
  - `LoginRequest`: Superadmin login
  - `ChatQueryRequest`: SQL agent query
  - `ChatSettingsUpdate`: Settings update
  - `MessageResponse`: Message data
  - `ChatResponse`: Chat data
- **Dependencies**: `pydantic`
- **Priority**: HIGH

---

### Batch 4: Bot Core (Depends on Batch 1, 2, 3)

#### 9. `/workspace/app/main.py` (MAJOR REWRITE)
- **Purpose**: Application entry point
- **Key Changes**:
  - Replace `python-telegram-bot` with `aiogram`
  - Initialize dispatcher and routers
  - Start task queue worker
  - Start web server concurrently
- **Dependencies**: All Batch 1-3
- **Priority**: CRITICAL

#### 10. `/workspace/app/bot/handlers.py` (COMPLETE REWRITE)
- **Purpose**: Aiogram event handlers
- **Key Handlers**:
  - `save_message()` - Encrypt and save
  - `bot_mention()` - QA with context
  - `private_chat()` - SQL agent mode
  - `summarize_thread()` - Thread summary
  - `handle_deleted_message()` - Track deletions
- **Key Changes**:
  - Use aiogram patterns (Router, filters)
  - Integrate encryption on save
  - Integrate decryption on retrieve
- **Dependencies**: `db.py`, `crypto.py`, `llm.py`, `rate_limiter.py`
- **Priority**: CRITICAL

#### 11. `/workspace/app/bot/commands.py` (NEW)
- **Purpose**: Bot command handlers
- **Commands**:
  - `/start` - Welcome message
  - `/stats` - Chat statistics
  - `/export` - Export to TXT
  - `/summarize_thread` - Thread summary
  - `/help` - Command list
- **Dependencies**: `handlers.py`, `db.py`
- **Priority**: MEDIUM

#### 12. `/workspace/app/bot/auth.py` (NEW)
- **Purpose**: Telegram OAuth integration
- **Key Functions**:
  - `verify_telegram_auth(data, bot_token) -> bool`
  - `create_jwt_token(user_id, is_superadmin) -> str`
  - `verify_jwt_token(token) -> dict`
- **Dependencies**: `db.py`, `config.py`
- **Priority**: HIGH

#### 13. `/workspace/app/bot/scheduler.py` (REWRITE)
- **Purpose**: APScheduler for daily tasks
- **Tasks**:
  - Daily summary (16:00 local time)
  - Daily coach feedback
  - Retention cleanup
- **Dependencies**: `db.py`, `llm.py`, `skills/`
- **Priority**: HIGH

---

### Batch 5: Web API (Depends on Batch 1, 2, 3)

#### 14. `/workspace/app/web/main.py` (REFACTOR)
- **Purpose**: FastAPI application factory
- **Key Changes**:
  - Separate app creation from routes
  - Integrate middleware
  - Mount static files
- **Dependencies**: `db.py`, `models.py`
- **Priority**: HIGH

#### 15. `/workspace/app/web/middleware.py` (NEW)
- **Purpose**: Auth, CORS, rate limiting middleware
- **Middleware**:
  - `AuthMiddleware` - JWT validation
  - `RateLimitMiddleware` - slowapi integration
- **Dependencies**: `models.py`, `config.py`
- **Priority**: HIGH

#### 16. `/workspace/app/web/routes/auth.py` (NEW)
- **Purpose**: Authentication endpoints
- **Endpoints**:
  - `POST /api/v1/auth/telegram` - Telegram OAuth
  - `POST /api/v1/auth/superadmin` - Admin login
  - `GET /api/v1/auth/me` - Current user
- **Dependencies**: `models.py`, `db.py`, `bot/auth.py`
- **Priority**: HIGH

#### 17. `/workspace/app/web/routes/chat.py` (NEW)
- **Purpose**: Chat and SQL agent endpoints
- **Endpoints**:
  - `GET /api/v1/chats` - List user chats
  - `GET /api/v1/chat/{id}/history` - Chat messages
  - `POST /api/v1/chat/query` - SQL agent query
- **Dependencies**: `models.py`, `db.py`, `sql_agent.py`
- **Priority**: HIGH

#### 18. `/workspace/app/web/routes/settings.py` (NEW)
- **Purpose**: Chat settings management
- **Endpoints**:
  - `GET /api/v1/settings/{chat_id}` - Get settings
  - `PUT /api/v1/settings/{chat_id}` - Update settings
- **Dependencies**: `models.py`, `db.py`
- **Priority**: MEDIUM

#### 19. `/workspace/app/web/routes/admin.py` (NEW)
- **Purpose**: Superadmin panel
- **Endpoints**:
  - `GET /api/v1/admin/stats` - Global statistics
  - `POST /api/v1/admin/notify` - Send notification
  - `GET /api/v1/admin/audit` - Audit log
- **Dependencies**: `models.py`, `db.py`
- **Priority**: MEDIUM

#### 20. `/workspace/app/web/routes/export.py` (NEW)
- **Purpose**: Export functionality
- **Endpoints**:
  - `GET /api/v1/export/csv` - Export to CSV
  - `GET /api/v1/export/txt` - Export to TXT
- **Dependencies**: `db.py`, `crypto.py`
- **Priority**: MEDIUM

---

### Batch 6: Skills System (Depends on Batch 2)

#### 21. `/workspace/app/skills/base.py` (NEW)
- **Purpose**: Abstract skill interface
- **Key Classes**:
  - `SkillResult` - Dataclass for results
  - `Skill` - Abstract base class
- **Dependencies**: None
- **Priority**: HIGH

#### 22. `/workspace/app/skills/summary.py` (NEW)
- **Purpose**: Daily summary generation
- **Key Classes**:
  - `SummarySkill(Skill)`
- **Dependencies**: `base.py`, `llm.py`
- **Priority**: HIGH

#### 23. `/workspace/app/skills/coach.py` (NEW)
- **Purpose**: Communication coaching
- **Key Classes**:
  - `CoachSkill(Skill)`
- **Dependencies**: `base.py`, `llm.py`
- **Priority**: MEDIUM

#### 24. `/workspace/app/skills/thread_summary.py` (NEW)
- **Purpose**: Thread summarization
- **Key Classes**:
  - `ThreadSummarySkill(Skill)`
- **Dependencies**: `base.py`, `llm.py`
- **Priority**: MEDIUM

---

## Milestones & Checkpoints

### Milestone 1: Foundation Complete
**Criteria:**
- [ ] config.py with all v2.0 settings
- [ ] core/crypto.py encrypting/decrypting
- [ ] core/db.py with v2.0 schema initialized
- [ ] Can encrypt message → save → decrypt → retrieve
- [ ] FTS5 search working with Russian text

### Milestone 2: Bot Functional
**Criteria:**
- [ ] main.py runs with aiogram dispatcher
- [ ] Bot joins group and saves encrypted messages
- [ ] Bot responds to @bot mentions with LLM QA
- [ ] Commands /stats, /help working
- [ ] Rate limiting active (30 msg/sec global)

### Milestone 3: Web API Working
**Criteria:**
- [ ] Telegram OAuth login generates JWT
- [ ] JWT tokens validated on protected endpoints
- [ ] Can view chat history (decrypted messages)
- [ ] SQL agent endpoint working with validation
- [ ] Settings endpoint can update chat config

### Milestone 4: Skills Operational
**Criteria:**
- [ ] Daily summary scheduled and sent to chats
- [ ] Coach skill provides feedback
- [ ] Thread summary works on /summarize_thread
- [ ] LLM usage tracked in database

### Milestone 5: Security Complete
**Criteria:**
- [ ] SQL agent blocks all unsafe queries
- [ ] Audit log populated for sensitive actions
- [ ] Rate limits enforced on API endpoints
- [ ] Input validation on all endpoints
- [ ] Per-chat encryption verified

### Milestone 6: Production Ready
**Criteria:**
- [ ] Task queue processing background jobs
- [ ] i18n working (ru/en languages)
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Docker configuration updated
- [ ] Documentation complete

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | CRITICAL | Full backup before migration, test migration on copy |
| Encryption key loss | CRITICAL | Secure key storage, backup procedure documented |
| SQL injection via agent | HIGH | Multi-layer validation, read-only mode, audit logging |
| Telegram rate limit bans | HIGH | Asyncio.Queue rate limiter, monitoring |
| Performance degradation | MEDIUM | Benchmark with large datasets, optimize FTS |
| aiogram learning curve | MEDIUM | Complete rewrite, not incremental migration |

---

## Critical Files for Implementation

### Top 5 Must-Have Files (in order):

1. **`/workspace/app/config.py`**
   - Foundation for all configuration
   - Required by: Everything
   - Reason: Single source of truth for all settings

2. **`/workspace/app/core/crypto.py`**
   - Required by: message saving, retrieval, FTS
   - Reason: All messages must be encrypted at rest

3. **`/workspace/app/core/db.py`**
   - Required by: All data operations
   - Reason: Complete rewrite with v2.0 schema

4. **`/workspace/app/bot/handlers.py`**
   - Required by: All bot functionality
   - Reason: Core event handlers, aiogram migration

5. **`/workspace/app/core/sql_agent.py`**
   - Required by: Web API, private chat
   - Reason: Security-critical SQL validation

---

## Estimated Effort

| Batch | Files | Complexity | Estimated Time |
|-------|-------|------------|----------------|
| Batch 1: Core Foundation | 3 | Medium | 2-3 days |
| Batch 2: Database & LLM | 2 | High | 3-4 days |
| Batch 3: Security Components | 3 | High | 2-3 days |
| Batch 4: Bot Core | 5 | High | 4-5 days |
| Batch 5: Web API | 7 | Medium | 3-4 days |
| Batch 6: Skills System | 4 | Low | 2-3 days |
| Testing & Migration | - | High | 3-4 days |
| **Total** | **24** | **High** | **19-26 days** |

---

**Версия:** 2.0 | **Статус:** Ready for Development | **Дата:** 2026-01-25
