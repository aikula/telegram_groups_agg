"""
Web Middleware - Authentication and other middleware for FastAPI (v2.0)
"""

import logging
import uuid
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param

from app.web.auth import decode_access_token, UserInfo

logger = logging.getLogger(__name__)


async def request_id_middleware(request: Request, call_next):
    """
    Middleware to add request ID to all requests for log tracing.

    Generates a unique request ID and adds it to the request state.
    The ID is then included in all log messages for that request.

    Args:
        request: Incoming FastAPI request
        call_next: Next middleware/route to call

    Returns:
        Response with X-Request-ID header
    """
    # Generate or get request ID from header
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())

    # Add to request state for access in routes
    request.state.request_id = request_id

    # Process request
    response = await call_next(request)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id

    return response


async def get_bearer_token(authorization: str = Header(None)) -> Optional[str]:
    """
    Extract bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        Token string or None
    """
    if authorization:
        scheme, token = get_authorization_scheme_param(authorization)
        if scheme.lower() == "bearer":
            return token
    return None


def _get_user_from_token(token: Optional[str]) -> Optional[UserInfo]:
    """
    Get user info from JWT token string (internal helper).

    Args:
        token: JWT token string

    Returns:
        UserInfo if valid token, None otherwise
    """
    if not token:
        return None

    payload = decode_access_token(token)

    if not payload:
        return None

    return UserInfo(
        user_id=int(payload.get("sub", 0)),
        username=payload.get("username", ""),
        is_superadmin=payload.get("is_superadmin", False)
    )


async def get_current_user(
    authorization: str = Header(None),
    auth_token: str = Header(None, alias="X-Auth-Token")
) -> Optional[UserInfo]:
    """
    Get current user from bearer token or X-Auth-Token header.

    Supports both:
    - Authorization: Bearer <token> header (for API calls)
    - X-Auth-Token: <token> header (for browser navigation, set via cookie)

    Args:
        authorization: Authorization header value
        auth_token: X-Auth-Token header value (from cookie)

    Returns:
        UserInfo if valid token, None otherwise
    """
    # Try Authorization header first (Bearer token)
    token = await get_bearer_token(authorization)

    # Fall back to X-Auth-Token header (for browser requests)
    if not token and auth_token:
        token = auth_token

    return _get_user_from_token(token)


async def get_current_user_required(authorization: str = Header(None)) -> UserInfo:
    """
    Get current user from bearer token, raise 401 if missing.

    Args:
        authorization: Authorization header value

    Returns:
        UserInfo if valid token

    Raises:
        HTTPException: If token is missing or invalid
    """
    user = await get_current_user(authorization)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")

    return user


