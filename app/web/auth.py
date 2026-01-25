"""
Authentication Module - JWT token based authentication for web API
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from pydantic import BaseModel, ValidationError
import jwt

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = "your-secret-key-change-this-in-production"  # Should be from config
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    username: str


class User(BaseModel):
    """User model."""
    username: str
    is_admin: bool = True


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
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
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def create_access_token(username: str, secret_key: str = None) -> str:
    """
    Create a JWT access token.

    Args:
        username: Username to encode in token
        secret_key: Secret key for signing (uses default if not provided)

    Returns:
        JWT token string
    """
    key = secret_key or JWT_SECRET_KEY

    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
        "is_admin": True
    }

    token = jwt.encode(payload, key, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str, secret_key: str = None) -> Optional[dict]:
    """
    Decode and verify a JWT access token.

    Args:
        token: JWT token string
        secret_key: Secret key for verification (uses default if not provided)

    Returns:
        Decoded payload dict or None if invalid
    """
    key = secret_key or JWT_SECRET_KEY

    try:
        payload = jwt.decode(token, key, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def authenticate_user(db, username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user against the database.

    Args:
        db: Database instance
        username: Username
        password: Plain text password

    Returns:
        User dict if authenticated, None otherwise
    """
    user = db.get_admin_user(username)

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
            "username": user['username'],
            "is_admin": True
        }
    else:
        logger.warning(f"Authentication failed: invalid password for user '{username}'")
        return None


def create_default_admin(db, username: str, password: str) -> bool:
    """
    Create a default admin user if one doesn't exist.

    Args:
        db: Database instance
        username: Admin username
        password: Admin password

    Returns:
        True if user created or already exists, False on error
    """
    # Check if user already exists
    existing_user = db.get_admin_user(username)
    if existing_user:
        logger.info(f"Admin user '{username}' already exists")
        return True

    # Create new user
    password_hash = hash_password(password)
    success = db.add_admin_user(username, password_hash)

    if success:
        logger.info(f"Created default admin user '{username}'")
    else:
        logger.error(f"Failed to create admin user '{username}'")

    return success


class AuthManager:
    """
    Authentication manager for handling login, token generation, and verification.
    """

    def __init__(self, db, secret_key: str = None):
        """
        Initialize the auth manager.

        Args:
            db: Database instance
            secret_key: JWT secret key (uses default if not provided)
        """
        self.db = db
        self.secret_key = secret_key or JWT_SECRET_KEY

    def login(self, username: str, password: str) -> Optional[TokenResponse]:
        """
        Handle user login and return access token.

        Args:
            username: Username
            password: Plain text password

        Returns:
            TokenResponse if successful, None otherwise
        """
        user = authenticate_user(self.db, username, password)

        if not user:
            return None

        access_token = create_access_token(username, self.secret_key)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            username=username
        )

    def verify_token(self, token: str) -> Optional[User]:
        """
        Verify a JWT token and return user info.

        Args:
            token: JWT token string

        Returns:
            User object if valid, None otherwise
        """
        payload = decode_access_token(token, self.secret_key)

        if not payload:
            return None

        return User(
            username=payload.get('username'),
            is_admin=payload.get('is_admin', False)
        )

    def create_user(self, username: str, password: str) -> bool:
        """
        Create a new admin user.

        Args:
            username: Username
            password: Plain text password

        Returns:
            True if successful, False otherwise
        """
        password_hash = hash_password(password)
        return self.db.add_admin_user(username, password_hash)


async def get_current_user(token: str, auth_manager: AuthManager) -> Optional[User]:
    """
    Get the current user from a bearer token.

    This is intended for use with FastAPI Depends.

    Args:
        token: Bearer token string (without "Bearer " prefix)
        auth_manager: AuthManager instance

    Returns:
        User object if valid, None otherwise
    """
    if not token:
        return None

    return auth_manager.verify_token(token)


def create_auth_manager(db, secret_key: str = None) -> AuthManager:
    """
    Factory function to create an AuthManager instance.

    Args:
        db: Database instance
        secret_key: Optional JWT secret key

    Returns:
        AuthManager instance
    """
    return AuthManager(db=db, secret_key=secret_key)
