"""
Encryption utilities for securing sensitive settings in the database.

Uses Fernet symmetric encryption with a key derived from SESSION_SECRET.
This provides encryption at rest for sensitive configuration values.
"""

import logging
import base64
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-load cryptography to avoid import errors if not installed
_cipher_suite = None


def _get_cipher_suite():
    """
    Get or create the Fernet cipher suite for encryption/decryption.
    
    The encryption key is derived from SESSION_SECRET to ensure:
    1. Settings are encrypted at rest in the database
    2. The same key is used across app restarts
    3. No additional secret management needed
    
    Returns:
        Fernet cipher suite instance
    """
    global _cipher_suite
    
    if _cipher_suite is None:
        try:
            from cryptography.fernet import Fernet
            from app.config import settings
            
            # Derive a Fernet-compatible key from SESSION_SECRET
            # Fernet requires a 32-byte base64-encoded key
            secret = settings.session_secret.encode('utf-8')
            
            # Use SHA256 to get exactly 32 bytes, then base64 encode
            key_bytes = hashlib.sha256(secret).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            
            _cipher_suite = Fernet(fernet_key)
            logger.debug("Encryption cipher suite initialized")
            
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
        encrypted_bytes = cipher.encrypt(plaintext.encode('utf-8'))
        # Prefix with "enc:" to identify encrypted values
        return "enc:" + encrypted_bytes.decode('utf-8')
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
        encrypted_bytes = ciphertext[4:].encode('utf-8')
        plaintext_bytes = cipher.decrypt(encrypted_bytes)
        return plaintext_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return "[DECRYPTION FAILED]"


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
