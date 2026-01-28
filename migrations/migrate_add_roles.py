"""
Migration: Add role-based authorization to chat_members table (v2.2)

Adds three roles:
- member: Read-only access, can chat with bot
- admin: Can modify chat settings
- owner: Full control (not implemented yet, reserved for future)

This migration enables proper authorization for chat settings modification.
"""

import aiosqlite
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


async def migrate_add_roles(db_path: str) -> bool:
    """
    Add role-based authorization to chat_members table.

    Adds role column with three possible values:
    - member: Default role, read-only access
    - admin: Can modify settings, manage members
    - owner: Full control (future use)

    Promotes the first member of each chat to admin.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if migration was applied, False if already applied
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")

        # Check if role column exists
        cursor = await db.execute("PRAGMA table_info(chat_members)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'role' in column_names:
            logger.info("Role column already exists in chat_members table")
            return False

        logger.info("Starting migration: add roles to chat_members")

        await db.execute("BEGIN TRANSACTION")

        try:
            # Step 1: Add role column with default value 'member'
            await db.execute("""
                ALTER TABLE chat_members
                ADD COLUMN role TEXT DEFAULT 'member'
            """)
            logger.info("Added role column to chat_members")

            # Step 2: Create index for role lookups (only active members)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_members_role
                ON chat_members(chat_id, role)
                WHERE left_at IS NULL
            """)
            logger.info("Created index on chat_members(chat_id, role)")

            # Step 3: Promote first member of each chat to admin
            # This is a heuristic - the first member is likely the chat creator
            await db.execute("""
                UPDATE chat_members
                SET role = 'admin'
                WHERE rowid IN (
                    SELECT MIN(rowid)
                    FROM chat_members
                    GROUP BY chat_id
                )
            """)
            logger.info("Promoted first member of each chat to admin")

            # Step 4: Validate roles (ensure all roles are valid)
            await db.execute("""
                UPDATE chat_members
                SET role = 'member'
                WHERE role NOT IN ('member', 'admin', 'owner')
            """)
            logger.info("Validated all role values")

            await db.commit()
            logger.info("Migration completed successfully: roles added to chat_members")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def rollback_roles(db_path: str) -> bool:
    """
    Rollback the roles migration.

    Note: SQLite doesn't support DROP COLUMN directly.
    This requires recreating the table.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if rollback was successful
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")

        # Check if role column exists
        cursor = await db.execute("PRAGMA table_info(chat_members)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'role' not in column_names:
            logger.info("Role column doesn't exist, nothing to rollback")
            return False

        logger.info("Starting rollback: remove roles from chat_members")

        await db.execute("BEGIN TRANSACTION")

        try:
            # SQLite doesn't support DROP COLUMN, need to recreate table
            # Get existing data
            await db.execute("""
                CREATE TABLE chat_members_backup AS
                SELECT id, chat_id, user_id, role, joined_at, left_at
                FROM chat_members
            """)

            # Drop old table
            await db.execute("DROP TABLE chat_members")

            # Recreate without role column
            await db.execute("""
                CREATE TABLE chat_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    left_at TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(chat_id, user_id)
                )
            """)

            # Copy data back (excluding role column)
            await db.execute("""
                INSERT INTO chat_members (chat_id, user_id, joined_at, left_at)
                SELECT chat_id, user_id, joined_at, left_at
                FROM chat_members_backup
            """)

            # Recreate indexes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_members_chat_id
                ON chat_members(chat_id)
                WHERE left_at IS NULL
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_members_user_id
                ON chat_members(user_id)
                WHERE left_at IS NULL
            """)

            # Drop backup
            await db.execute("DROP TABLE chat_members_backup")

            await db.commit()
            logger.info("Rollback completed: removed role column")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Rollback failed: {e}")
            raise


async def _get_schema_version(db_path: str) -> int:
    """Get current schema version."""
    async with aiosqlite.connect(db_path) as db:
        # Check if schema_migrations table exists
        cursor = await db.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_migrations'
        """)
        if not await cursor.fetchone():
            return 0

        cursor = await db.execute("SELECT MAX(version) FROM schema_migrations")
        result = await cursor.fetchone()
        return result[0] if result and result[0] else 0


async def set_schema_version(db_path: str, version: int) -> None:
    """Set schema version."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        await db.execute(
            "INSERT OR REPLACE INTO schema_migrations (version, description) VALUES (?, ?)",
            (version, "Add roles to chat_members")
        )
        await db.commit()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    async def main():
        db_path = sys.argv[1] if len(sys.argv) > 1 else "data/database.db"

        if len(sys.argv) > 2 and sys.argv[2] == "rollback":
            success = await rollback_roles(db_path)
        else:
            success = await migrate_add_roles(db_path)
            if success:
                await set_schema_version(db_path, 4)

        if success:
            print("Migration completed successfully")
        else:
            print("Migration was not applied (already migrated)")

    asyncio.run(main())
