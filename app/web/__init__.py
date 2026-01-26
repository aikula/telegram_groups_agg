"""
Web API module - FastAPI application

Exports:
- get_app: Get FastAPI application singleton
- get_app_state: Get application state
"""

from app.web.app import get_app, get_app_state, lifespan

__all__ = ["get_app", "get_app_state", "lifespan"]
