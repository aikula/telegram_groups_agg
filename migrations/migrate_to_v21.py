"""
Database Migration v2.1 - AGENTS.md schema support

Migration changes:
1. chats table: Add separate chat_id column
2. chat_settings table: Convert to enabled_skills JSON format
3. Migration data from old boolean format to new JSON format
"""

import aiosqlite
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


async def migrate_to_v21(db_path: str) -> bool:
    """
    Migrate database from v2.0 to v2.1 for AGENTS.md support.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if migration was applied, False if already at v2.1
    """
    logger.info(f"Starting migration to v2.1 for {db_path}")

    try:
        async with aiosqlite.connect(db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")

            # Check current schema version
            schema_version = await _get_schema_version(db)
            logger.info(f"Current schema version: {schema_version}")

            if schema_version >= 21:
                logger.info("Already at v2.1 or higher, no migration needed")
                return False

            # Begin transaction
            await db.execute("BEGIN TRANSACTION")

            try:
                # Migration 1: Add chat_id column to chats table
                await _migrate_chats_table(db)

                # Migration 2: Convert chat_settings to enabled_skills JSON
                await _migrate_chat_settings(db)

                # Update schema version
                await _update_schema_version(db, version=21)

                # Commit transaction
                await db.commit()

                logger.info("Migration to v2.1 completed successfully")
                return True

            except Exception as e:
                # Rollback on error
                await db.rollback()
                logger.error(f"Migration failed, rolling back: {e}")
                raise

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    """Get current schema version."""
    # Check if chat_id column exists in chats table
    cursor = await db.execute(
        "PRAGMA table_info(chats)"
    )
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]

    # If chat_id column exists, we're at least v2.1
    if 'chat_id' in column_names:
        return 21

    # Check if enabled_skills exists
    cursor = await db.execute(
        "PRAGMA table_info(chat_settings)"
    )
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'enabled_skills' in column_names:
        return 21

    # Check for v2.0 boolean columns
    if 'summary_enabled' in column_names and 'coach_enabled' in column_names:
        return 20

    return 1  # Initial schema (v1.0)