async def require_superadmin(user: UserInfo = None) -> UserInfo:
    """
    Require superadmin role.

    Args:
        user: User info from get_current_user

    Returns:
        UserInfo if superadmin

    Raises:
        HTTPException: If user is not superadmin
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin role required")

    return user


# FastAPI dependency for optional auth
async def optional_auth(request: Request) -> Optional[UserInfo]:
    """
    Optional authentication dependency.

    Returns user info if valid token provided, None otherwise.

    Checks:
    1. Authorization header (Bearer token)
    2. auth_token cookie (for browser navigation)

    Args:
        request: FastAPI request object

    Returns:
        UserInfo if valid token, None otherwise
    """
    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    token = None

    if auth_header:
        scheme, token_candidate = get_authorization_scheme_param(auth_header)
        if scheme.lower() == "bearer":
            token = token_candidate

    # Fall back to cookie
    if not token:
        token = request.cookies.get("auth_token")

    return _get_user_from_token(token)


# FastAPI dependency for required auth
async def required_auth(request: Request) -> UserInfo:
    """
    Required authentication dependency.

    Returns user info if valid token provided, raises 401 otherwise.

    Checks:
    1. Authorization header (Bearer token)
    2. auth_token cookie (for browser navigation)

    Args:
        request: FastAPI request object

    Returns:
        UserInfo if valid token

    Raises:
        HTTPException: If token is missing or invalid
    """
    # Check if user is already set (for testing or internal calls)
    if hasattr(request.state, 'user') and request.state.user:
        return request.state.user

    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    token = None

    if auth_header:
        scheme, token_candidate = get_authorization_scheme_param(auth_header)
        if scheme.lower() == "bearer":
            token = token_candidate

    # Fall back to cookie
    if not token:
        token = request.cookies.get("auth_token")

    user = _get_user_from_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")

    return user


async def require_chat_membership(request: Request, chat_id: int) -> UserInfo:
    """
    Verify user is a member of the specified chat.

    Superadmins can access any chat.
    Regular users must be members of the chat.

    Args:
        request: FastAPI request object
        chat_id: Telegram chat ID (will be converted to internal id)

    Returns:
        UserInfo if user has access

    Raises:
        HTTPException: If user is not a member of the chat
    """
    user = await required_auth(request)

    # Superadmins can access any chat
    if user.is_superadmin:
        return user

    # Convert Telegram chat_id to internal id (chats.id)
    db = request.app.state.db
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )
    internal_id = chat["id"]

    # Check if user is a member of the chat using internal id
    is_member = await db.is_chat_member(user.user_id, internal_id)

    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this chat"
        )

    return user


# Middleware dependencies for use in router dependencies
auth_required = Depends(required_auth)
optional_auth_dependency = Depends(optional_auth)


# ============================================================================
# Role-Based Authorization (v2.2)
# ============================================================================

class UserRole:
    """User roles in a chat (v2.2 - Role-based authorization)."""
    MEMBER = "member"    # Read-only access, can chat with bot
    ADMIN = "admin"      # Can modify settings, manage members
    OWNER = "owner"      # Full control + transfer ownership (future)


async def require_chat_role(
    request: Request,
    chat_id: int,
    min_role: str = UserRole.MEMBER
) -> UserInfo:
    """
    Require user to have minimum role in chat.

    Role hierarchy: owner > admin > member

    Args:
        request: FastAPI request object
        chat_id: Telegram chat ID (will be converted to internal id)
        min_role: Minimum required role (member/admin/owner)

    Returns:
        UserInfo if user has required role

    Raises:
        HTTPException: If user lacks required role
    """
    user = await required_auth(request)

    # Superadmins bypass role checks
    if user.is_superadmin:
        return user

    # Convert Telegram chat_id to internal id (chats.id)
    db = request.app.state.db
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )
    internal_id = chat["id"]

    # Check if user is a member first using internal id
    is_member = await db.is_chat_member(user.user_id, internal_id)
    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this chat"
        )

    # Get user's telegram_id for role lookup
    # Note: chat_members.user_id stores telegram_id, not internal users.id
    # But for backward compatibility, if telegram_id is NULL, use user.user_id
    async with db.get_connection() as conn:
        cursor = await conn.execute(
            """SELECT telegram_id FROM users WHERE id = ?""",
            (user.user_id,)
        )
        user_row = await cursor.fetchone()
        user_telegram_id = user_row[0] if user_row and user_row[0] else None

        # Use telegram_id if available, otherwise fall back to user.user_id
        # This handles both old users (where id = telegram_id) and new users (where telegram_id is set)
        chat_member_user_id = user_telegram_id if user_telegram_id else user.user_id

        # Get user's role in chat - check BOTH telegram_id AND user.id for backward compatibility
        # This handles the case where a user has multiple records (legacy id=telegram_id vs new with telegram_id set)
        cursor = await conn.execute(
            """SELECT role FROM chat_members
               WHERE user_id = ? AND chat_id = ? AND left_at IS NULL
               UNION
               SELECT role FROM chat_members
               WHERE user_id = ? AND chat_id = ? AND left_at IS NULL""",
            (chat_member_user_id, internal_id, user.user_id, internal_id)
        )
        result = await cursor.fetchone()

    user_role = result[0] if result and result[0] else UserRole.MEMBER

    # Role hierarchy
    role_hierarchy = {
        UserRole.MEMBER: 1,
        UserRole.ADMIN: 2,
        UserRole.OWNER: 3
    }

    if role_hierarchy.get(user_role, 0) < role_hierarchy.get(min_role, 0):
        raise HTTPException(
            status_code=403,
            detail=f"This action requires {min_role} role or higher"
        )

    return user


async def can_modify_chat_settings(request: Request, chat_id: int) -> UserInfo:
    """
    Check if user can modify chat settings.

    Authorization rules:
    - superadmin: can modify any chat settings
    - chat admin/owner: can modify their own chat settings
    - chat member: CANNOT modify settings (403 Forbidden)

    Args:
        request: FastAPI request
        chat_id: Chat ID

    Returns:
        UserInfo if authorized

    Raises:
        HTTPException: If not authorized
    """
    return await require_chat_role(request, chat_id, min_role=UserRole.ADMIN)


async def get_user_role_in_chat(request: Request, chat_id: int) -> str:
    """
    Get user's role in a chat.

    Args:
        request: FastAPI request
        chat_id: Telegram chat ID (will be converted to internal id)

    Returns:
        User's role (member/admin/owner)
    """
    user = await required_auth(request)

    # Superadmins are effectively owners
    if user.is_superadmin:
        return UserRole.OWNER

    # Convert Telegram chat_id to internal id (chats.id)
    db = request.app.state.db
    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        return UserRole.MEMBER  # Chat doesn't exist, return default

    internal_id = chat["id"]

    # Get user's role using proper connection method
    # Note: chat_members.user_id stores telegram_id, need to get it first
    async with db.get_connection() as conn:
        # Get telegram_id (if exists) for lookup in chat_members
        cursor = await conn.execute(
            """SELECT telegram_id FROM users WHERE id = ?""",
            (user.user_id,)
        )
        user_row = await cursor.fetchone()
        user_telegram_id = user_row[0] if user_row and user_row[0] else None

        # Use telegram_id if available, otherwise fall back to user.user_id
        chat_member_user_id = user_telegram_id if user_telegram_id else user.user_id

        cursor = await conn.execute(
            """SELECT role FROM chat_members
               WHERE user_id = ? AND chat_id = ? AND left_at IS NULL""",
            (chat_member_user_id, internal_id)
        )
        result = await cursor.fetchone()

    return result[0] if result and result[0] else UserRole.MEMBER
