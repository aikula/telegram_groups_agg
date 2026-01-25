"""
Database module - SQLite operations
"""

import sqlite3
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class Database:
    """SQLite database manager"""
    
    def __init__(self, db_path: str = "data/messages.db"):
        """Initialize database connection"""
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    
    def init(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_message_id INTEGER UNIQUE NOT NULL,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                message_text TEXT,
                timestamp DATETIME NOT NULL,
                is_deleted BOOLEAN DEFAULT 0,
                deleted_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_timestamp 
            ON messages(chat_id, timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id 
            ON messages(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_deleted 
            ON messages(is_deleted)
        """)
        
        # Chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT NOT NULL,
                chat_type TEXT,
                bot_added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # Admin users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    def insert_message(self, telegram_message_id: int, chat_id: int, user_id: int,
                      username: str, first_name: str, last_name: str, 
                      message_text: str, timestamp: datetime) -> bool:
        """Insert a message into database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO messages 
                (telegram_message_id, chat_id, user_id, username, first_name, 
                 last_name, message_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (telegram_message_id, chat_id, user_id, username, 
                  first_name, last_name, message_text, timestamp))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Message {telegram_message_id} already exists")
            return False
        except Exception as e:
            logger.error(f"Error inserting message: {e}")
            return False
    
    def mark_deleted(self, telegram_message_id: int) -> bool:
        """Mark message as deleted"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE messages 
                SET is_deleted = 1, deleted_at = ?
                WHERE telegram_message_id = ?
            """, (datetime.now(), telegram_message_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error marking message deleted: {e}")
            return False
    
    def get_messages(self, chat_id: Optional[int] = None, 
                    days: int = 7, exclude_deleted: bool = True) -> List[Dict]:
        """Get messages from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM messages WHERE 1=1"
            params = []
            
            if chat_id:
                query += " AND chat_id = ?"
                params.append(chat_id)
            
            if exclude_deleted:
                query += " AND is_deleted = 0"
            
            query += " AND datetime(timestamp) >= datetime('now', '-' || ? || ' days')"
            params.append(days)
            
            query += " ORDER BY timestamp DESC"
            
            cursor.execute(query, params)
            messages = cursor.fetchall()
            conn.close()
            
            return [dict(m) for m in messages]
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []
    
    def add_chat(self, chat_id: int, chat_name: str, chat_type: str) -> bool:
        """Add or update chat in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO chats (chat_id, chat_name, chat_type)
                VALUES (?, ?, ?)
            """, (chat_id, chat_name, chat_type))
            
            conn.commit()
            conn.close()
            logger.info(f"Chat {chat_id} added/updated")
            return True
        except Exception as e:
            logger.error(f"Error adding chat: {e}")
            return False
    
    def get_chats(self, active_only: bool = True) -> List[Dict]:
        """Get all chats"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM chats"
            if active_only:
                query += " WHERE is_active = 1"
            
            cursor.execute(query)
            chats = cursor.fetchall()
            conn.close()
            
            return [dict(c) for c in chats]
        except Exception as e:
            logger.error(f"Error getting chats: {e}")
            return []
    
    def get_admin_user(self, username: str) -> Optional[Dict]:
        """Get admin user by username"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
            user = cursor.fetchone()
            conn.close()
            
            return dict(user) if user else None
        except Exception as e:
            logger.error(f"Error getting admin user: {e}")
            return None
    
    def add_admin_user(self, username: str, password_hash: str) -> bool:
        """Add admin user to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO admin_users (username, password_hash)
                VALUES (?, ?)
            """, (username, password_hash))
            
            conn.commit()
            conn.close()
            logger.info(f"Admin user {username} created")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Admin user {username} already exists")
            return False
        except Exception as e:
            logger.error(f"Error adding admin user: {e}")
            return False
