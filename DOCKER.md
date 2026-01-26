# Docker Deployment

## Быстрый старт

1. **Копируйте файл переменных окружения:**
   ```bash
   cp .env.example .env
   ```

2. **Отредактируйте `.env` и укажите свои токены:**
   ```bash
   nano .env
   ```
   Обязательные переменные:
   - `TELEGRAM_BOT_TOKEN` - токен от @BotFather
   - `OPENROUTER_API_KEY` - ключ с https://openrouter.ai/

3. **Сгенерируйте ключи безопасности:**

   ### ENCRYPTION_MASTER_KEY (для AES-256 шифрования)
   ```bash
   python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
   ```
   ⚠️ **ВАЖНО:** Сохраните этот ключ! При потере все данные станут недоступны.

   ### SUPERADMIN_PASSWORD_HASH (для входа суперадмина)
   ```bash
   python -c "from app.web.auth import hash_password; print(hash_password('ВАШ_ПАРОЛЬ'))"
   ```

   ### JWT_SECRET_KEY (для токенов авторизации)
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   ### TELEGRAM_BOT_USERNAME (для Login Widget)
   Имя вашего бота без @ (например: `my_analytics_bot`)

4. **Добавьте сгенерированные значения в `.env`:**
   ```env
   # Telegram
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_BOT_USERNAME=your_bot_username

   # LLM
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx

   # Безопасность
   ENCRYPTION_MASTER_KEY=сгенерированный_ключ
   SUPERADMIN_PASSWORD_HASH=сгенерированный_хеш
   SUPERADMIN_USERNAME=superadmin
   JWT_SECRET_KEY=сгенерированный_jwt_ключ
   ```

5. **Запустите бота:**
   ```bash
   docker compose up -d
   ```

4. **Проверьте статус:**
   ```bash
   docker compose ps
   docker compose logs -f bot
   ```

## Полезные команды

| Команда | Описание |
|---------|----------|
| `docker compose up -d` | Запуск в фоне |
| `docker compose down` | Остановка и удаление контейнеров |
| `docker compose logs -f` | Просмотр логов в реальном времени |
| `docker compose restart` | Перезапуск контейнеров |
| `docker compose ps` | Статус контейнеров |
| `docker compose exec bot bash` | Запуск shell внутри контейнера |
| `docker compose pull` | Обновление образов |
| `docker compose up -d --build` | Пересборка и запуск |

## Порты

- **8000** - Web API (FastAPI)

## Вolumes

- `./data` - база данных SQLite и другие данные

## Health Check

Контейнер имеет встроенную проверку здоровья. Статус можно посмотреть:
```bash
docker inspect chat-analytics-bot --format='{{.State.Health.Status}}'
```

## Логи

Логи вращаются автоматически (макс. 10MB, 3 файла).

Просмотр логов:
```bash
# Все логи
docker compose logs bot

# Последние 100 строк
docker compose logs --tail=100 bot

| Режим
docker compose logs -f bot
```
