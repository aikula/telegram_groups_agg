"""
Core database module - Async SQLite operations with v2.0 schema

Features:
- aiosqlite for async operations
- FTS5 full-text search with Russian language support
- Per-chat encryption integration
- Audit logging
- LLM usage tracking
- Task queue for background jobs
- Migration support from v1.0
"""

import aiosqlite
import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import asynccontextmanager

import logging

from app.config import settings
from app.core.crypto import get_crypto

logger = logging.getLogger(__name__)


class Database:
    """
    Async database operations with v2.0 schema.

    Thread-safe singleton pattern with connection pooling.
    All operations are async and use aiosqlite.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file. If None, uses settings.database_path.
        """
        self.db_path = db_path or settings.database_path
        self._lock = asyncio.Lock()
        self._connection: Optional[aiosqlite.Connection] = None
        self._crypto = get_crypto()

    async def init_database(self) -> None:
        """
        Initialize database with all tables, indexes, and triggers.

        Creates schema if doesn't exist, performs migrations if needed.
        """
        # Ensure data directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA synchronous=NORMAL")

            # Create all tables
            await self._create_tables(db)
            await self._create_fts_tables(db)
            await self._create_indexes(db)
            await self._create_triggers(db)

            # Run migrations
            await self._run_migrations(db)

            await db.commit()

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create all base tables according to v2.0 schema."""

        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT DEFAULT 'ru',
                is_superadmin BOOLEAN DEFAULT 0,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Chats table (v2.1: added chat_id for AGENTS.md)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)

        # Chat members table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                left_at TIMESTAMP,
                PRIMARY KEY (chat_id, user_id),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Messages table (encrypted + plaintext for FTS)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT,
                content_encrypted TEXT,
                timestamp TIMESTAMP NOT NULL,
                is_deleted BOOLEAN DEFAULT 0,
                deleted_at TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (chat_id, message_id)
            )
        """)

        # Chat settings table (v2.1: enabled_skills JSON format)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled_skills TEXT DEFAULT '["summary","coach","qa","analytics"]',
                summary_time_local TEXT DEFAULT '16:00',
                summary_timezone TEXT DEFAULT 'Europe/Moscow',
                summary_custom_prompt TEXT,
                summary_target TEXT DEFAULT 'chat',
                coach_custom_prompt TEXT,
                coach_target TEXT DEFAULT 'chat',
                language TEXT DEFAULT 'ru',
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        # LLM usage tracking
        await db.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                skill TEXT NOT NULL,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                cost_usd REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Audit log
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                chat_id INTEGER,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (chat_id) REFERENCES chats(id)
            )
        """)

        # Task queue
        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                payload TEXT,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # OTP codes for web authentication
        await db.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

    async def _create_fts_tables(self, db: aiosqlite.Connection) -> None:
        """Create FTS5 virtual table for full-text search."""

        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                message_id UNINDEXED,
                chat_id UNINDEXED,
                content,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)

    async def _create_indexes(self, db: aiosqlite.Connection) -> None:
        """Create indexes for performance."""

        # Messages
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_time
            ON messages(chat_id, timestamp DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user
            ON messages(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_deleted
            ON messages(is_deleted, deleted_at)
        """)

        # Chat members
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_members_user
            ON chat_members(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_members_active
            ON chat_members(user_id, left_at)
        """)

        # LLM usage
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_chat
            ON llm_usage(chat_id, timestamp)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_user
            ON llm_usage(user_id, timestamp)
        """)

        # Audit log
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_user
            ON audit_log(user_id, timestamp)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_chat
            ON audit_log(chat_id, timestamp)
        """)

        # Task queue
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_queue_status
            ON task_queue(status, created_at)
        """)

        # OTP codes
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_otp_codes_code
            ON otp_codes(code)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_otp_codes_expires
            ON otp_codes(expires_at)
        """)

    async def _create_triggers(self, db: aiosqlite.Connection) -> None:
        """Create triggers for FTS synchronization."""

        # Insert trigger
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts (message_id, chat_id, content)
                VALUES (NEW.message_id, NEW.chat_id, NEW.content);
            END
        """)

        # Delete trigger
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                DELETE FROM messages_fts
                WHERE message_id = OLD.message_id AND chat_id = OLD.chat_id;
            END
        """)

        # Update trigger
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                DELETE FROM messages_fts
                WHERE message_id = OLD.message_id AND chat_id = OLD.chat_id;
                INSERT INTO messages_fts (message_id, chat_id, content)
                VALUES (NEW.message_id, NEW.chat_id, NEW.content);
            END
        """)

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """
        Run database migrations with version tracking (v2.2).

        Creates schema_migrations table if not exists and tracks
        which migrations have been applied. Only runs pending migrations.
        """
        # Create migration tracking table (v2.2)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        logger.info("schema_migrations table ensured")

        # Get current version
        cursor = await db.execute("SELECT MAX(version) FROM schema_migrations")
        result = await cursor.fetchone()
        current_version = result[0] if result and result[0] else 0

        # Define migrations
        migrations = [
            (1, "Initial schema", self._migrate_v1),
            (2, "Add telegram_id column", self._migrate_v2),
            (3, "Add otp_codes table", self._migrate_v3),
            (4, "Add enabled_skills JSON format", self._migrate_v4),
            (5, "Add role column to chat_members", self._migrate_v5),
            (6, "Add chat_id column to chats table", self._migrate_v6),
        ]

        # Run pending migrations
        for version, description, migration_fn in migrations:
            if version > current_version:
                logger.info(f"Running migration v{version}: {description}")
                try:
                    await migration_fn(db)
                    await db.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                        (version, description)
                    )
                    logger.info(f"Migration v{version} completed successfully")
                except Exception as e:
                    logger.error(f"Migration v{version} failed: {e}")
                    raise  # Fail fast to prevent partial migrations

        logger.info(f"All migrations complete. Current version: {len(migrations)}")

    # Migration functions (v2.2)
    async def _migrate_v1(self, db: aiosqlite.Connection) -> None:
        """Initial schema (no-op, tables created in _create_tables)."""
        pass

    async def _migrate_v2(self, db: aiosqlite.Connection) -> None:
        """Add telegram_id column to users table."""
        try:
            await db.execute("""
                ALTER TABLE users ADD COLUMN telegram_id INTEGER
            """)
            logger.info("  -> Added telegram_id column to users table")
        except aiosqlite.OperationalError:
            # Column already exists
            logger.info("  -> telegram_id column already exists")

    async def _migrate_v3(self, db: aiosqlite.Connection) -> None:
        """Add otp_codes table."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_otp_codes_code ON otp_codes(code)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_otp_codes_expires_at ON otp_codes(expires_at)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_otp_codes_user_id ON otp_codes(user_id)
        """)
        logger.info("  -> otp_codes table ensured")

    async def _migrate_v4(self, db: aiosqlite.Connection) -> None:
        """Add enabled_skills JSON format to chat_settings."""
        # Check if enabled_skills column exists
        cursor = await db.execute("PRAGMA table_info(chat_settings)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'enabled_skills' not in column_names:
            # Add column and migrate from old format
            await db.execute("""
                ALTER TABLE chat_settings ADD COLUMN enabled_skills TEXT
            """)
            logger.info("  -> Added enabled_skills column to chat_settings")

    async def _migrate_v5(self, db: aiosqlite.Connection) -> None:
        """Add role column to chat_members table."""
        # Check if role column exists
        cursor = await db.execute("PRAGMA table_info(chat_members)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'role' not in column_names:
            await db.execute("""
                ALTER TABLE chat_members ADD COLUMN role TEXT DEFAULT 'member'
            """)
            logger.info("  -> Added role column to chat_members")

            # Promote first member of each chat to admin
            await db.execute("""
                UPDATE chat_members
                SET role = 'admin'
                WHERE rowid IN (
                    SELECT MIN(rowid)
                    FROM chat_members
                    GROUP BY chat_id
                )
            """)
            logger.info("  -> Promoted first member of each chat to admin")

            # Create index for role lookups
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_members_role
                ON chat_members(chat_id, role)
                WHERE left_at IS NULL
            """)
            logger.info("  -> Created index on chat_members(chat_id, role)")
        else:
            logger.info("  -> role column already exists in chat_members")

    async def _migrate_v6(self, db: aiosqlite.Connection) -> None:
        """Add chat_id column to chats table and create index."""
        # Check if chat_id column exists
        cursor = await db.execute("PRAGMA table_info(chats)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'chat_id' not in column_names:
            # Add column (nullable initially, will be populated)
            await db.execute("""
                ALTER TABLE chats ADD COLUMN chat_id INTEGER
            """)
            logger.info("  -> Added chat_id column to chats table")

            # Copy existing id values to chat_id for backward compatibility
            await db.execute("""
                UPDATE chats SET chat_id = id WHERE chat_id IS NULL
            """)
            logger.info("  -> Populated chat_id from id values")

            # Create unique index on chat_id
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chats_chat_id
                ON chats(chat_id)
            """)
            logger.info("  -> Created unique index on chats(chat_id)")
        else:
            logger.info("  -> chat_id column already exists in chats table")
            # Ensure index exists
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chats_chat_id
                ON chats(chat_id)
            """)


    # === Connection Management ===

    @asynccontextmanager
    async def get_connection(self):
        """
        Get database connection with context manager.

        Yields:
            aiosqlite.Connection: Active database connection
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    # === User Operations ===

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "ru"
    ) -> Dict[str, Any]:
        """
        Get existing user or create new one.

        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: First name
            last_name: Last name
            language_code: Language code

        Returns:
            User data dictionary
        """
        async with self.get_connection() as db:
            # Try to get existing user
            cursor = await db.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

            # Create new user
            await db.execute(
                """
                INSERT INTO users (id, username, first_name, last_name, language_code)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, username, first_name, last_name, language_code)
            )
            await db.commit()

            return {
                "id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "is_superadmin": False,
                "created_at": datetime.now().isoformat()
            }

    async def is_chat_member(self, user_id: int, chat_id: int) -> bool:
        """Check if user is a member of chat (active, not left)."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM chat_members
                WHERE user_id = ? AND chat_id = ? AND left_at IS NULL
                LIMIT 1
                """,
                (user_id, chat_id)
            )
            return await cursor.fetchone() is not None

    async def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        """Check if user is admin of chat."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM chat_members
                WHERE user_id = ? AND chat_id = ? AND role = 'admin' AND left_at IS NULL
                LIMIT 1
                """,
                (user_id, chat_id)
            )
            return await cursor.fetchone() is not None

    async def get_user_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all chats where user is an active member."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT c.id, c.title, c.type, cm.role
                FROM chats c
                JOIN chat_members cm ON c.id = cm.chat_id
                WHERE cm.user_id = ? AND cm.left_at IS NULL AND c.deleted_at IS NULL
                ORDER BY c.id
                """,
                (user_id,)
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # === Chat Operations ===

    async def get_or_create_chat(
        self,
        chat_id: int,
        title: str,
        chat_type: str = "supergroup"
    ) -> Dict[str, Any]:
        """
        Get existing chat or create new one.

        v2.1: Uses chat_id column (Telegram chat ID) separately from id (internal PK).

        Args:
            chat_id: Telegram chat ID
            title: Chat title
            chat_type: Type of chat (group, supergroup)

        Returns:
            Chat data dictionary with both 'id' (internal) and 'chat_id' (Telegram)
        """
        async with self.get_connection() as db:
            # Try to get existing chat by chat_id (v2.1)
            cursor = await db.execute(
                "SELECT * FROM chats WHERE chat_id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()

            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

            # Create new chat (id auto-increments, chat_id is set)
            cursor = await db.execute(
                """
                INSERT INTO chats (chat_id, title, type)
                VALUES (?, ?, ?)
                """,
                (chat_id, title, chat_type)
            )
            await db.commit()

            # Get the auto-generated internal id
            internal_id = cursor.lastrowid

            return {
                "id": internal_id,
                "chat_id": chat_id,
                "title": title,
                "type": chat_type,
                "created_at": datetime.now().isoformat(),
                "deleted_at": None
            }

    async def add_chat_member(
        self,
        chat_id: int,
        user_id: int,
        role: str = "member"
    ) -> None:
        """Add user to chat or update their join time."""
        async with self.get_connection() as db:
            # Check if already a member
            cursor = await db.execute(
                """
                SELECT left_at FROM chat_members
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id)
            )
            row = await cursor.fetchone()

            if row and row[0] is None:
                # Already active member, do nothing
                return

            if row:
                # Previous member, update joined_at
                await db.execute(
                    """
                    UPDATE chat_members
                    SET joined_at = CURRENT_TIMESTAMP, left_at = NULL, role = ?
                    WHERE chat_id = ? AND user_id = ?
                    """,
                    (role, chat_id, user_id)
                )
            else:
                # New member
                await db.execute(
                    """
                    INSERT INTO chat_members (chat_id, user_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (chat_id, user_id, role)
                )

            await db.commit()

    # === Message Operations ===

    async def save_message(
        self,
        chat_id: int,
        message_id: int,
        user_id: int,
        content: str,
        timestamp: datetime
    ) -> int:
        """
        Save message with encryption.

        Args:
            chat_id: Telegram chat ID
            message_id: Telegram message ID
            user_id: Sender user ID
            content: Message text content
            timestamp: Message timestamp

        Returns:
            Internal message ID
        """
        # Encrypt content
        encrypted = self._crypto.encrypt(chat_id, content)

        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO messages (message_id, chat_id, user_id, content, content_encrypted, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (chat_id, message_id) DO UPDATE SET
                    content = excluded.content,
                    content_encrypted = excluded.content_encrypted,
                    timestamp = excluded.timestamp
                """,
                (message_id, chat_id, user_id, content, encrypted, timestamp.isoformat())
            )
            await db.commit()
            return cursor.lastrowid

    async def get_messages(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        days: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
        exclude_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get messages from chat.

        Args:
            chat_id: Telegram chat ID (optional)
            user_id: Filter by user ID (optional)
            days: Filter messages from last N days (optional)
            limit: Max messages to return
            offset: Offset for pagination
            include_deleted: Include deleted messages (legacy, use exclude_deleted)
            exclude_deleted: Exclude deleted messages (default: True)

        Returns:
            List of message dictionaries with decrypted content
        """
        # Handle exclude_deleted vs include_deleted
        if exclude_deleted or not include_deleted:
            deleted_filter = "AND m.is_deleted = 0"
        else:
            deleted_filter = ""

        # Build WHERE clause
        where_conditions = []
        params = []

        if chat_id is not None:
            where_conditions.append("m.chat_id = ?")
            params.append(chat_id)

        if user_id is not None:
            where_conditions.append("m.user_id = ?")
            params.append(user_id)

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            where_conditions.append("m.timestamp >= ?")
            params.append(cutoff)

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        async with self.get_connection() as db:
            cursor = await db.execute(
                f"""
                SELECT
                    m.id, m.message_id, m.chat_id, m.user_id,
                    m.content, m.timestamp, m.is_deleted,
                    u.username, u.first_name, u.last_name
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE {where_clause} {deleted_filter}
                ORDER BY m.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset]
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            messages = []
            for row in rows:
                msg = dict(zip(columns, row))
                messages.append(msg)

            return messages

    async def get_recent_messages(
        self,
        chat_id: int,
        limit: int = 20,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages from chat for LLM context.

        Args:
            chat_id: Telegram chat ID
            limit: Max messages to return
            hours: Only messages from last N hours

        Returns:
            List of message dictionaries with decrypted content
        """
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    m.id, m.message_id, m.user_id, m.content, m.timestamp,
                    u.username, u.first_name
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE m.chat_id = ? AND m.is_deleted = 0 AND m.timestamp >= ?
                ORDER BY m.timestamp ASC
                LIMIT ?
                """,
                (chat_id, cutoff_time, limit)
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            messages = []
            for row in rows:
                msg = dict(zip(columns, row))
                messages.append(msg)

            return messages

    async def mark_message_deleted(
        self,
        chat_id: int,
        message_id: int
    ) -> None:
        """Mark message as deleted (soft delete)."""
        async with self.get_connection() as db:
            await db.execute(
                """
                UPDATE messages
                SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
                WHERE chat_id = ? AND message_id = ?
                """,
                (chat_id, message_id)
            )
            await db.commit()

    async def fts_search(
        self,
        chat_id: int,
        query: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Full-text search in chat messages.

        Args:
            chat_id: Telegram chat ID
            query: Search query
            limit: Max results
            offset: Pagination offset

        Returns:
            List of matching messages with decrypted content
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    fts.message_id, fts.chat_id, fts.content,
                    m.user_id, m.timestamp, u.username, u.first_name
                FROM messages_fts fts
                JOIN messages m ON fts.message_id = m.message_id AND fts.chat_id = m.chat_id
                JOIN users u ON m.user_id = u.id
                WHERE fts.chat_id = ? AND fts.content MATCH ?
                ORDER BY fts.rowid
                LIMIT ? OFFSET ?
                """,
                (chat_id, query, limit, offset)
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            # FTS stores plaintext, no decryption needed
            # But for consistency we return same structure
            messages = []
            for row in rows:
                msg = dict(zip(columns, row))
                # Rename content to match get_messages structure
                msg["content"] = msg.pop("content")
                messages.append(msg)

            return messages

    # === Statistics ===

    async def get_chat_stats(self, chat_id: int) -> Dict[str, Any]:
        """Get statistics for a chat."""
        async with self.get_connection() as db:
            # Message count
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND is_deleted = 0",
                (chat_id,)
            )
            message_count = (await cursor.fetchone())[0]

            # Member count
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM chat_members
                WHERE chat_id = ? AND left_at IS NULL
                """,
                (chat_id,)
            )
            member_count = (await cursor.fetchone())[0]

            # Messages today
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM messages
                WHERE chat_id = ? AND is_deleted = 0
                AND date(timestamp) = date('now')
                """,
                (chat_id,)
            )
            messages_today = (await cursor.fetchone())[0]

            # Last activity
            cursor = await db.execute(
                """
                SELECT MAX(timestamp) FROM messages
                WHERE chat_id = ? AND is_deleted = 0
                """,
                (chat_id,)
            )
            last_activity = (await cursor.fetchone())[0]

            return {
                "message_count": message_count,
                "member_count": member_count,
                "messages_today": messages_today,
                "last_activity": last_activity
            }

    async def count_messages(self, chat_id: Optional[int] = None) -> int:
        """Count messages, optionally filtered by chat."""
        async with self.get_connection() as db:
            if chat_id is not None:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND is_deleted = 0",
                    (chat_id,)
                )
            else:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM messages WHERE is_deleted = 0"
                )
            return (await cursor.fetchone())[0]

    async def count_users(self) -> int:
        """Count total users."""
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            return (await cursor.fetchone())[0]

    async def count_chats(self) -> int:
        """Count total active chats."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM chats WHERE deleted_at IS NULL"
            )
            return (await cursor.fetchone())[0]

    # === Settings ===

    async def get_chat_settings(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get chat settings."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM chat_settings WHERE chat_id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))

    async def update_chat_settings(
        self,
        chat_id: int,
        updates: Dict[str, Any]
    ) -> None:
        """
        Update chat settings (partial update).
        Creates row if doesn't exist.

        v2.1: Supports both legacy boolean format and new enabled_skills JSON format.
        """
        if not updates:
            return

        async with self.get_connection() as db:
            # First check if settings exist
            cursor = await db.execute(
                "SELECT chat_id FROM chat_settings WHERE chat_id = ?",
                (chat_id,)
            )
            exists = await cursor.fetchone() is not None

            # Get current settings if exists
            current_settings = None
            if exists:
                cursor = await db.execute(
                    "SELECT * FROM chat_settings WHERE chat_id = ?",
                    (chat_id,)
                )
                row = await cursor.fetchone()
                columns = [desc[0] for desc in cursor.description]
                current_settings = dict(zip(columns, row))

            # Handle enabled_skills updates
            enabled_skills = None
            if "enabled_skills" in updates:
                enabled_skills = updates.pop("enabled_skills")
                if isinstance(enabled_skills, list):
                    enabled_skills = json.dumps(enabled_skills)

            # Check for legacy boolean settings
            if "summary_enabled" in updates or "coach_enabled" in updates:
                # Convert legacy boolean to new enabled_skills
                current_enabled = self._parse_enabled_skills(current_settings)
                if "summary_enabled" in updates:
                    if updates["summary_enabled"] and "summary" not in current_enabled:
                        current_enabled.append("summary")
                if "coach_enabled" in updates:
                    if updates["coach_enabled"] and "coach" not in current_enabled:
                        current_enabled.append("coach")
                enabled_skills = json.dumps(current_enabled)

            # Update insert
            if exists:
                # Update existing row
                if enabled_skills is not None:
                    await db.execute(
                        "UPDATE chat_settings SET enabled_skills = ? WHERE chat_id = ?",
                        (enabled_skills, chat_id)
                    )

                # Update other fields if provided
                if updates:
                    # Filter out handled fields
                    remaining_updates = {k: v for k, v in updates.items()
                                           if k not in ["enabled_skills", "summary_enabled", "coach_enabled"]}
                    if remaining_updates:
                        set_clause = ", ".join(f"{k} = ?" for k in remaining_updates.keys())
                        values = list(remaining_updates.values()) + [chat_id]
                        await db.execute(
                            f"UPDATE chat_settings SET {set_clause} WHERE chat_id = ?",
                            values
                        )
            else:
                # Insert new row
                all_values = {
                    "enabled_skills": enabled_skills or '["summary", "coach", "qa", "analytics"]',
                }
                # Add other fields
                if updates:
                    all_values.update(updates)

                # Build insert statement dynamically
                columns = list(all_values.keys())
                placeholders = ", ".join(["?"] * len(columns))
                await db.execute(
                    f"INSERT INTO chat_settings (chat_id, {', '.join(columns)}) VALUES (?, {placeholders})",
                    [chat_id] + list(all_values.values())
                )

            await db.commit()

    def _parse_enabled_skills(self, settings: Optional[Dict[str, Any]]) -> List[str]:
        """
        Parse enabled_skills from settings dict (v2.1).
        Supports both JSON format and legacy boolean format.
        """
        if not settings:
            return ["qa", "analytics"]  # Default minimal skills

        # Try JSON format first
        if "enabled_skills" in settings:
            try:
                return json.loads(settings["enabled_skills"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback to legacy boolean format
        skills = []
        if settings.get("summary_enabled"):
            skills.append("summary")
        if settings.get("coach_enabled"):
            skills.append("coach")
        # Always include qa and analytics
        skills.extend(["qa", "analytics"])
        return skills

    # === LLM Usage Tracking ===

    async def log_llm_usage(
        self,
        user_id: Optional[int],
        chat_id: Optional[int],
        skill: str,
        tokens_prompt: int,
        tokens_completion: int,
        cost_usd: Optional[float] = None
    ) -> None:
        """Log LLM token usage."""
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT INTO llm_usage
                (user_id, chat_id, skill, tokens_prompt, tokens_completion, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, chat_id, skill, tokens_prompt, tokens_completion, cost_usd)
            )
            await db.commit()

    async def get_tokens_by_skill(
        self,
        chat_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, int]:
        """Get token usage grouped by skill."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.get_connection() as db:
            if chat_id is not None:
                cursor = await db.execute(
                    """
                    SELECT skill, SUM(tokens_prompt + tokens_completion) as total
                    FROM llm_usage
                    WHERE chat_id = ? AND timestamp >= ?
                    GROUP BY skill
                    """,
                    (chat_id, cutoff)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT skill, SUM(tokens_prompt + tokens_completion) as total
                    FROM llm_usage
                    WHERE timestamp >= ?
                    GROUP BY skill
                    """,
                    (cutoff,)
                )

            return {row[0]: row[1] for row in await cursor.fetchall()}

    # === Audit Log ===

    async def audit_log(
        self,
        user_id: Optional[int],
        action: str,
        chat_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log action to audit log."""
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT INTO audit_log (user_id, action, chat_id, details)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    action,
                    chat_id,
                    json.dumps(details) if details else None
                )
            )
            await db.commit()

    async def get_audit_log(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        chat_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        async with self.get_connection() as db:
            conditions = []
            params = []

            if user_id is not None:
                conditions.append("user_id = ?")
                params.append(user_id)
            if action is not None:
                conditions.append("action = ?")
                params.append(action)
            if chat_id is not None:
                conditions.append("chat_id = ?")
                params.append(chat_id)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            params.extend([limit, offset])

            cursor = await db.execute(
                f"""
                SELECT * FROM audit_log
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            results = []
            for row in rows:
                entry = dict(zip(columns, row))
                if entry["details"]:
                    entry["details"] = json.loads(entry["details"])
                results.append(entry)

            return results

    # === Generic Query ===

    async def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        allow_write: bool = False  # v2.2: Safety flag
    ) -> List[Dict[str, Any]]:
        """
        Execute a parameterized SQL query and return results as list of dicts.

        SECURITY WARNING (v2.2):
        - Only use with trusted, parameterized queries
        - User-provided queries should use the sql_analytics tool instead
        - Set allow_write=True only for INSERT/UPDATE/DELETE operations
        - This method does NOT perform SQL injection validation

        Args:
            query: SQL query string (use ? for parameters)
            params: Optional query parameters tuple
            allow_write: Allow INSERT/UPDATE/DELETE (default: False for read-only)

        Returns:
            List of dictionaries with column names as keys

        Raises:
            ValueError: If query contains unsafe patterns or allow_write=False with DML
        """
        # Safety checks for raw SQL (v2.2)
        if not allow_write:
            query_upper = query.upper().strip()

            # Must be SELECT or WITH (CTE)
            if not (query_upper.startswith('SELECT') or query_upper.startswith('WITH')):
                raise ValueError(
                    "Only SELECT queries allowed with allow_write=False. "
                    "Use allow_write=True for INSERT/UPDATE/DELETE."
                )

            # Check for dangerous keywords
            dangerous = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE']
            for keyword in dangerous:
                if keyword in query_upper:
                    raise ValueError(
                        f"Dangerous keyword '{keyword}' in read-only query. "
                        f"Use allow_write=True if you intend to modify data."
                    )

        # Execute with parameters
        async with self.get_connection() as db:
            cursor = await db.execute(query, params or ())
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            return [dict(zip(columns, row)) for row in rows]

    # === Task Queue ===

    async def add_task(
        self,
        task_type: str,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> int:
        """Add task to queue."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO task_queue (task_type, chat_id, user_id, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    task_type,
                    chat_id,
                    user_id,
                    json.dumps(payload) if payload else None
                )
            )
            await db.commit()
            return cursor.lastrowid

    async def get_next_pending_task(self) -> Optional[Dict[str, Any]]:
        """Get next pending task from queue."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM task_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            )
            row = await cursor.fetchone()

            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            task = dict(zip(columns, row))

            if task["payload"]:
                task["payload"] = json.loads(task["payload"])

            return task

    async def update_task_status(
        self,
        task_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Update task status."""
        async with self.get_connection() as db:
            if status == "processing":
                await db.execute(
                    """
                    UPDATE task_queue
                    SET status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, task_id)
                )
            elif status == "completed":
                await db.execute(
                    """
                    UPDATE task_queue
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, task_id)
                )
            elif status == "failed":
                await db.execute(
                    """
                    UPDATE task_queue
                    SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, error_message, task_id)
                )
            await db.commit()

    async def increment_task_retry(self, task_id: int) -> None:
        """Increment task retry count."""
        async with self.get_connection() as db:
            await db.execute(
                """
                UPDATE task_queue
                SET retry_count = retry_count + 1, status = 'pending'
                WHERE id = ?
                """,
                (task_id,)
            )
            await db.commit()

    # === Web API Methods ===

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            User dict or None
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, username, first_name, last_name, language_code,
                       is_superadmin, password_hash, created_at
                FROM users WHERE username = ?
                """,
                (username,)
            )
            row = await cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "first_name": row[2],
                    "last_name": row[3],
                    "language_code": row[4],
                    "is_superadmin": row[5],
                    "password_hash": row[6],
                    "created_at": row[7]
                }
            return None

    async def create_user(
        self,
        username: str,
        password_hash: Optional[str] = None,
        is_superadmin: bool = False
    ) -> bool:
        """
        Create a new user.

        Args:
            username: Username (must be unique)
            password_hash: Bcrypt password hash (optional, for web admin users)
            is_superadmin: Whether user is superadmin

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO users (username, password_hash, is_superadmin)
                    VALUES (?, ?, ?)
                    """,
                    (username, password_hash, 1 if is_superadmin else 0)
                )
                await db.commit()
                return True
        except Exception:
            return False

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by Telegram ID.

        Args:
            telegram_id: Telegram user ID

        Returns:
            User dict or None
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, username, first_name, last_name, language_code,
                       is_superadmin, password_hash, telegram_id, created_at
                FROM users WHERE telegram_id = ?
                """,
                (telegram_id,)
            )
            row = await cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "first_name": row[2],
                    "last_name": row[3],
                    "language_code": row[4],
                    "is_superadmin": row[5],
                    "password_hash": row[6],
                    "telegram_id": row[7],
                    "created_at": row[8]
                }
            return None

    async def create_user_from_telegram(
        self,
        telegram_id: int,
        username: str,
        first_name: str = "",
        last_name: str = ""
    ) -> bool:
        """
        Create or update a user from Telegram OAuth data.

        Args:
            telegram_id: Telegram user ID
            username: Username (will be made unique if needed)
            first_name: First name
            last_name: Last name

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_connection() as db:
                # Check if user with this telegram_id exists
                existing = await db.execute(
                    "SELECT id FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                row = await existing.fetchone()

                if row:
                    # Update existing user
                    await db.execute(
                        """
                        UPDATE users
                        SET username = ?, first_name = ?, last_name = ?
                        WHERE id = ?
                        """,
                        (username, first_name, last_name, row[0])
                    )
                else:
                    # Create new user with unique username
                    # Add suffix if username already exists
                    unique_username = username
                    counter = 1
                    while True:
                        check = await db.execute(
                            "SELECT id FROM users WHERE username = ?",
                            (unique_username,)
                        )
                        if not await check.fetchone():
                            break
                        unique_username = f"{username}_{counter}"
                        counter += 1

                    await db.execute(
                        """
                        INSERT INTO users (telegram_id, username, first_name, last_name)
                        VALUES (?, ?, ?, ?)
                        """,
                        (telegram_id, unique_username, first_name, last_name)
                    )

                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to create user from telegram: {e}")
            return False

    async def get_chat_by_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chat by internal id or Telegram chat_id.

        v2.1: First searches by internal id, then by chat_id (Telegram).

        Args:
            chat_id: Internal id or Telegram chat ID

        Returns:
            Chat dict or None
        """
        async with self.get_connection() as db:
            # Try internal id first (for backward compatibility)
            cursor = await db.execute(
                """
                SELECT id, chat_id, title, type, created_at, deleted_at
                FROM chats WHERE id = ?
                """,
                (chat_id,)
            )
            row = await cursor.fetchone()

            # If not found by internal id, try by chat_id (Telegram)
            if not row:
                cursor = await db.execute(
                    """
                    SELECT id, chat_id, title, type, created_at, deleted_at
                    FROM chats WHERE chat_id = ?
                    """,
                    (chat_id,)
                )
                row = await cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "chat_id": row[1],
                    "title": row[2],
                    "chat_type": row[3],
                    "created_at": row[4],
                    "deleted_at": row[5]
                }
            return None

    async def get_chats(
        self,
        active_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get list of chats.

        Args:
            active_only: Only return active (not deleted) chats
            limit: Maximum chats to return

        Returns:
            List of chat dicts
        """
        async with self.get_connection() as db:
            if active_only:
                cursor = await db.execute(
                    """
                    SELECT id, title, type, created_at, deleted_at
                    FROM chats WHERE deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, title, type, created_at, deleted_at
                    FROM chats
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                )

            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "chat_type": row[2],
                    "created_at": row[3],
                    "deleted_at": row[4]
                }
                for row in rows
            ]

    async def get_user_chats(
        self,
        user_id: int,
        active_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get list of chats where user is a member.

        Args:
            user_id: User ID (Telegram user_id)
            active_only: Only return active (not deleted) chats
            limit: Maximum chats to return

        Returns:
            List of chat dicts where user is a member
        """
        async with self.get_connection() as db:
            if active_only:
                cursor = await db.execute(
                    """
                    SELECT c.id, c.title, c.type, c.created_at, c.deleted_at,
                           (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) as message_count
                    FROM chats c
                    INNER JOIN chat_members cm ON c.id = cm.chat_id
                    WHERE cm.user_id = ?
                      AND c.deleted_at IS NULL
                      AND cm.left_at IS NULL
                    ORDER BY c.created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT c.id, c.title, c.type, c.created_at, c.deleted_at,
                           (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) as message_count
                    FROM chats c
                    INNER JOIN chat_members cm ON c.id = cm.chat_id
                    WHERE cm.user_id = ? AND cm.left_at IS NULL
                    ORDER BY c.created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                )

            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "chat_type": row[2],
                    "created_at": row[3],
                    "deleted_at": row[4],
                    "member_count": row[5]
                }
                for row in rows
            ]

    async def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get message by ID.

        Args:
            message_id: Telegram message ID

        Returns:
            Message dict or None
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT m.message_id, m.chat_id, m.user_id, u.username,
                       u.first_name, u.last_name, m.content_encrypted, m.timestamp
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE m.message_id = ?
                """,
                (message_id,)
            )
            row = await cursor.fetchone()

            if row:
                # Decrypt content
                content_encrypted = row[6]
                if content_encrypted:
                    content = self._crypto.decrypt(row[1], content_encrypted)
                else:
                    content = ""
                return {
                    "message_id": row[0],
                    "chat_id": row[1],
                    "user_id": row[2],
                    "username": row[3],
                    "first_name": row[4],
                    "last_name": row[5],
                    "content": content,
                    "timestamp": row[7]
                }
            return None

    async def get_message_context(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Get context around a message (thread).

        Args:
            message_id: Telegram message ID
            before: Number of messages before
            after: Number of messages after

        Returns:
            Dict with 'before', 'target', 'after' lists or None
        """
        # First get the target message
        target = await self.get_message_by_id(message_id)
        if not target:
            return None

        chat_id = target["chat_id"]
        timestamp = target["timestamp"]

        # Get messages before
        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT m.message_id, m.chat_id, m.user_id, u.username,
                       u.first_name, u.last_name, m.content, m.timestamp
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE m.chat_id = ? AND m.timestamp < ?
                ORDER BY m.timestamp DESC
                LIMIT ?
                """,
                (chat_id, timestamp, before)
            )
            before_rows = await cursor.fetchall()
            before_messages = []
            for row in reversed(before_rows):  # Reverse to get chronological order
                before_messages.append({
                    "message_id": row[0],
                    "chat_id": row[1],
                    "user_id": row[2],
                    "username": row[3],
                    "first_name": row[4],
                    "last_name": row[5],
                    "content": row[6] or "",
                    "timestamp": row[7]
                })

            # Get messages after
            cursor = await db.execute(
                """
                SELECT m.message_id, m.chat_id, m.user_id, u.username,
                       u.first_name, u.last_name, m.content, m.timestamp
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE m.chat_id = ? AND m.timestamp > ?
                ORDER BY m.timestamp ASC
                LIMIT ?
                """,
                (chat_id, timestamp, after)
            )
            after_rows = await cursor.fetchall()
            after_messages = []
            for row in after_rows:
                after_messages.append({
                    "message_id": row[0],
                    "chat_id": row[1],
                    "user_id": row[2],
                    "username": row[3],
                    "first_name": row[4],
                    "last_name": row[5],
                    "content": row[6] or "",
                    "timestamp": row[7]
                })

        return {
            "before": before_messages,
            "target": target,
            "after": after_messages
        }

    async def search_messages(
        self,
        query: str,
        chat_id: Optional[int] = None,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search messages using full-text search.

        Args:
            query: Search query
            chat_id: Filter by chat (optional)
            days: Number of days to search
            limit: Maximum results

        Returns:
            List of message dicts
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.get_connection() as db:
            if chat_id is not None:
                cursor = await db.execute(
                    """
                    SELECT m.message_id, m.chat_id, m.user_id, u.username,
                           u.first_name, u.last_name, m.content, m.timestamp
                    FROM messages_fts mfts
                    JOIN messages m ON mfts.message_id = m.message_id
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE mfts.content MATCH ? AND m.chat_id = ? AND m.timestamp >= ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, chat_id, cutoff, limit)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT m.message_id, m.chat_id, m.user_id, u.username,
                           u.first_name, u.last_name, m.content, m.timestamp
                    FROM messages_fts mfts
                    JOIN messages m ON mfts.message_id = m.message_id
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE mfts.content MATCH ? AND m.timestamp >= ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, cutoff, limit)
                )

            rows = await cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    "message_id": row[0],
                    "chat_id": row[1],
                    "user_id": row[2],
                    "username": row[3],
                    "first_name": row[4],
                    "last_name": row[5],
                    "content": row[6] or "",
                    "timestamp": row[7]
                })
            return results

    async def get_chat_members(
        self,
        chat_id: int,
        active_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get members of a chat.

        Args:
            chat_id: Telegram chat ID
            active_only: Only return active members (not left)
            limit: Maximum members to return

        Returns:
            List of member dicts
        """
        async with self.get_connection() as db:
            if active_only:
                cursor = await db.execute(
                    """
                    SELECT cm.user_id, u.username, u.first_name, u.last_name,
                           cm.role, cm.joined_at
                    FROM chat_members cm
                    JOIN users u ON cm.user_id = u.id
                    WHERE cm.chat_id = ? AND cm.left_at IS NULL
                    ORDER BY cm.joined_at DESC
                    LIMIT ?
                    """,
                    (chat_id, limit)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT cm.user_id, u.username, u.first_name, u.last_name,
                           cm.role, cm.joined_at, cm.left_at
                    FROM chat_members cm
                    JOIN users u ON cm.user_id = u.id
                    WHERE cm.chat_id = ?
                    ORDER BY cm.joined_at DESC
                    LIMIT ?
                    """,
                    (chat_id, limit)
                )

            rows = await cursor.fetchall()
            return [
                {
                    "user_id": row[0],
                    "username": row[1],
                    "first_name": row[2],
                    "last_name": row[3],
                    "role": row[4],
                    "joined_at": row[5]
                }
                for row in rows
            ]

    # === Cleanup ===

    async def cleanup_old_messages(self, retention_days: int) -> int:
        """
        Delete messages older than retention period.

        Args:
            retention_days: Days to keep messages

        Returns:
            Number of messages deleted
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        async with self.get_connection() as db:
            cursor = await db.execute(
                """
                DELETE FROM messages
                WHERE timestamp < ? AND is_deleted = 1
                """,
                (cutoff,)
            )
            await db.commit()
            return cursor.rowcount

    async def cleanup_old_audit_logs(self, days: int = 365) -> int:
        """Delete audit logs older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM audit_log WHERE timestamp < ?",
                (cutoff,)
            )
            await db.commit()
            return cursor.rowcount

    # === OTP Authentication ===

    async def create_otp(self, user_id: int, telegram_id: int, valid_minutes: int = 5) -> str:
        """
        Create a one-time password for web authentication.

        Args:
            user_id: Database user ID
            telegram_id: Telegram user ID
            valid_minutes: OTP validity in minutes (default 5)

        Returns:
            6-digit OTP code
        """
        import secrets
        import string

        # Generate 6-digit code
        code = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Calculate expiration
        expires_at = (datetime.now() + timedelta(minutes=valid_minutes)).isoformat()

        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT INTO otp_codes (code, user_id, telegram_id, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, user_id, telegram_id, expires_at)
            )
            await db.commit()

        logger.info(f"Created OTP for telegram_id={telegram_id}, expires in {valid_minutes} min")
        return code

    async def verify_otp(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Verify OTP code and return user info if valid.

        Args:
            code: 6-digit OTP code

        Returns:
            User dict with user_id, telegram_id, username if valid, None otherwise
        """
        now = datetime.now().isoformat()

        async with self.get_connection() as db:
            # Find unused, non-expired OTP
            cursor = await db.execute(
                """
                SELECT o.id, o.code, o.user_id, o.telegram_id, o.expires_at,
                       u.username, u.first_name
                FROM otp_codes o
                JOIN users u ON o.user_id = u.id
                WHERE o.code = ? AND o.used_at IS NULL AND o.expires_at > ?
                ORDER BY o.created_at DESC
                LIMIT 1
                """,
                (code, now)
            )
            row = await cursor.fetchone()

            if not row:
                logger.warning(f"Invalid or expired OTP: {code}")
                return None

            columns = [desc[0] for desc in cursor.description]
            otp_data = dict(zip(columns, row))

            # Mark OTP as used
            await db.execute(
                "UPDATE otp_codes SET used_at = ? WHERE id = ?",
                (now, otp_data['id'])
            )
            await db.commit()

            logger.info(f"OTP verified for telegram_id={otp_data['telegram_id']}")

            return {
                'user_id': otp_data['user_id'],
                'telegram_id': otp_data['telegram_id'],
                'username': otp_data['username'] or otp_data['first_name']
            }

    async def cleanup_expired_otps(self) -> int:
        """Delete expired OTP codes (older than 1 hour)."""
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()

        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM otp_codes WHERE expires_at < ?",
                (cutoff,)
            )
            await db.commit()
            return cursor.rowcount


# Singleton instance
_db: Optional[Database] = None


def get_database() -> Database:
    """Get database singleton instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
