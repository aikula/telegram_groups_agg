"""
FastAPI Web Application - Main web server for analytics dashboard
"""

import logging
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("FastAPI application starting...")
    yield
    # Shutdown
    logger.info("FastAPI application shutting down...")


def create_app(db, bot_instance=None, config=None):
    """
    Create and configure the FastAPI application.

    Args:
        db: Database instance
        bot_instance: Optional TelegramBot instance for manual summaries
        config: Optional application configuration

    Returns:
        Configured FastAPI application
    """
    # Create FastAPI app
    app = FastAPI(
        title="Telegram Chat Analytics",
        description="Analytics dashboard for Telegram chat messages",
        version="1.0.0",
        lifespan=lifespan
    )

    # Get static files directory
    static_dir = Path(__file__).parent / "static"

    # Setup CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify actual origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and setup auth
    from app.web.auth import create_auth_manager, create_default_admin
    from app.web.routes import create_routes, setup_error_handlers

    # Create auth manager
    secret_key = getattr(config, 'jwt_secret', None) if config else None
    auth_manager = create_auth_manager(db, secret_key=secret_key)

    # Create default admin if not exists
    if config:
        create_default_admin(
            db,
            username=config.admin_username,
            password=config.admin_password
        )

    # Setup routes
    api_router = create_routes(db, auth_manager, bot_instance)
    app.include_router(api_router)

    # Setup error handlers
    setup_error_handlers(app)

    # Mount static files
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ========== Root Endpoints ==========

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Serve the main dashboard page."""
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return HTMLResponse("<h1>Dashboard not found. Please ensure static files are built.</h1>")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        """Serve the login page."""
        login_path = static_dir / "login.html"
        if login_path.exists():
            return FileResponse(str(login_path))
        return HTMLResponse("<h1>Login page not found.</h1>")

    # ========== API Documentation ==========

    @app.get("/api")
    async def api_info():
        """API information endpoint."""
        return {
            "name": "Telegram Chat Analytics API",
            "version": "1.0.0",
            "endpoints": {
                "auth": "/api/auth/login",
                "stats": "/api/stats/messages",
                "chats": "/api/chats",
                "messages": "/api/messages",
                "export": "/api/export/csv",
                "summary": "/api/summary/manual",
                "health": "/api/health"
            }
        }

    # Store dependencies for access in routes
    app.state.db = db
    app.state.auth_manager = auth_manager
    app.state.bot = bot_instance

    logger.info("FastAPI application created successfully")

    return app


# For development/testing
async def create_dev_app():
    """
    Create a development app with in-memory database.

    Only for testing purposes.
    """
    from app.database import Database

    # Create temporary database
    db = Database(":memory:")
    db.init()

    # Create test admin
    from app.web.auth import create_default_admin
    create_default_admin(db, "admin", "password")

    return create_app(db=db)


if __name__ == "__main__":
    import uvicorn

    # For direct running (development only)
    async def main():
        app = await create_dev_app()
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

    import asyncio
    asyncio.run(main())
