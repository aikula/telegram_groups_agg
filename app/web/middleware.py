"""
Web Middleware - Authentication and other middleware for FastAPI (v2.0)
"""

import logging
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param

from app.web.auth import decode_access_token, UserInfo

logger = logging.getLogger(__name__)


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


async def get_current_user(authorization: str = Header(None)) -> Optional[UserInfo]:
    """
    Get current user from bearer token.

    Args:
        authorization: Authorization header value

    Returns:
        UserInfo if valid token, None otherwise
    """
    token = await get_bearer_token(authorization)

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

    Args:
        request: FastAPI request object

    Returns:
        UserInfo if valid token, None otherwise
    """
    auth_header = request.headers.get("Authorization")
    return await get_current_user(auth_header)


# FastAPI dependency for required auth
async def required_auth(request: Request) -> UserInfo:
    """
    Required authentication dependency.

    Returns user info if valid token provided, raises 401 otherwise.

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

    auth_header = request.headers.get("Authorization")
    user = await get_current_user(auth_header)

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
        chat_id: Chat ID to check membership for

    Returns:
        UserInfo if user has access

    Raises:
        HTTPException: If user is not a member of the chat
    """
    user = await required_auth(request)

    # Superadmins can access any chat
    if user.is_superadmin:
        return user

    # Check if user is a member of the chat
    db = request.app.state.db
    is_member = await db.is_chat_member(user.user_id, chat_id)

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
        chat_id: Chat ID to check
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

    db = request.app.state.db

    # Check if user is a member first
    is_member = await db.is_chat_member(user.user_id, chat_id)
    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this chat"
        )

    # Get user's role in chat
    cursor = await db._execute("""
        SELECT role FROM chat_members
        WHERE user_id = ? AND chat_id = ? AND left_at IS NULL
    """, (user.user_id, chat_id))
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
        chat_id: Chat ID

    Returns:
        User's role (member/admin/owner)
    """
    user = await required_auth(request)

    # Superadmins are effectively owners
    if user.is_superadmin:
        return UserRole.OWNER

    db = request.app.state.db

    cursor = await db._execute("""
        SELECT role FROM chat_members
        WHERE user_id = ? AND chat_id = ? AND left_at IS NULL
    """, (user.user_id, chat_id))
    result = await cursor.fetchone()

    return result[0] if result and result[0] else UserRole.MEMBER
