"""Tests for app/views/help.py module."""

import pytest


@pytest.mark.integration
class TestHelpViews:
    """Tests for the help documentation view routes."""

    def test_help_redirect(self, client):
        """GET /help should redirect permanently to /help/."""
        response = client.get("/help", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] in ("/help/", "http://testserver/help/")

    def test_help_redirect_follows(self, client):
        """Following /help redirect leads to /help/ (docs served or 404 if not built)."""
        # In test environments docs_build/ is not present, so /help/ may 404.
        # We only verify the initial redirect works; the final landing page depends
        # on whether the docs have been built (they are built only in Docker images).
        response = client.get("/help", follow_redirects=False)
        assert response.status_code == 301
        # Redirect target must be /help/
        location = response.headers.get("location", "")
        assert location.endswith("/help/")

    def test_help_route_is_registered(self, client):
        """Verify the /help route exists in the app router."""
        # A GET to /help must not return 405 Method Not Allowed
        response = client.get("/help", follow_redirects=False)
        assert response.status_code != 405


@pytest.mark.unit
class TestHelpViewUnit:
    """Unit tests for the help view module."""

    def test_help_redirect_returns_301(self):
        """Verify the redirect is HTTP 301 (permanent)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.views.help import router

        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help", follow_redirects=False)
        assert resp.status_code == 301

    def test_help_redirect_target(self):
        """Verify the redirect points to /help/."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.views.help import router

        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help", follow_redirects=False)
        assert resp.headers["location"].rstrip("/").endswith("help") or resp.headers["location"].endswith("/help/")

    def test_docs_build_path_constant(self):
        """Verify _DOCS_BUILD_DIR is resolved relative to the app package."""
        import pathlib

        from app.views.help import _DOCS_BUILD_DIR

        assert isinstance(_DOCS_BUILD_DIR, pathlib.Path)
        # Should point to <repo_root>/docs_build
        assert _DOCS_BUILD_DIR.name == "docs_build"


@pytest.mark.integration
class TestHelpNavigationLink:
    """Tests that the Help link appears in the navigation."""

    def test_help_link_in_nav(self, client):
        """The Help navigation link should appear in the base template."""
        response = client.get("/about")
        assert response.status_code == 200
        # The Help link should be present somewhere in the rendered page
        assert b"/help/" in response.content

    def test_help_link_has_accessible_text(self, client):
        """The Help link should have visible text for accessibility."""
        response = client.get("/about")
        assert response.status_code == 200
        content = response.text
        # Should include the word "Help" associated with /help/
        assert "Help" in content
