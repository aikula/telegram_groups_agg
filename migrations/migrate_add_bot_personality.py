"""
Migration v2.3: Add bot_personality column to chat_settings

Adds bot personality customization per chat.
"""

import aiosqlite
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def migrate_add_bot_personality(db_path: str) -> bool:
    """
    Add bot_personality column to chat_settings table.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful
    """
    logger.info(f"Starting migration: Add bot_personality for {db_path}")

    try:
        async with aiosqlite.connect(db_path) as db:
            # Check if column already exists
            cursor = await db.execute("PRAGMA table_info(chat_settings)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'bot_personality' in column_names:
                logger.info("  -> bot_personality column already exists")
                return True

            # Add column
            await db.execute(
                """ALTER TABLE chat_settings
                   ADD COLUMN bot_personality TEXT"""
            )
            await db.commit()

            logger.info("  -> Added bot_personality column to chat_settings")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


async def rollback_bot_personality(db_path: str) -> bool:
    """
    Rollback bot_personality migration (SQLite doesn't support DROP COLUMN).

    Note: SQLite doesn't support ALTER TABLE DROP COLUMN.
    To rollback, you'd need to recreate the table.
    """
    logger.warning(f"Rollback not supported for bot_personality (SQLite limitation)")
    return True


async def set_schema_version(db_path: str, version: int) -> None:
    """Set schema version."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"INSERT OR REPLACE INTO schema_version (version) VALUES ({version})"
        )
        await db.commit()


async def main():
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/chat_data.db"

    print(f"Migrating database: {db_path}")

    # Run migration
    success = await migrate_add_bot_personality(db_path)

    if success:
        # Update schema version to 7
        await set_schema_version(db_path, 7)
        print("✓ Migration completed successfully")
    else:
        print("✗ Migration failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