async def _migrate_chats_table(db: aiosqlite.Connection) -> None:
    """
    Migration 1: Add chat_id column to chats table.

    Current schema:
    - id: INTEGER PRIMARY KEY (internal ID)

    New schema:
    - id: INTEGER PRIMARY KEY (internal ID)
    - chat_id: INTEGER UNIQUE (Telegram chat_id)
    """
    logger.info("Migration 1: Adding chat_id column to chats table")

    # Check if chat_id column already exists
    cursor = await db.execute("PRAGMA table_info(chats)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'chat_id' in column_names:
        logger.info("chat_id column already exists, skipping")
        return

    # Add chat_id column (nullable initially to avoid breaking existing data)
    await db.execute("""
        ALTER TABLE chats ADD COLUMN chat_id INTEGER
    """)

    # Create unique index on chat_id
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chats_chat_id
        ON chats(chat_id)
    """)

    # Migrate existing data: copy id to chat_id for existing chats
    await db.execute("""
        UPDATE chats SET chat_id = id
        WHERE chat_id IS NULL
    """)

    # Note: We keep chat_id as nullable to avoid breaking foreign key relationships
    # in other tables. New chats should have chat_id set explicitly.

    logger.info("Migration 1 completed: chat_id column added")


async def _migrate_chat_settings(db: aiosqlite.Connection) -> None:
    """
    Migration 2: Convert chat_settings to enabled_skills JSON format.

    Current schema:
    - summary_enabled BOOLEAN
    - coach_enabled BOOLEAN

    New schema:
    - enabled_skills TEXT (JSON array)
    """
    logger.info("Migration 2: Converting chat_settings to enabled_skills JSON")

    # Check if enabled_skills column already exists
    cursor = await db.execute("PRAGMA table_info(chat_settings)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'enabled_skills' in column_names:
        logger.info("enabled_skills column already exists, skipping")
        return

    # Add enabled_skills column
    await db.execute("""
        ALTER TABLE chat_settings ADD COLUMN enabled_skills TEXT
        DEFAULT '["summary","coach","qa","analytics"]'
    """)

    # Migrate existing data from boolean columns to JSON
    await db.execute("""
        UPDATE chat_settings
        SET enabled_skills = CASE
            WHEN summary_enabled = 1 AND coach_enabled = 1 THEN '["summary", "coach", "qa", "analytics"]'
            WHEN summary_enabled = 1 THEN '["summary", "qa", "analytics"]'
            WHEN coach_enabled = 1 THEN '["coach", "qa", "analytics"]'
            ELSE '["qa", "analytics"]'
        END
    """)

    logger.info("Migration 2 completed: enabled_skills JSON format added")


async def _update_schema_version(db: aiosqlite.Connection, version: int) -> None:
    """Update schema version."""
    # Create schema_version table if not exists
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert or update version
    await db.execute("""
        INSERT OR REPLACE INTO schema_version (version, applied_at)
        VALUES (?, CURRENT_TIMESTAMP)
    """, (version,))

    logger.info(f"Schema version updated to {version}")


async def rollback_migration_v21(db_path: str) -> bool:
    """
    Rollback migration from v2.1 to v2.0.

    WARNING: This will lose data! Use only for testing.
    """
    logger.warning(f"Rolling back migration from v2.1 for {db_path}")

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN TRANSACTION")

            try:
                # Rollback migration 2: Remove enabled_skills, restore boolean columns
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS chat_settings_old (
                        chat_id INTEGER PRIMARY KEY,
                        summary_enabled BOOLEAN DEFAULT 1,
                        summary_time_local TEXT DEFAULT '16:00',
                        summary_timezone TEXT DEFAULT 'Europe/Moscow',
                        summary_custom_prompt TEXT,
                        summary_target TEXT DEFAULT 'chat',
                        coach_enabled BOOLEAN DEFAULT 1,
                        coach_custom_prompt TEXT,
                        coach_target TEXT DEFAULT 'chat',
                        language TEXT DEFAULT 'ru',
                        FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                    )
                """)

                # Migrate data back
                await db.execute("""
                    INSERT INTO chat_settings_old
                    SELECT
                        chat_id,
                        CASE
                            WHEN json_extract(enabled_skills, '$') LIKE '%summary%' THEN 1
                            ELSE 0
                        END as summary_enabled,
                        summary_time_local,
                        summary_timezone,
                        summary_custom_prompt,
                        summary_target,
                        CASE
                            WHEN json_extract(enabled_skills, '$') LIKE '%coach%' THEN 1
                            ELSE 0
                        END as coach_enabled,
                        coach_custom_prompt,
                        coach_target,
                        language
                    FROM chat_settings
                """)

                await db.execute("DROP TABLE chat_settings")
                await db.execute("ALTER TABLE chat_settings_old RENAME TO chat_settings")

                # Rollback migration 1: Remove chat_id column (more complex, skip for now)
                logger.info("Rollback completed (chat_id column rollback skipped)")

                await db.execute("INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (20, CURRENT_TIMESTAMP)")
                await db.commit()

                return True

            except Exception as e:
                await db.rollback()
                logger.error(f"Rollback failed: {e}")
                raise

    except Exception as e:
        logger.error(f"Rollback error: {e}")
        raise


# ============================================================================
# Migration CLI
# ============================================================================

async def main():
    """Run migration."""
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/chat_data.db"

    print(f"Migrating database: {db_path}")
    print("Backup your database before proceeding!")

    # Check if backup exists
    from pathlib import Path
    db_file = Path(db_path)
    if db_file.exists():
        backup_file = db_file.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        print(f"Creating backup: {backup_file}")
        import shutil
        shutil.copy2(db_file, backup_file)
        print(f"Backup created: {backup_file}")

    # Run migration
    migrated = await migrate_to_v21(db_path)

    if migrated:
        print("✅ Migration to v2.1 completed successfully!")
    else:
        print("ℹ️ Database already at v2.1 or higher")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
