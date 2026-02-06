"""
Tests for path traversal security in file operations.
"""
import pytest
import os
import tempfile
from app.api.common import resolve_file_path
from app.config import settings


class TestPathTraversalSecurity:
    """Tests to ensure path traversal attacks are blocked."""
    
    def setup_method(self):
        """Set up test environment with a temporary workdir."""
        self.temp_dir = tempfile.mkdtemp()
        # Store original workdir
        self.original_workdir = settings.workdir
        # Set test workdir
        settings.workdir = self.temp_dir
        
        # Create a subdirectory for testing subfolder parameter
        self.processed_dir = os.path.join(self.temp_dir, "processed")
        os.makedirs(self.processed_dir, exist_ok=True)
        
    def teardown_method(self):
        """Clean up test environment."""
        # Restore original workdir
        settings.workdir = self.original_workdir
        # Clean up temp directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_resolve_simple_filename(self):
        """Test resolving a simple filename within workdir."""
        result = resolve_file_path("test.pdf")
        expected = os.path.realpath(os.path.join(self.temp_dir, "test.pdf"))
        assert result == expected
    
    def test_resolve_filename_with_subfolder(self):
        """Test resolving a filename with subfolder parameter."""
        result = resolve_file_path("document.pdf", subfolder="processed")
        expected = os.path.realpath(os.path.join(self.temp_dir, "processed", "document.pdf"))
        assert result == expected
    
    def test_block_parent_directory_traversal(self):
        """Test that parent directory traversal is blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("../etc/passwd")
    
    def test_block_multiple_parent_traversal(self):
        """Test that multiple parent directory traversals are blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("../../etc/passwd")
    
    def test_block_absolute_path_outside_workdir(self):
        """Test that absolute paths outside workdir are blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("/etc/passwd")
    
    def test_block_mixed_traversal(self):
        """Test that mixed path traversal attempts are blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("subdir/../../etc/passwd")
    
    def test_block_dot_dot_in_middle(self):
        """Test that traversal in the middle of path is blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("foo/../../../etc/passwd")
    
    def test_allow_subdirectory_path(self):
        """Test that legitimate subdirectory paths are allowed."""
        # Create subdirectory
        subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(subdir, exist_ok=True)
        
        result = resolve_file_path("subdir/test.pdf")
        expected = os.path.realpath(os.path.join(self.temp_dir, "subdir", "test.pdf"))
        assert result == expected
    
    def test_allow_nested_subdirectory_path(self):
        """Test that nested subdirectory paths are allowed."""
        # Create nested subdirectories
        nested_dir = os.path.join(self.temp_dir, "level1", "level2")
        os.makedirs(nested_dir, exist_ok=True)
        
        result = resolve_file_path("level1/level2/document.pdf")
        expected = os.path.realpath(os.path.join(self.temp_dir, "level1", "level2", "document.pdf"))
        assert result == expected
    
    def test_block_traversal_with_subfolder(self):
        """Test that path traversal is blocked even with subfolder parameter."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            resolve_file_path("../test.pdf", subfolder="processed")
    
    def test_absolute_path_within_workdir(self):
        """Test that absolute paths within workdir are allowed."""
        test_file = os.path.join(self.temp_dir, "test.pdf")
        result = resolve_file_path(test_file)
        expected = os.path.realpath(test_file)
        assert result == expected
    
    def test_block_url_encoded_traversal(self):
        """Test that URL-encoded path traversal characters are blocked."""
        # Note: Python file operations don't automatically decode URLs
        # On Unix systems, these characters are part of the filename
        # This test verifies that even with weird characters, the path is safe
        result = resolve_file_path("..%2Fetc%2Fpasswd")
        # Should be within workdir since %2F isn't decoded to /
        assert result.startswith(os.path.realpath(self.temp_dir))
    
    def test_block_backslash_traversal_windows_style(self):
        """Test that Windows-style backslash traversal attempts don't escape."""
        # On Unix, backslashes are literal filename characters
        # On Windows, they are path separators
        # Either way, the result should be safe
        result = resolve_file_path("..\\..\\etc\\passwd")
        # Should be within workdir
        assert result.startswith(os.path.realpath(self.temp_dir))
    
    def test_resolve_current_directory_reference(self):
        """Test that current directory references (.) are handled correctly."""
        result = resolve_file_path("./test.pdf")
        expected = os.path.realpath(os.path.join(self.temp_dir, "test.pdf"))
        assert result == expected
    
    def test_block_symlink_escape(self):
        """Test that symlinks pointing outside workdir are blocked."""
        # Create a symlink pointing to /tmp
        symlink_path = os.path.join(self.temp_dir, "escape_link")
        try:
            os.symlink("/tmp", symlink_path)
            
            # Try to access a file through the symlink
            with pytest.raises(ValueError, match="Path traversal detected"):
                resolve_file_path("escape_link/sensitive.txt")
        except OSError:
            # Symlink creation might fail in some environments, skip test
            pytest.skip("Unable to create symlink in test environment")
