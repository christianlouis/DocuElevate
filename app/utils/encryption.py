"""
Encryption utilities for securing sensitive settings in the database.

Uses Fernet symmetric encryption with a key derived from SESSION_SECRET.
This provides encryption at rest for sensitive configuration values.
"""

import base64
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-load cryptography to avoid import errors if not installed
_cipher_suite = None
_primary_cipher = None


class EncryptionRotationError(RuntimeError):
    """Raised when encrypted data cannot be safely rotated to the primary key."""


def _derive_fernet(secret: str) -> object:
    """Derive a Fernet instance from a DocuElevate session secret."""
    from cryptography.fernet import Fernet

    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _get_cipher_suite() -> object | None:
    """
    Get or create the Fernet cipher suite for encryption/decryption.

    The encryption key is derived from SESSION_SECRET to ensure:
    1. Settings are encrypted at rest in the database
    2. The same key is used across app restarts
    3. No additional secret management needed

    Returns:
        Fernet cipher suite instance
    """
    global _cipher_suite, _primary_cipher

    if _cipher_suite is None:
        try:
            from cryptography.fernet import MultiFernet

            from app.config import settings

            if not settings.session_secret:
                raise ValueError("SESSION_SECRET is not configured")

            _primary_cipher = _derive_fernet(settings.session_secret)
            ciphers = [_primary_cipher]
            if settings.session_secret_previous:
                ciphers.append(_derive_fernet(settings.session_secret_previous))
            _cipher_suite = MultiFernet(ciphers)
            logger.debug("Encryption cipher suite initialized with %d key(s)", len(ciphers))

        except ImportError:
            logger.warning(
                "cryptography library not installed. "
                "Sensitive settings will be stored in plaintext. "
                "Install with: pip install cryptography"
            )
            _cipher_suite = None
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            _cipher_suite = None

    return _cipher_suite


def reset_cipher_cache() -> None:
    """Clear cached ciphers after settings changes and in isolated tests."""
    global _cipher_suite, _primary_cipher
    _cipher_suite = None
    _primary_cipher = None


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    """
    Encrypt a plaintext value for storage in the database.

    Args:
        plaintext: The value to encrypt (or None)

    Returns:
        Encrypted value as base64 string, or plaintext if encryption unavailable
    """
    if plaintext is None or plaintext == "":
        return plaintext

    cipher = _get_cipher_suite()

    if cipher is None:
        # Encryption not available, store in plaintext with warning
        logger.warning("Storing sensitive value in plaintext (encryption unavailable)")
        return plaintext

    try:
        encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))
        # Prefix with "enc:" to identify encrypted values
        return "enc:" + encrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        # Fall back to plaintext
        return plaintext


def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    """
    Decrypt a value from the database.

    Args:
        ciphertext: The encrypted value (or plaintext if not encrypted)

    Returns:
        Decrypted plaintext value
    """
    if ciphertext is None or ciphertext == "":
        return ciphertext

    # Check if value is encrypted (has "enc:" prefix)
    if not ciphertext.startswith("enc:"):
        # Not encrypted, return as-is
        return ciphertext

    cipher = _get_cipher_suite()

    if cipher is None:
        logger.error("Cannot decrypt value: encryption not available")
        return "[ENCRYPTED - Cannot decrypt]"

    try:
        # Remove "enc:" prefix and decrypt
        encrypted_bytes = ciphertext[4:].encode("utf-8")
        plaintext_bytes = cipher.decrypt(encrypted_bytes)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return "[DECRYPTION FAILED]"


def rotate_encrypted_value(value: Optional[str]) -> tuple[Optional[str], bool]:
    """Re-encrypt *value* with the current ``SESSION_SECRET`` when needed.

    Plaintext legacy values are encrypted as part of the same operation. Values
    already decryptable by the primary key are left byte-for-byte unchanged so
    the database rotation command is idempotent.
    """
    if value is None or value == "":
        return value, False

    cipher = _get_cipher_suite()
    if cipher is None or _primary_cipher is None:
        raise EncryptionRotationError("Encryption is unavailable")

    if not value.startswith("enc:"):
        encrypted = encrypt_value(value)
        if not encrypted or not encrypted.startswith("enc:"):
            raise EncryptionRotationError("Could not encrypt a legacy plaintext value")
        return encrypted, True

    token = value[4:].encode("utf-8")
    from cryptography.fernet import InvalidToken

    try:
        _primary_cipher.decrypt(token)
        return value, False
    except InvalidToken:
        logger.debug("Encrypted value requires rotation to the primary key")

    try:
        plaintext = cipher.decrypt(token)
        rotated = _primary_cipher.encrypt(plaintext)
        return "enc:" + rotated.decode("utf-8"), True
    except InvalidToken as exc:
        raise EncryptionRotationError("Value is not decryptable by the configured keyring") from exc


def value_uses_primary_key(value: Optional[str]) -> bool:
    """Return whether an encrypted value is protected by the primary key."""
    if value is None or value == "":
        return True
    if not value.startswith("enc:"):
        return False
    _get_cipher_suite()
    if _primary_cipher is None:
        return False
    from cryptography.fernet import InvalidToken

    try:
        _primary_cipher.decrypt(value[4:].encode("utf-8"))
        return True
    except InvalidToken:
        return False


def is_encrypted(value: Optional[str]) -> bool:
    """
    Check if a value is encrypted.

    Args:
        value: The value to check

    Returns:
        True if the value is encrypted, False otherwise
    """
    return value is not None and isinstance(value, str) and value.startswith("enc:")


def is_encryption_available() -> bool:
    """
    Check if encryption is available.

    Returns:
        True if cryptography library is installed and encryption is working
    """
    return _get_cipher_suite() is not None
