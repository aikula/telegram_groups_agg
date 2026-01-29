"""
Authentication Routes - Login and user management (v2.0)

Supports:
- Telegram OAuth login (widget-based)
- Superadmin password login (fallback)
- Username/password login (legacy, for compatibility)
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.web.auth import (
    LoginRequest,
    TokenResponse,
    UserInfo,
    TelegramAuthRequest,
    SuperadminLoginRequest,
    OTPRequest,
    OTPVerifyRequest
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
async def login_telegram(request: Request, response: Response, auth_data: TelegramAuthRequest):
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

    Sets cookie:
        - auth_token: JWT token for browser navigation
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

    # Set cookie for browser navigation (httpOnly for security)
    from app.config import settings
    response.set_cookie(
        key="auth_token",
        value=result.access_token,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
        httponly=True,
        samesite="lax"
    )

    return result


@router.post("/superadmin", response_model=TokenResponse)
async def login_superadmin(request: Request, response: Response, credentials: SuperadminLoginRequest):
    """
    Authenticate as superadmin using username and password.

    This is a fallback authentication method for administrative access.

    Request body:
        - username: Superadmin username
        - password: Superadmin password

    Returns:
        Access token and expiration time

    Sets cookie:
        - auth_token: JWT token for browser navigation
    """
    auth_manager = request.app.state.auth_manager

    logger.info(f"Superadmin login attempt for user: {credentials.username}")

    result = await auth_manager.login_superadmin(credentials.username, credentials.password)

    if not result:
        logger.warning(f"Failed superadmin login attempt for user: {credentials.username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    logger.info(f"Successful superadmin login for user: {credentials.username}")

    # Set cookie for browser navigation (httpOnly for security)
    from app.config import settings
    response.set_cookie(
        key="auth_token",
        value=result.access_token,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
        httponly=True,
        samesite="lax"
    )

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
async def logout(response: Response):
    """
    Logout endpoint.

    Clears the auth cookie. JWT tokens are stateless, so client-side
    token discarding is also recommended.

    Returns:
        Success message
    """
    response.delete_cookie(key="auth_token", path="/")
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
    """OTP login request model (legacy)."""
    code: str


@router.post("/request-otp")
async def request_otp(request: Request, otp_request: OTPRequest):
    """
    Request OTP code for authentication.

    Generates a 6-digit OTP code and sends it to user via Telegram bot.

    Request body:
        - telegram_id: Telegram user ID

    Returns:
        Success message with code validity period

    Rate limit: 3 requests per minute per telegram_id
    """
    from app.core.rate_limiter import get_rate_limiter

    db = request.app.state.db
    rate_limiter = get_rate_limiter()
    telegram_id = otp_request.telegram_id

    # Rate limiting by telegram_id
    allowed, retry_after = await rate_limiter.check_api_rate_limit(
        endpoint="otp_request",
        identifier=str(telegram_id)
    )

    if not allowed:
        logger.warning(
            f"OTP request rate limited for telegram_id: {telegram_id}, "
            f"retry_after: {retry_after}"
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many OTP requests. Try again in {int(retry_after or 60)} seconds.",
            headers={"Retry-After": str(int(retry_after or 60))}
        )

    logger.info(f"OTP request for telegram_id: {telegram_id}")

    # Get or create user by telegram_id
    user = await db.get_user_by_telegram_id(telegram_id)

    if not user:
        # Create user without data - will be populated when they verify OTP
        success = await db.create_user_from_telegram(
            telegram_id=telegram_id,
            username=f"user_{telegram_id}",
            first_name="",
            last_name=""
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create user")

        user = await db.get_user_by_telegram_id(telegram_id)

    # Generate OTP code (valid for 5 minutes)
    otp_code = await db.create_otp(
        user_id=user['id'],
        telegram_id=telegram_id,
        valid_minutes=5
    )

    # Send OTP to user via Telegram bot
    try:
        from app.config import settings
        import httpx

        bot_token = settings.telegram_bot_token
        if not bot_token:
            raise HTTPException(status_code=500, detail="Bot not configured")

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": f"🔐 Your authentication code: {otp_code}\n\nValid for 5 minutes.\n\nIf you didn't request this, ignore this message."
                }
            )

        # Security: Don't log the actual OTP code
        logger.info(f"OTP sent successfully to telegram_id: {telegram_id}")

    except Exception as e:
        logger.error(f"Failed to send OTP via Telegram: {e}")
        # Still return success - OTP was created and can be verified
        # The bot might be unable to send messages, but the code exists

    return {
        "message": "OTP code sent to your Telegram",
        "expires_in": 300  # 5 minutes in seconds
    }


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(request: Request, otp_verify: OTPVerifyRequest):
    """
    Verify OTP code and return JWT token.

    Request body:
        - telegram_id: Telegram user ID
        - otp: 6-digit OTP code

    Returns:
        Access token and expiration time

    Rate limit: 10 requests per minute per telegram_id
    """
    from app.core.rate_limiter import get_rate_limiter

    db = request.app.state.db
    rate_limiter = get_rate_limiter()
    telegram_id = otp_verify.telegram_id

    # Rate limiting by telegram_id
    allowed, retry_after = await rate_limiter.check_api_rate_limit(
        endpoint="otp_verify",
        identifier=str(telegram_id)
    )

    if not allowed:
        logger.warning(
            f"OTP verify rate limited for telegram_id: {telegram_id}, "
            f"retry_after: {retry_after}"
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many verification attempts. Try again in {int(retry_after or 60)} seconds.",
            headers={"Retry-After": str(int(retry_after or 60))}
        )

    logger.info(f"OTP verify attempt for telegram_id: {telegram_id}")

    logger.info(f"OTP verify attempt for telegram_id: {otp_verify.telegram_id}")

    # Verify OTP
    user_data = await db.verify_otp(otp_verify.otp)

    if not user_data or user_data.get('telegram_id') != otp_verify.telegram_id:
        logger.warning(f"Failed OTP verification for telegram_id: {otp_verify.telegram_id}")
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    logger.info(f"Successful OTP verification for telegram_id: {user_data['telegram_id']}")

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


@router.post("/otp", response_model=TokenResponse)
async def login_otp(request: Request, otp_data: OTPLoginRequest):
    """
    Authenticate using one-time password from Telegram bot (legacy endpoint).

    User sends /login to bot, receives 6-digit code, and enters it here.

    DEPRECATED: Use /api/auth/verify-otp instead.

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
