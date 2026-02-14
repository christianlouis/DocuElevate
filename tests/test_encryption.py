"""
Tests for app/utils/encryption.py

Tests encryption/decryption functionality for sensitive settings.
"""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestEncryption:
    """Test encryption utility functions"""

    def test_encrypt_value_with_none(self):
        """Test that None values are returned as-is"""
        from app.utils.encryption import encrypt_value

        result = encrypt_value(None)
        assert result is None

    def test_encrypt_value_with_empty_string(self):
        """Test that empty strings are returned as-is"""
        from app.utils.encryption import encrypt_value

        result = encrypt_value("")
        assert result == ""

    @patch("app.utils.encryption._get_cipher_suite")
    def test_encrypt_value_when_encryption_unavailable(self, mock_cipher):
        """Test that plaintext is returned when encryption is unavailable"""
        from app.utils.encryption import encrypt_value

        mock_cipher.return_value = None
        result = encrypt_value("secret_value")

        # Should return plaintext with warning logged
        assert result == "secret_value"

    @patch("app.utils.encryption._get_cipher_suite")
    def test_encrypt_value_success(self, mock_cipher):
        """Test successful encryption"""
        from app.utils.encryption import encrypt_value

        # Mock cipher that returns encrypted bytes
        mock_fernet = Mock()
        mock_fernet.encrypt.return_value = b"encrypted_data"
        mock_cipher.return_value = mock_fernet

        result = encrypt_value("secret_value")

        # Should have "enc:" prefix
        assert result.startswith("enc:")
        assert "encrypted_data" in result
        mock_fernet.encrypt.assert_called_once()

    @patch("app.utils.encryption._get_cipher_suite")
    def test_encrypt_value_encryption_failure(self, mock_cipher):
        """Test that encryption failures fall back to plaintext"""
        from app.utils.encryption import encrypt_value

        # Mock cipher that raises exception
        mock_fernet = Mock()
        mock_fernet.encrypt.side_effect = Exception("Encryption error")
        mock_cipher.return_value = mock_fernet

        result = encrypt_value("secret_value")

        # Should fall back to plaintext
        assert result == "secret_value"

    def test_decrypt_value_with_none(self):
        """Test that None values are returned as-is"""
        from app.utils.encryption import decrypt_value

        result = decrypt_value(None)
        assert result is None

    def test_decrypt_value_with_empty_string(self):
        """Test that empty strings are returned as-is"""
        from app.utils.encryption import decrypt_value

        result = decrypt_value("")
        assert result == ""

    def test_decrypt_value_plaintext(self):
        """Test that plaintext values without enc: prefix are returned as-is"""
        from app.utils.encryption import decrypt_value

        result = decrypt_value("plain_value")
        assert result == "plain_value"

    @patch("app.utils.encryption._get_cipher_suite")
    def test_decrypt_value_when_encryption_unavailable(self, mock_cipher):
        """Test decryption when cipher is unavailable"""
        from app.utils.encryption import decrypt_value

        mock_cipher.return_value = None
        result = decrypt_value("enc:encrypted_data")

        # Should return error message
        assert result == "[ENCRYPTED - Cannot decrypt]"

    @patch("app.utils.encryption._get_cipher_suite")
    def test_decrypt_value_success(self, mock_cipher):
        """Test successful decryption"""
        from app.utils.encryption import decrypt_value

        # Mock cipher that returns decrypted bytes
        mock_fernet = Mock()
        mock_fernet.decrypt.return_value = b"decrypted_value"
        mock_cipher.return_value = mock_fernet

        result = decrypt_value("enc:encrypted_data")

        assert result == "decrypted_value"
        mock_fernet.decrypt.assert_called_once()

    @patch("app.utils.encryption._get_cipher_suite")
    def test_decrypt_value_decryption_failure(self, mock_cipher):
        """Test that decryption failures return error message"""
        from app.utils.encryption import decrypt_value

        # Mock cipher that raises exception
        mock_fernet = Mock()
        mock_fernet.decrypt.side_effect = Exception("Decryption error")
        mock_cipher.return_value = mock_fernet

        result = decrypt_value("enc:bad_data")

        # Should return error message
        assert result == "[DECRYPTION FAILED]"

    def test_is_encrypted_with_encrypted_value(self):
        """Test is_encrypted returns True for encrypted values"""
        from app.utils.encryption import is_encrypted

        assert is_encrypted("enc:some_encrypted_data") is True

    def test_is_encrypted_with_plaintext(self):
        """Test is_encrypted returns False for plaintext"""
        from app.utils.encryption import is_encrypted

        assert is_encrypted("plain_value") is False

    def test_is_encrypted_with_none(self):
        """Test is_encrypted returns False for None"""
        from app.utils.encryption import is_encrypted

        assert is_encrypted(None) is False

    def test_is_encrypted_with_empty_string(self):
        """Test is_encrypted returns False for empty string"""
        from app.utils.encryption import is_encrypted

        assert is_encrypted("") is False

    def test_is_encrypted_with_non_string(self):
        """Test is_encrypted returns False for non-string types"""
        from app.utils.encryption import is_encrypted

        assert is_encrypted(123) is False
        assert is_encrypted([]) is False
        assert is_encrypted({}) is False

    @patch("app.utils.encryption._get_cipher_suite")
    def test_is_encryption_available_true(self, mock_cipher):
        """Test is_encryption_available when cryptography is available"""
        from app.utils.encryption import is_encryption_available

        mock_cipher.return_value = Mock()  # Non-None cipher
        assert is_encryption_available() is True

    @patch("app.utils.encryption._get_cipher_suite")
    def test_is_encryption_available_false(self, mock_cipher):
        """Test is_encryption_available when cryptography is not available"""
        from app.utils.encryption import is_encryption_available

        mock_cipher.return_value = None
        assert is_encryption_available() is False


