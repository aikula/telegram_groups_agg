"""
Web API Routes - Individual route modules for FastAPI (v2.0)
"""

from app.web.routes import auth, stats, chats, messages, export, health, webhook, admin, bot, summary, feedback

__all__ = ["auth", "stats", "chats", "messages", "export", "health", "webhook", "admin", "bot", "summary", "feedback"]
