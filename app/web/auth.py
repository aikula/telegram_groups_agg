"""
Authentication Module - JWT token based authentication for web API (v2.0)
Supports Telegram OAuth and superadmin password authentication.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import jwt
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Request/Response Models
class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class TelegramAuthRequest(BaseModel):
    """Telegram OAuth auth request model."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class SuperadminLoginRequest(BaseModel):
    """Superadmin login request model."""
    username: str
    password: str


class OTPRequest(BaseModel):
    """OTP request model."""
    telegram_id: int


class OTPVerifyRequest(BaseModel):
    """OTP verification request model."""
    telegram_id: int
    otp: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    """User info model."""
    user_id: int
    username: str
    is_superadmin: bool


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    # Use bcrypt directly to avoid passlib's validation issues
    import bcrypt as bcrypt_lib
    # bcrypt has a 72 byte limit, use SHA256 to handle longer passwords
    import hashlib
    password_bytes = password.encode('utf-8')
    # SHA256 gives us 32 bytes, well within the 72 byte limit
    password_hash = hashlib.sha256(password_bytes).digest()
    # Salt and hash
    salt = bcrypt_lib.gensalt()
    hashed = bcrypt_lib.hashpw(password_hash, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        import bcrypt as bcrypt_lib
        import hashlib
        password_bytes = plain_password.encode('utf-8')
        password_hash = hashlib.sha256(password_bytes).digest()
        return bcrypt_lib.checkpw(password_hash, hashed_password.encode('utf-8'))
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def create_access_token(username: str, user_id: int, is_superadmin: bool = False) -> tuple[str, int]:
    """
    Create a JWT access token.

    Args:
        username: Username to encode in token
        user_id: User ID to encode in token
        is_superadmin: Whether user is superadmin

    Returns:
        Tuple of (token string, expires in seconds)
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": str(user_id),
        "username": username,
        "is_superadmin": is_superadmin,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    from jose.exceptions import ExpiredSignatureError, JWTError

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except JWTError as e:
        logger.warning(f"Invalid token: {e}")
        return None


async def authenticate_user(db, username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user against the database.

    Args:
        db: Database instance
        username: Username
        password: Plain text password

    Returns:
        User dict if authenticated, None otherwise
    """
    user = await db.get_user_by_username(username)

    if not user:
        logger.warning(f"Authentication failed: user '{username}' not found")
        return None

    stored_hash = user.get('password_hash')
    if not stored_hash:
        logger.error(f"User '{username}' has no password hash")
        return None

    if verify_password(password, stored_hash):
        logger.info(f"User '{username}' authenticated successfully")
        return {
            "user_id": user['id'],
            "username": user['username'],
            "is_superadmin": user.get('is_superadmin', 0) == 1
        }
    else:
        logger.warning(f"Authentication failed: invalid password for user '{username}'")
        return None


def verify_telegram_auth(auth_data: dict, bot_token: str) -> bool:
    """
    Verify Telegram Login Widget auth data.

    Args:
        auth_data: Dict from Telegram widget with id, first_name, username, auth_date, hash
        bot_token: Bot token for verification

    Returns:
        True if auth is valid, False otherwise
    """
    # Check if auth_date is not too old (max 24 hours)
    import time
    auth_date = auth_data.get('auth_date', 0)
    if time.time() - auth_date > 86400:  # 24 hours
        logger.warning("Telegram auth data is too old")
        return False

    # Create data check string
    # Data must be sorted alphabetically before hashing
    check_string = '\n'.join(
        f"{k}={v}"
        for k, v in sorted(auth_data.items())
        if k != 'hash'  # Exclude hash from check string
    )

    # Create secret key from bot token
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # Calculate expected hash
    expected_hash = hmac.new(
        secret_key,
        check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare hashes
    received_hash = auth_data.get('hash', '')
    is_valid = hmac.compare_digest(expected_hash, received_hash)

    if is_valid:
        logger.info(f"Telegram auth verified for user {auth_data.get('id')}")
    else:
        logger.warning(f"Telegram auth verification failed for user {auth_data.get('id')}")

    return is_valid


async def authenticate_telegram_user(db, auth_data: dict, bot_token: str) -> Optional[dict]:
    """
    Authenticate or create user via Telegram OAuth.

    Args:
        db: Database instance
        auth_data: Telegram auth data from widget
        bot_token: Bot token for verification

    Returns:
        User dict if authenticated, None otherwise
    """
    # First verify the auth data hash
    if not verify_telegram_auth(auth_data, bot_token):
        logger.warning(f"Invalid Telegram auth data for user {auth_data.get('id')}")
        return None

    # Get or create user by Telegram ID
    telegram_id = auth_data.get('id')
    username = auth_data.get('username') or auth_data.get('first_name', f'user_{telegram_id}')

    user = await db.get_user_by_telegram_id(telegram_id)

    if not user:
        # Create new user from Telegram data
        success = await db.create_user_from_telegram(
            telegram_id=telegram_id,
            username=username,
            first_name=auth_data.get('first_name', ''),
            last_name=auth_data.get('last_name', '')
        )

        if not success:
            logger.error(f"Failed to create user from Telegram data: {telegram_id}")
            return None

        # Get the created user
        user = await db.get_user_by_telegram_id(telegram_id)

    return {
        "user_id": user['id'],
        "username": user['username'],
        "is_superadmin": user.get('is_superadmin', 0) == 1
    }


async def authenticate_superadmin(db, username: str, password: str) -> Optional[dict]:
    """
    Authenticate superadmin using username and password.

    Args:
        db: Database instance
        username: Username
        password: Plain text password

    Returns:
        User dict if authenticated, None otherwise
    """
    # Check if superadmin password hash is set in config
    superadmin_hash = getattr(settings, 'superadmin_password_hash', None)

    if not superadmin_hash:
        logger.warning("Superadmin password not configured")
        return None

    # Verify username matches configured superadmin username
    configured_username = getattr(settings, 'superadmin_username', 'superadmin')
    if username != configured_username:
        logger.warning(f"Invalid superadmin username: {username}")
        return None

    if not verify_password(password, superadmin_hash):
        logger.warning(f"Invalid superadmin password for user: {username}")
        return None

    # Get or create superadmin user
    user = await db.get_user_by_username(username)

    if not user:
        # Create superadmin user
        success = await db.create_user(
            username=username,
            password_hash=superadmin_hash,
            is_superadmin=1
        )

        if not success:
            logger.error(f"Failed to create superadmin user: {username}")
            return None

        user = await db.get_user_by_username(username)

    return {
        "user_id": user['id'],
        "username": user['username'],
        "is_superadmin": True
    }


async def create_default_admin(db, username: str = "superadmin", password_hash: str = None) -> bool:
    """
    Create a default superadmin user if one doesn't exist.

    Args:
        db: Database instance
        username: Admin username
        password_hash: Pre-hashed password (for security)

    Returns:
        True if user created or already exists, False on error
    """
    # Check if user already exists
    existing_user = await db.get_user_by_username(username)
    if existing_user:
        logger.info(f"Superadmin user '{username}' already exists")
        return True

    # Create new user with provided hash or generate one
    if not password_hash:
        logger.warning("No password hash provided for default admin, skipping creation")
        return False

    success = await db.create_user(
        username=username,
        password_hash=password_hash,
        is_superadmin=1
    )

    if success:
        logger.info(f"Created default superadmin user '{username}'")
    else:
        logger.error(f"Failed to create superadmin user '{username}'")

    return success


class AuthManager:
    """
    Authentication manager for handling login, token generation, and verification.
    """

    def __init__(
        self,
        db,
        secret_key: str = None,
        algorithm: str = "HS256",
        expire_minutes: int = 10080
    ):
        """
        Initialize the auth manager.

        Args:
            db: Database instance
            secret_key: JWT secret key (uses default if not provided)
            algorithm: JWT algorithm
            expire_minutes: Token expiration in minutes
        """
        self.db = db
        self.secret_key = secret_key or settings.jwt_secret_key
        self.algorithm = algorithm or settings.jwt_algorithm
        self.expire_minutes = expire_minutes or settings.jwt_expire_minutes

    async def login(self, username: str, password: str) -> Optional[TokenResponse]:
        """
        Handle user login and return access token.

        Args:
            username: Username
            password: Plain text password

        Returns:
            TokenResponse if successful, None otherwise
        """
        user = await authenticate_user(self.db, username, password)

        if not user:
            return None

        token, expires_in = create_access_token(
            username=user["username"],
            user_id=user["user_id"],
            is_superadmin=user["is_superadmin"]
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in
        )

    def verify_token(self, token: str) -> Optional[UserInfo]:
        """
        Verify a JWT token and return user info.

        Args:
            token: JWT token string

        Returns:
            UserInfo object if valid, None otherwise
        """
        payload = decode_access_token(token)

        if not payload:
            return None

        return UserInfo(
            user_id=int(payload.get("sub", 0)),
            username=payload.get("username", ""),
            is_superadmin=payload.get("is_superadmin", False)
        )

    async def create_user(self, username: str, password: str, is_superadmin: bool = False) -> bool:
        """
        Create a new admin user.

        Args:
            username: Username
            password: Plain text password
            is_superadmin: Whether user is superadmin

        Returns:
            True if successful, False otherwise
        """
        password_hash = hash_password(password)
        return await self.db.create_user(
            username=username,
            password_hash=password_hash,
            is_superadmin=1 if is_superadmin else 0
        )

    async def login_telegram(self, auth_data: dict) -> Optional[TokenResponse]:
        """
        Handle Telegram OAuth login and return access token.

        Args:
            auth_data: Telegram auth data from widget (id, first_name, username, auth_date, hash)

        Returns:
            TokenResponse if successful, None otherwise
        """
        from app.config import settings

        user = await authenticate_telegram_user(
            self.db,
            auth_data,
            settings.telegram_bot_token
        )

        if not user:
            return None

        token, expires_in = create_access_token(
            username=user["username"],
            user_id=user["user_id"],
            is_superadmin=user["is_superadmin"]
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in
        )

    async def login_superadmin(self, username: str, password: str) -> Optional[TokenResponse]:
        """
        Handle superadmin password login and return access token.

        Args:
            username: Username
            password: Plain text password

        Returns:
            TokenResponse if successful, None otherwise
        """
        user = await authenticate_superadmin(self.db, username, password)

        if not user:
            return None

        token, expires_in = create_access_token(
            username=user["username"],
            user_id=user["user_id"],
            is_superadmin=True
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in
        )
