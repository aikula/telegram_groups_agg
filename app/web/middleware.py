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
