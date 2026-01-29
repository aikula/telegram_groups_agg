"""
FastAPI Web Application - Main web server for analytics dashboard (v2.0)
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.db import get_database
from app.bot.bot import get_bot

logger = logging.getLogger(__name__)

# Singleton instance
_app: Optional[FastAPI] = None


async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses.

    Adds OWASP recommended security headers:
    - X-Content-Type-Options: nosniff (prevent MIME sniffing)
    - X-Frame-Options: DENY (prevent clickjacking)
    - X-XSS-Protection: 1; mode=block (enable XSS filter)
    - Strict-Transport-Security: max-age=31536000 (HTTPS only)
    - Content-Security-Policy: default-src 'self' (restrict resources)

    Note: HSTS is only added in production (not debug mode).
          CSP is permissive for development.

    Args:
        request: FastAPI request
        call_next: Next middleware/handler

    Returns:
        Response with security headers
    """
    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable browser XSS filter
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # HSTS (HTTPS only in production)
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy (permissive for development)
    # In production, consider stricter policies
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",  # Allow inline scripts + Chart.js CDN
        "style-src 'self' 'unsafe-inline'",  # Allow inline styles
        "img-src 'self' data: https:",  # Allow data URLs and HTTPS images
        "font-src 'self' data:",  # Allow data URLs for fonts
        "connect-src 'self' https://cdn.jsdelivr.net",  # API calls + Chart.js source maps
        "frame-ancestors 'none'",  # Prevent embedding in frames
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy (restrict browser features)
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Args:
        app: FastAPI application instance
    """
    # Import auth module here to avoid circular dependency
    from app.web.auth import create_default_admin

    # Startup
    logger.info("FastAPI application starting...")

    # Initialize database
    db = get_database()
    await db.init_database()

    # Create default superadmin if password hash is set
    if settings.superadmin_password_hash:
        await create_default_admin(
            db,
            username="superadmin",
            password_hash=settings.superadmin_password_hash
        )

    yield

    # Shutdown
    logger.info("FastAPI application shutting down...")


def get_app() -> FastAPI:
    """
    Get FastAPI application singleton.

    Returns:
        FastAPI application instance
    """
    global _app
    if _app is None:
        _app = _create_app()
    return _app


def get_app_state() -> dict:
    """
    Get application state.

    Returns:
        Application state dictionary
    """
    app = get_app()
    return {
        "db": app.state.db,
        "auth_manager": app.state.auth_manager,
        "bot": app.state.bot,
    }


def _create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    # Create FastAPI app
    app = FastAPI(
        title="Telegram Chat Analytics",
        description="Analytics dashboard for Telegram chat messages (v2.0)",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Get static files directory
    static_dir = Path(__file__).parent / "static"
    templates_dir = Path(__file__).parent / "templates"

    # Setup CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify actual origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and setup middleware
    from app.web.middleware import request_id_middleware
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(security_headers_middleware)

    # Import and setup auth
    from app.web.auth import AuthManager, create_default_admin

    # Create database instance
    db = get_database()

    # Create auth manager with JWT secret from config
    auth_manager = AuthManager(
        db=db,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_expire_minutes
    )

    # Create default superadmin if password hash is set
    # Note: This will be handled during lifespan startup

    # Store dependencies in app state
    app.state.db = db
    app.state.auth_manager = auth_manager
    app.state.bot = None  # Will be set when bot starts

    # Setup routes
    from app.web.routes import auth, stats, chats, messages, export, health, webhook, admin, bot, summary, feedback
    from app.web.middleware import auth_required

    # Include routers
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"], dependencies=[auth_required])
    app.include_router(chats.router, prefix="/api/chats", tags=["Chats"], dependencies=[auth_required])
    app.include_router(messages.router, prefix="/api/messages", tags=["Messages"], dependencies=[auth_required])
    app.include_router(export.router, prefix="/api/export", tags=["Export"], dependencies=[auth_required])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin"], dependencies=[auth_required])
    app.include_router(bot.router, prefix="/api/bot", tags=["Bot"], dependencies=[auth_required])
    app.include_router(summary.router, prefix="/api/summary", tags=["Summary"], dependencies=[auth_required])
    app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"], dependencies=[auth_required])
    app.include_router(health.router, prefix="/api", tags=["Health"])

    # Webhook route (no auth required, validated by Telegram)
    app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])

    # Setup error handlers
    _setup_error_handlers(app)

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
        """Serve the login page with bot username injected."""
        import asyncio

        login_path = static_dir / "login.html"
        if login_path.exists():
            bot_username = settings.telegram_bot_username

            # Use asyncio.to_thread for non-blocking file read (Python 3.9+)
            loop = asyncio.get_event_loop()
            html_content = await loop.run_in_executor(
                None,
                lambda: login_path.read_text(encoding="utf-8")
            )

            if not bot_username:
                # Hide Telegram widget section if not configured
                html_content = html_content.replace(
                    '<div id="telegram-login-btn"',
                    '<div id="telegram-login-btn" style="display: none;"'
                )
            else:
                # Replace bot username - widget needs it WITHOUT @ prefix
                # Remove @ if user included it
                clean_username = bot_username.lstrip('@')
                html_content = html_content.replace("'YOUR_BOT_USERNAME'", f"'{clean_username}'")

            # Add cache busting headers
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }

            return HTMLResponse(content=html_content, headers=headers)
        return HTMLResponse("<h1>Login page not found.</h1>")

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin.html", response_class=HTMLResponse)
    async def admin_page(request: Request):
        """Serve the superadmin panel page.

        Server-side auth check is performed via Authorization header.
        For browser navigation, a cookie-based session is checked.
        """
        from app.web.middleware import required_auth

        # Check authentication - allow both Bearer token and cookie
        try:
            user = await required_auth(request)
        except HTTPException:
            # Return 401 with JSON for AJAX, or redirect for navigation
            auth_header = request.headers.get("Authorization")
            if auth_header:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Authentication required"}
                )
            # For browser navigation without auth, show login link
            return HTMLResponse(
                '<html><body><h1>Authentication Required</h1>'
                '<p><a href="/login">Login via Telegram</a></p></body></html>',
                status_code=401
            )

        # Check superadmin permission
        if not user.is_superadmin:
            return HTMLResponse(
                '<html><body><h1>Access Denied</h1>'
                '<p>Superadmin access required.</p></body></html>',
                status_code=403
            )

        admin_path = static_dir / "admin.html"
        if admin_path.exists():
            return FileResponse(str(admin_path))
        return HTMLResponse("<h1>Admin panel not found.</h1>")

    # ========== API Documentation ==========

    @app.get("/api")
    async def api_info():
        """API information endpoint."""
        return {
            "name": "Telegram Chat Analytics API",
            "version": "2.0.0",
            "endpoints": {
                "auth": "/api/auth",
                "stats": "/api/stats",
                "chats": "/api/chats",
                "messages": "/api/messages",
                "export": "/api/export",
                "health": "/api/health",
                "webhook": "/webhook/telegram",
                "docs": "/api/docs"
            }
        }

    logger.info("FastAPI application created successfully")

    return app


def _setup_error_handlers(app: FastAPI) -> None:
    """
    Setup global error handlers for the FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail}
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )


async def set_webhook(bot_instance, webhook_url: str) -> bool:
    """
    Set Telegram bot webhook.

    Args:
        bot_instance: Bot instance
        webhook_url: Webhook URL

    Returns:
        True if successful, False otherwise
    """
    try:
        from aiogram.types import WebhookInfo

        webhook_info = WebhookInfo(url=webhook_url)
        await bot_instance.set_webhook(webhook_info)
        logger.info(f"Webhook set to: {webhook_url}")
        return True

    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False


async def delete_webhook(bot_instance) -> bool:
    """
    Delete Telegram bot webhook.

    Args:
        bot_instance: Bot instance

    Returns:
        True if successful, False otherwise
    """
    try:
        await bot_instance.delete_webhook()
        logger.info("Webhook deleted")
        return True

    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        return False
