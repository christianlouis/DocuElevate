import os
import tempfile

import pytest

from app.utils import hash_file


@pytest.mark.unit
class TestUtils:
    def test_hash_file_empty(self):
        """Test hashing an empty file"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            pass

        try:
            # Known SHA-256 hash of an empty file
            expected_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert hash_file(tmp_file.name) == expected_hash
        finally:
            os.unlink(tmp_file.name)

    def test_hash_file_with_content(self):
        """Test hashing a file with known content"""
        content = b"Hello, World!"
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()

        try:
            # Known SHA-256 hash of "Hello, World!"
            expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
            assert hash_file(tmp_file.name) == expected_hash
        finally:
            os.unlink(tmp_file.name)

    def test_hash_file_large_content(self):
        """Test hashing a file larger than the chunk size"""
        # Create content larger than the default chunk size (65536)
        content = b"x" * 100000
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()

        try:
            # Test that we can hash a large file
            hash_result = hash_file(tmp_file.name)
            assert len(hash_result) == 64  # SHA-256 hashes are 64 characters long
        finally:
            os.unlink(tmp_file.name)
