import re

with open("tests/test_api_saved_searches.py", "r") as f:
    content = f.read()

# We need to mock get_current_user in app.api.saved_searches (which is imported from app.auth)
# because saved searches uses `_get_user_id` which calls `get_current_user(request)`.
# But `_get_user_id` is NOT a dependency injected via `Depends`!
# Let's verify `app/api/saved_searches.py` uses `Depends` or just calls it.

# In `app/api/saved_searches.py`:
# def _get_user_id(request: Request) -> str:
#     user = get_current_user(request)
#     if user:
#         return user.get("preferred_username") ...
# It's called directly inside the routes: `user_id = _get_user_id(request)`
# It doesn't use `Depends(_get_user_id)`.
# Ah! But earlier I saw `_get_user_id` wasn't mocked properly. Let's use patch to mock `_get_user_id`.

# Wait, `TestClient` can be given an active session, but `app.auth.get_current_user` uses `request.session.get("user")` or Bearer token.
# Is `AUTH_ENABLED` false? The test env has `os.environ["AUTH_ENABLED"] = "False"` in `tests/conftest.py`.
# If `AUTH_ENABLED` is false, `require_login` is a no-op, and `_get_user_id` falls back to "anonymous".
# Actually, `_get_user_id` returns "anonymous" if `get_current_user(request)` is None.
# If `_OWNER` is "test_user@example.com", we should probably just patch `_get_user_id`.

replacement = """def _make_client(int_engine, owner_id: str = _OWNER):
    \"\"\"Return a TestClient with *owner_id* injected as the authenticated user.\"\"\"
    from app.main import app
    from unittest.mock import patch

    def override_db():
        Session = sessionmaker(bind=int_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with patch("app.api.saved_searches._get_user_id", return_value=owner_id):
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()"""

content = re.sub(
    r"def _make_client\(int_engine, owner_id: str = _OWNER\):.*?(?=@pytest\.fixture\(\)\ndef int_client\(int_engine\):)",
    replacement + "\n\n\n",
    content,
    flags=re.DOTALL
)

with open("tests/test_api_saved_searches.py", "w") as f:
    f.write(content)