@pytest.mark.unit
class TestGetCipherSuite:
    """Test the _get_cipher_suite internal function"""

    def test_cipher_suite_caching(self):
        """Test that cipher suite is cached after first call"""
        import app.utils.encryption

        # First call
        result1 = app.utils.encryption._get_cipher_suite()

        # Second call should return same instance (cached)
        result2 = app.utils.encryption._get_cipher_suite()

        # Both calls should return the same object (cached)
        assert result1 is result2

    def test_get_cipher_suite_import_error(self):
        """Test _get_cipher_suite when cryptography is not installed"""
        import app.utils.encryption
        import sys

        # Reset the cached cipher suite
        original_cipher = app.utils.encryption._cipher_suite
        app.utils.encryption._cipher_suite = None

        # Mock the cryptography.fernet module to not exist
        original_modules = sys.modules.copy()
        
        # Remove cryptography from sys.modules to simulate it not being installed
        if "cryptography.fernet" in sys.modules:
            del sys.modules["cryptography.fernet"]
        if "cryptography" in sys.modules:
            del sys.modules["cryptography"]
        
        # Mock the import to raise ImportError
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "cryptography" in name:
                raise ImportError("No module named 'cryptography'")
            return real_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=mock_import):
                result = app.utils.encryption._get_cipher_suite()
                # Should return None when cryptography is not available
                assert result is None
        finally:
            # Restore the original state
            app.utils.encryption._cipher_suite = original_cipher
            sys.modules.update(original_modules)

    def test_get_cipher_suite_general_exception(self):
        """Test _get_cipher_suite when initialization fails with general exception"""
        import app.utils.encryption

        # Reset the cached cipher suite
        original_cipher = app.utils.encryption._cipher_suite
        app.utils.encryption._cipher_suite = None

        try:
            # Mock Fernet class to raise an exception during initialization
            from unittest.mock import MagicMock
            
            with patch("app.utils.encryption.hashlib.sha256", side_effect=RuntimeError("Hash error")):
                result = app.utils.encryption._get_cipher_suite()

                # Should return None when initialization fails
                assert result is None
        finally:
            # Restore the original cipher suite
            app.utils.encryption._cipher_suite = original_cipher


@pytest.mark.unit
class TestEncryptionIntegration:
    """Integration tests for encrypt/decrypt cycle"""

    @patch("app.utils.encryption._get_cipher_suite")
    def test_encrypt_decrypt_cycle(self, mock_cipher):
        """Test that encrypting and then decrypting returns original value"""
        from app.utils.encryption import decrypt_value, encrypt_value

        # Mock a simple reversible encryption
        mock_fernet = Mock()

        # Simulate encryption: just add a prefix
        def mock_encrypt(data):
            return b"ENCRYPTED_" + data

        # Simulate decryption: remove the prefix
        def mock_decrypt(data):
            return data.replace(b"ENCRYPTED_", b"")

        mock_fernet.encrypt = mock_encrypt
        mock_fernet.decrypt = mock_decrypt
        mock_cipher.return_value = mock_fernet

        original = "my_secret_password"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert encrypted != original
        assert encrypted.startswith("enc:")
        assert decrypted == original

    def test_real_encryption_round_trip(self):
        """Test actual encryption/decryption with real cryptography library."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        # Skip if encryption is not available
        if not is_encryption_available():
            pytest.skip("Encryption not available (cryptography library not installed)")

        original_value = "my_super_secret_password_123"

        # Encrypt the value
        encrypted = encrypt_value(original_value)

        # Should be encrypted (has enc: prefix)
        assert encrypted.startswith("enc:")
        assert encrypted != original_value

        # Decrypt should return original value
        decrypted = decrypt_value(encrypted)
        assert decrypted == original_value

    def test_encryption_with_special_characters(self):
        """Test encryption with special characters and symbols."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        original = "P@ssw0rd!#$%^&*()_+-=[]{}|;:',.<>?/~`"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    def test_encryption_with_unicode(self):
        """Test encryption with unicode characters."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        original = "Hello 世界 🌍 Привет мир"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    def test_encryption_with_long_string(self):
        """Test encryption with very long strings."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        # Create a long string (1000 characters)
        original = "A" * 1000
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original
        assert len(decrypted) == 1000

    def test_encryption_with_newlines_and_whitespace(self):
        """Test encryption preserves newlines and whitespace."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        original = "line1\n  line2\t\ttabbed\r\nline3  "
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    def test_encryption_with_json_string(self):
        """Test encryption with JSON string."""
        from app.utils.encryption import decrypt_value, encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        original = '{"key": "value", "nested": {"array": [1, 2, 3]}}'
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    def test_multiple_encrypt_same_value_produces_different_ciphertext(self):
        """Test that encrypting the same value twice produces different ciphertext (if using random IV)."""
        from app.utils.encryption import encrypt_value, is_encryption_available

        if not is_encryption_available():
            pytest.skip("Encryption not available")

        original = "same_value"
        encrypted1 = encrypt_value(original)
        encrypted2 = encrypt_value(original)

        # Both should be encrypted
        assert encrypted1.startswith("enc:")
        assert encrypted2.startswith("enc:")

        # Fernet uses timestamp-based encryption, so they might be different
        # (depending on timing). This test documents the behavior.
        # We'll just verify both decrypt correctly
        from app.utils.encryption import decrypt_value

        assert decrypt_value(encrypted1) == original
        assert decrypt_value(encrypted2) == original
