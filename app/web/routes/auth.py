"""
Authentication Routes - Login and user management (v2.0)

Supports:
- Telegram OAuth login (widget-based)
- Superadmin password login (fallback)
- Username/password login (legacy, for compatibility)
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.web.auth import (
    LoginRequest,
    TokenResponse,
    UserInfo,
    TelegramAuthRequest,
    SuperadminLoginRequest
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginResponse(BaseModel):
    """Login response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str


class MeResponse(BaseModel):
    """Current user response model."""
    user_id: int
    username: str
    is_superadmin: bool


@router.post("/telegram", response_model=TokenResponse)
async def login_telegram(request: Request, auth_data: TelegramAuthRequest):
    """
    Authenticate via Telegram OAuth Login Widget.

    This endpoint receives data from Telegram Login Widget and returns JWT token.

    Request body should contain:
        - id: Telegram user ID
        - first_name: User's first name
        - last_name: User's last name (optional)
        - username: Username (optional)
        - photo_url: Profile photo URL (optional)
        - auth_date: Authentication timestamp
        - hash: Data hash for verification

    Returns:
        Access token and expiration time
    """
    auth_manager = request.app.state.auth_manager

    logger.info(f"Telegram auth attempt for user_id: {auth_data.id}")

    # Convert Pydantic model to dict
    auth_data_dict = {
        "id": auth_data.id,
        "first_name": auth_data.first_name,
        "last_name": auth_data.last_name,
        "username": auth_data.username,
        "photo_url": auth_data.photo_url,
        "auth_date": auth_data.auth_date,
        "hash": auth_data.hash
    }

    result = await auth_manager.login_telegram(auth_data_dict)

    if not result:
        logger.warning(f"Failed Telegram auth for user_id: {auth_data.id}")
        raise HTTPException(status_code=401, detail="Invalid Telegram authentication data")

    logger.info(f"Successful Telegram auth for user_id: {auth_data.id}")

    return result


@router.post("/superadmin", response_model=TokenResponse)
async def login_superadmin(request: Request, credentials: SuperadminLoginRequest):
    """
    Authenticate as superadmin using username and password.

    This is a fallback authentication method for administrative access.

    Request body:
        - username: Superadmin username
        - password: Superadmin password

    Returns:
        Access token and expiration time
    """
    auth_manager = request.app.state.auth_manager

    logger.info(f"Superadmin login attempt for user: {credentials.username}")

    result = await auth_manager.login_superadmin(credentials.username, credentials.password)

    if not result:
        logger.warning(f"Failed superadmin login attempt for user: {credentials.username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    logger.info(f"Successful superadmin login for user: {credentials.username}")

    return result


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, credentials: LoginRequest):
    """
    Authenticate user with username/password (legacy method).

    This endpoint is kept for backward compatibility.
    For new integrations, use Telegram OAuth instead.

    Request body:
        - username: Username
        - password: Password

    Returns:
        Access token, expiration, and username
    """
    auth_manager = request.app.state.auth_manager

    logger.info(f"Login attempt for user: {credentials.username}")

    result = await auth_manager.login(credentials.username, credentials.password)

    if not result:
        logger.warning(f"Failed login attempt for user: {credentials.username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    logger.info(f"Successful login for user: {credentials.username}")

    return LoginResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
        username=credentials.username
    )


@router.get("/me", response_model=MeResponse)
async def get_current_user(request: Request):
    """
    Get current authenticated user info.

    Requires valid Bearer token in Authorization header.

    Returns:
        Current user information
    """
    from app.web.middleware import required_auth

    user: UserInfo = await required_auth(request)

    return MeResponse(
        user_id=user.user_id,
        username=user.username,
        is_superadmin=user.is_superadmin
    )


@router.post("/logout")
async def logout():
    """
    Logout endpoint.

    Note: JWT tokens are stateless, so logout is handled client-side
    by discarding the token. This endpoint exists for API completeness
    and potential future token blacklisting.

    Returns:
        Success message
    """
    return {"message": "Logged out successfully"}


@router.get("/config")
async def get_config(request: Request):
    """
    Get current configuration (for debugging).

    Requires superadmin access.

    Returns:
        Current configuration including bot username, enabled features
    """
    from app.web.middleware import required_auth

    user = await required_auth(request)

    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    from app.config import settings

    return {
        "telegram_bot_username": settings.telegram_bot_username or "Not configured",
        "telegram_bot_token_configured": bool(settings.telegram_bot_token),
        "superadmin_username": settings.superadmin_username,
        "superadmin_password_configured": bool(settings.superadmin_password_hash),
        "llm_api_key_configured": bool(settings.llm_api_key),
        "llm_model": settings.llm_model_name,
        "encryption_enabled": bool(settings.encryption_master_key),
        "webhook_url": settings.telegram_webhook_url or "Not configured"
    }


class OTPLoginRequest(BaseModel):
    """OTP login request model."""
    code: str


@router.post("/otp", response_model=TokenResponse)
async def login_otp(request: Request, otp_data: OTPLoginRequest):
    """
    Authenticate using one-time password from Telegram bot.

    User sends /login to bot, receives 6-digit code, and enters it here.

    Request body:
        - code: 6-digit OTP code from bot

    Returns:
        Access token and expiration time
    """
    auth_manager = request.app.state.auth_manager
    db = request.app.state.db

    logger.info(f"OTP login attempt for code: {otp_data.code}")

    # Verify OTP
    user_data = await db.verify_otp(otp_data.code)

    if not user_data:
        logger.warning(f"Failed OTP login for code: {otp_data.code}")
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    logger.info(f"Successful OTP login for telegram_id: {user_data['telegram_id']}")

    # Generate JWT token
    from app.web.auth import create_access_token
    token, expires_in = create_access_token(
        username=user_data['username'],
        user_id=user_data['user_id'],
        is_superadmin=False
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in
    )
