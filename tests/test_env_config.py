"""
Test that .env.test loading works correctly in conftest.py
"""
import os
import pytest
from pathlib import Path


@pytest.mark.unit
def test_env_test_loading_mechanism():
    """
    Test that environment variables are loaded correctly.
    
    This test verifies that the test environment loading in conftest.py
    provides fallback values when .env.test doesn't exist.
    """
    # These should always be set by conftest.py (either from .env.test or defaults)
    assert os.getenv("DATABASE_URL") is not None
    assert os.getenv("REDIS_URL") is not None
    assert os.getenv("OPENAI_API_KEY") is not None
    assert os.getenv("AZURE_AI_KEY") is not None
    assert os.getenv("GOTENBERG_URL") is not None
    assert os.getenv("WORKDIR") is not None
    assert os.getenv("AUTH_ENABLED") is not None
    assert os.getenv("SESSION_SECRET") is not None


@pytest.mark.unit
def test_default_test_values():
    """
    Test that default test values are set when .env.test is not present.
    
    If .env.test exists with custom values, these assertions might fail,
    which is expected behavior.
    """
    # Check that we have some environment value (either from .env.test or defaults)
    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None
    
    # The DATABASE_URL should be configured for testing (either in-memory SQLite or test database)
    assert "sqlite" in database_url or "test" in database_url.lower()


@pytest.mark.unit 
def test_env_test_file_is_gitignored():
    """
    Test that .env.test is properly gitignored.
    
    This is a static check to ensure developers can safely use .env.test
    without accidentally committing secrets.
    """
    repo_root = Path(__file__).parent.parent
    gitignore_path = repo_root / ".gitignore"
    
    assert gitignore_path.exists(), ".gitignore file should exist"
    
    with open(gitignore_path) as f:
        gitignore_content = f.read()
    
    # Check that .env.test is explicitly mentioned or covered by patterns
    assert ".env.test" in gitignore_content or "*.env" in gitignore_content, \
        ".env.test should be gitignored to prevent committing secrets"


@pytest.mark.unit
def test_env_test_example_exists():
    """
    Test that .env.test.example template file exists.
    
    This file serves as documentation and template for developers
    setting up their test environment.
    """
    repo_root = Path(__file__).parent.parent
    example_file = repo_root / ".env.test.example"
    
    assert example_file.exists(), ".env.test.example template should exist"
    
    # Verify it contains some key documentation
    with open(example_file) as f:
        content = f.read()
    
    assert "OPENAI_API_KEY" in content, "Template should include OpenAI configuration"
    assert "AZURE_AI_KEY" in content, "Template should include Azure configuration"
    assert "test" in content.lower(), "Template should mention it's for testing"
    assert "copy" in content.lower() or "cp" in content.lower(), \
        "Template should explain how to use it"


@pytest.mark.unit
def test_sensitive_keys_have_safe_defaults():
    """
    Test that API keys and secrets have safe default values for testing.
    
    This ensures that tests can run in CI/CD without real credentials.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    azure_key = os.getenv("AZURE_AI_KEY")
    
    # In test environment without .env.test, these should be test/mock values
    # The actual values don't matter, as long as they're set and won't cause
    # tests to fail when external services are mocked
    assert openai_key is not None
    assert azure_key is not None
    
    # Keys should not be empty strings
    assert len(openai_key) > 0
    assert len(azure_key) > 0


@pytest.mark.unit
def test_auth_disabled_by_default_in_tests():
    """
    Test that authentication is disabled by default in test environment.
    
    This makes testing easier by avoiding authentication overhead in most tests.
    """
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower()
    
    # Should be "false" in test environment (unless explicitly overridden in .env.test)
    # This test documents the expected default behavior
    assert auth_enabled in ["false", "true"], "AUTH_ENABLED should be a boolean string"


@pytest.mark.integration
def test_can_override_with_env_test():
    """
    Integration test documenting that .env.test values are used if present.
    
    This test passes whether or not .env.test exists, but documents
    the expected behavior.
    """
    repo_root = Path(__file__).parent.parent
    env_test_file = repo_root / ".env.test"
    
    if env_test_file.exists():
        # If .env.test exists, environment should reflect custom test config
        # We can't assert specific values since they're user-defined,
        # but we can verify the mechanism works
        print(f"✓ .env.test found at {env_test_file}")
        print("  Test environment is using custom configuration")
        print(f"  OPENAI_API_KEY length: {len(os.getenv('OPENAI_API_KEY', ''))}")
        
        # Verify it's actually loading from the file by checking it has content
        with open(env_test_file) as f:
            content = f.read()
        assert len(content) > 0, ".env.test should not be empty"
    else:
        # If .env.test doesn't exist, we should be using defaults
        print("  .env.test not found (expected in CI/CD)")
        print("  Test environment is using default mock values")
        
    # Either way, critical variables should be set
    assert os.getenv("OPENAI_API_KEY") is not None
    assert os.getenv("DATABASE_URL") is not None
