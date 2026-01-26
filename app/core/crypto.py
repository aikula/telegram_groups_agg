"""
Core cryptography module - Per-chat AES-256 encryption

Algorithm: Fernet (AES-128-CBC + HMAC-SHA256)
Key derivation: SHA256(master_key + chat_id) -> Base64

Each chat gets a unique encryption key derived from the master key.
This ensures that compromising one chat's key doesn't affect others.
"""

import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class ChatCrypto:
    """
    Per-chat AES-256 encryption/decryption using Fernet.

    The encryption key for each chat is derived from the master key
    using SHA256(master_key + str(chat_id)). This ensures each chat
    has a unique encryption key.

    Example:
        crypto = ChatCrypto(settings.encryption_master_key)
        encrypted = crypto.encrypt(chat_id=-1001234567890, text="Hello world")
        decrypted = crypto.decrypt(chat_id=-1001234567890, encrypted=encrypted)
        assert decrypted == "Hello world"
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize ChatCrypto with master key.

        Args:
            master_key: Base64-encoded 32 bytes. If None, uses settings.encryption_master_key.

        Raises:
            ValueError: If master_key is invalid base64 or too short.
        """
        self.master_key = master_key or settings.encryption_master_key
        self._validate_master_key()
        self._decoded_master_key = base64.urlsafe_b64decode(self.master_key)

    def _validate_master_key(self) -> None:
        """Validate that master key is valid base64 and at least 32 bytes."""
        try:
            decoded = base64.urlsafe_b64decode(self.master_key)
            if len(decoded) < 32:
                raise ValueError(
                    f"Master key must be at least 32 bytes when decoded, got {len(decoded)}"
                )
        except Exception as e:
            raise ValueError(f"Invalid master key: {e}")

    def _derive_chat_key(self, chat_id: int) -> bytes:
        """
        Derive unique 32-byte encryption key for a specific chat.

        The key is derived using SHA256(master_key + str(chat_id)).
        This ensures each chat has a unique key while remaining deterministic.

        Args:
            chat_id: Telegram chat ID (usually negative for groups/supergroups)

        Returns:
            Base64-encoded 32-byte key suitable for Fernet
        """
        # Create a deterministic key for this chat
        key_material = hashlib.sha256(
            self._decoded_master_key + str(chat_id).encode()
        ).digest()

        # Fernet requires a 32-byte base64-encoded key
        return base64.urlsafe_b64encode(key_material)

    def _get_fernet(self, chat_id: int) -> Fernet:
        """Get Fernet instance for specific chat."""
        chat_key = self._derive_chat_key(chat_id)
        return Fernet(chat_key)

    def encrypt(self, chat_id: int, text: str) -> str:
        """
        Encrypt text for a specific chat.

        Args:
            chat_id: Telegram chat ID
            text: Plain text to encrypt

        Returns:
            Base64-encoded encrypted text (Fernet token)

        Raises:
            ValueError: If text is not a string
            Exception: If encryption fails
        """
        if not isinstance(text, str):
            raise ValueError(f"Text must be string, got {type(text)}")

        if not text:
            return ""

        try:
            f = self._get_fernet(chat_id)
            encrypted = f.encrypt(text.encode("utf-8"))
            return encrypted.decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Encryption failed for chat {chat_id}: {e}")

    def decrypt(self, chat_id: int, encrypted: str) -> str:
        """
        Decrypt text for a specific chat.

        Args:
            chat_id: Telegram chat ID
            encrypted: Base64-encoded encrypted text (Fernet token)

        Returns:
            Decrypted plain text

        Raises:
            InvalidToken: If decryption fails (wrong key, corrupted data, etc.)
            ValueError: If encrypted is not a string
        """
        if not isinstance(encrypted, str):
            raise ValueError(f"Encrypted must be string, got {type(encrypted)}")

        if not encrypted:
            return ""

        try:
            f = self._get_fernet(chat_id)
            decrypted = f.decrypt(encrypted.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken as e:
            raise InvalidToken(
                f"Decryption failed for chat {chat_id}. "
                f"This may indicate a wrong encryption key or corrupted data."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Decryption failed for chat {chat_id}: {e}")

    def get_key_hash(self, chat_id: int) -> str:
        """
        Get hash of the chat's encryption key for identification purposes.

        Useful for GDPR/key rotation verification without exposing the actual key.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Hexadecimal SHA256 hash of the derived chat key
        """
        chat_key = self._derive_chat_key(chat_id)
        return hashlib.sha256(chat_key).hexdigest()

    def re_encrypt(
        self,
        old_chat_id: int,
        new_chat_id: int,
        encrypted: str
    ) -> str:
        """
        Re-encrypt data from one chat key to another.

        Useful for chat ID changes or key rotation scenarios.

        Args:
            old_chat_id: Original chat ID for decryption
            new_chat_id: New chat ID for encryption
            encrypted: Data encrypted with old_chat_id key

        Returns:
            Data encrypted with new_chat_id key
        """
        decrypted = self.decrypt(old_chat_id, encrypted)
        return self.encrypt(new_chat_id, decrypted)

    def is_encrypted(self, data: str) -> bool:
        """
        Check if data looks like Fernet-encrypted content.

        This is a heuristic check and not 100% reliable.
        Fernet tokens have specific structure with version byte.

        Args:
            data: String to check

        Returns:
            True if data looks like Fernet token, False otherwise
        """
        if not isinstance(data, str) or len(data) < 44:
            return False

        try:
            # Fernet tokens are base64, should decode without error
            # Structure: version(1) + timestamp(8) + IV(16) + ciphertext + HMAC(32)
            decoded = base64.urlsafe_b64decode(data)
            # Minimum length: version(1) + timestamp(8) + IV(16) + HMAC(32) = 57 bytes
            if len(decoded) < 57:
                return False

            # Fernet version byte must be 0x80 (128)
            if decoded[0] != 0x80:
                return False

            # Length should be multiple of 16 bytes (AES block size) + version byte
            # After removing version byte, the rest should be divisible by 16
            return (len(decoded) - 1) % 16 == 0

        except (ValueError, TypeError):
            return False
        except Exception:
            return False


# Singleton instance using settings
_default_crypto: Optional[ChatCrypto] = None


def get_crypto(master_key: Optional[str] = None) -> ChatCrypto:
    """
    Get ChatCrypto instance (singleton by default).

    Args:
        master_key: Optional custom master key. If None, uses settings.

    Returns:
        ChatCrypto instance
    """
    global _default_crypto

    if master_key is not None:
        return ChatCrypto(master_key)

    if _default_crypto is None:
        _default_crypto = ChatCrypto(settings.encryption_master_key)

    return _default_crypto
