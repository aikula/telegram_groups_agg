"""
Tests for FastAPI web endpoints
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

# Import modules to test
from app.web.app import create_app
from app.web.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_auth_manager
)


# ========== Auth Tests ==========

def test_hash_password():
    """Test password hashing"""
    password = "test_password_123"
    hashed = hash_password(password)

    assert hashed != password
    assert len(hashed) > 20
    assert isinstance(hashed, str)


def test_verify_password():
    """Test password verification"""
    password = "test_password_123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_verify_password_invalid_hash():
    """Test password verification with invalid hash"""
    assert verify_password("password", "invalid_hash") is False


def test_create_access_token():
    """Test JWT token creation"""
    username = "testuser"
    token = create_access_token(username)

    assert isinstance(token, str)
    assert len(token) > 50


def test_decode_access_token_valid():
    """Test JWT token decoding with valid token"""
    username = "testuser"
    token = create_access_token(username)

    payload = decode_access_token(token)

    assert payload is not None
    assert payload["username"] == username
    assert "exp" in payload


def test_decode_access_token_invalid():
    """Test JWT token decoding with invalid token"""
    payload = decode_access_token("invalid_token")

    assert payload is None


def test_decode_access_token_expired():
    """Test JWT token decoding with expired token"""
    # Create a token that's already expired
    import jwt
    from datetime import datetime, timedelta

    expired_payload = {
        "username": "test",
        "exp": datetime.utcnow() - timedelta(hours=1),
        "iat": datetime.utcnow()
    }

    expired_token = jwt.encode(expired_payload, "your-secret-key-change-this-in-production", algorithm="HS256")

    payload = decode_access_token(expired_token)

    assert payload is None


@pytest.fixture
def mock_auth_db():
    """Mock database for auth tests"""
    db = Mock()
    db.get_admin_user = Mock(return_value={
        "username": "admin",
        "password_hash": hash_password("password")
    })
    db.add_admin_user = Mock(return_value=True)
    return db


def test_auth_manager_init(mock_auth_db):
    """Test AuthManager initialization"""
    auth_manager = create_auth_manager(mock_auth_db)

    assert auth_manager.db == mock_auth_db
    assert auth_manager.secret_key is not None


def test_auth_manager_login_success(mock_auth_db):
    """Test successful login"""
    auth_manager = create_auth_manager(mock_auth_db)

    result = auth_manager.login("admin", "password")

    assert result is not None
    assert result.access_token is not None
    assert result.username == "admin"


def test_auth_manager_login_wrong_password(mock_auth_db):
    """Test login with wrong password"""
    auth_manager = create_auth_manager(mock_auth_db)

    result = auth_manager.login("admin", "wrong_password")

    assert result is None


def test_auth_manager_login_unknown_user(mock_auth_db):
    """Test login with unknown user"""
    mock_auth_db.get_admin_user = Mock(return_value=None)

    auth_manager = create_auth_manager(mock_auth_db)

    result = auth_manager.login("unknown", "password")

    assert result is None


def test_auth_manager_verify_token_valid(mock_auth_db):
    """Test token verification with valid token"""
    auth_manager = create_auth_manager(mock_auth_db)

    token = create_access_token("admin", auth_manager.secret_key)
    user = auth_manager.verify_token(token)

    assert user is not None
    assert user.username == "admin"


def test_auth_manager_verify_token_invalid(mock_auth_db):
    """Test token verification with invalid token"""
    auth_manager = create_auth_manager(mock_auth_db)

    user = auth_manager.verify_token("invalid_token")

    assert user is None


# ========== FastAPI App Tests ==========

@pytest.fixture
def mock_app_db():
    """Mock database for app tests"""
    db = Mock()
    db.get_admin_user = Mock(return_value={
        "username": "admin",
        "password_hash": hash_password("password")
    })
    db.add_admin_user = Mock(return_value=True)
    db.get_chats = Mock(return_value=[
        {"chat_id": 123, "chat_name": "Test Chat", "chat_type": "group", "bot_added_at": "2024-01-01"}
    ])
    db.get_messages = Mock(return_value=[
        {
            "id": 1,
            "telegram_message_id": 100,
            "chat_id": 123,
            "user_id": 456,
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "message_text": "Hello world",
            "timestamp": "2024-01-01 12:00:00"
        }
    ])
    return db


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.admin_username = "admin"
    config.admin_password = "password"
    config.openrouter_api_key = "test_key"
    return config


@pytest.fixture
def test_app(mock_app_db, mock_config):
    """Create test FastAPI app"""
    return create_app(db=mock_app_db, config=mock_config)


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    return TestClient(test_app)


def test_app_creation(test_app):
    """Test app creation"""
    assert test_app is not None
    assert test_app.title == "Telegram Chat Analytics"


def test_root_endpoint(test_client):
    """Test root endpoint"""
    response = test_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_page(test_client):
    """Test login page"""
    response = test_client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_api_info(test_client):
    """Test API info endpoint"""
    response = test_client.get("/api")

    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data


def test_health_check(test_client):
    """Test health check endpoint"""
    response = test_client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_login_success(test_client):
    """Test successful login via API"""
    response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "password"
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "admin"


def test_login_wrong_password(test_client):
    """Test login with wrong password"""
    response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong_password"
    })

    assert response.status_code == 401


def test_login_missing_fields(test_client):
    """Test login with missing fields"""
    response = test_client.post("/api/auth/login", json={
        "username": "admin"
    })

    # Should get validation error
    assert response.status_code == 422


def test_protected_endpoint_without_token(test_client):
    """Test accessing protected endpoint without token"""
    response = test_client.get("/api/stats/messages")

    assert response.status_code == 401


def test_protected_endpoint_with_invalid_token(test_client):
    """Test accessing protected endpoint with invalid token"""
    response = test_client.get(
        "/api/stats/messages",
        headers={"Authorization": "Bearer invalid_token"}
    )

    assert response.status_code == 401


def test_get_chats_with_token(test_client):
    """Test getting chats list with valid token"""
    # First login to get token
    login_response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "password"
    })
    token = login_response.json()["access_token"]

    # Then use token to get chats
    response = test_client.get(
        "/api/chats",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_message_stats_with_token(test_client):
    """Test getting message stats with valid token"""
    # First login to get token
    login_response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "password"
    })
    token = login_response.json()["access_token"]

    # Then use token to get stats
    response = test_client.get(
        "/api/stats/messages?days=7",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "total_messages" in data
    assert "active_users" in data


def test_export_csv_with_token(test_client):
    """Test CSV export with valid token"""
    # First login to get token
    login_response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "password"
    })
    token = login_response.json()["access_token"]

    # Then use token to export
    response = test_client.get(
        "/api/export/csv?days=7",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]


def test_get_messages_with_token(test_client):
    """Test getting messages with valid token"""
    # First login to get token
    login_response = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "password"
    })
    token = login_response.json()["access_token"]

    # Then use token to get messages
    response = test_client.get(
        "/api/messages?days=7&limit=10",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "total" in data


# ========== Route Handler Tests ==========

def test_create_routes(mock_app_db, mock_config):
    """Test routes creation"""
    from app.web.routes import create_routes

    auth_manager = create_auth_manager(mock_app_db)
    router = create_routes(mock_app_db, auth_manager, bot_instance=None)

    assert router is not None
    assert len(router.routes) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
