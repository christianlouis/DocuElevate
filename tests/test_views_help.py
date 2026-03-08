"""Tests for app/views/help.py module – user-facing Help Center."""

import pytest


@pytest.mark.integration
class TestHelpViews:
    """Tests for the Help Center view routes."""

    def test_help_returns_200(self, client):
        """GET /help should return the Help Center page."""
        response = client.get("/help")
        assert response.status_code == 200

    def test_help_contains_help_center_title(self, client):
        """The page should contain the Help Center heading."""
        response = client.get("/help")
        assert b"Help Center" in response.content

    def test_help_contains_quick_start_section(self, client):
        """The page should contain the Quick Start section."""
        response = client.get("/help")
        assert b"Quick Start" in response.content

    def test_help_contains_sources_section(self, client):
        """The page should contain the Sources section."""
        response = client.get("/help")
        assert b"Sources" in response.content

    def test_help_contains_destinations_section(self, client):
        """The page should contain the Destinations section."""
        response = client.get("/help")
        assert b"Destinations" in response.content

    def test_help_contains_faq_section(self, client):
        """The page should contain the FAQ section."""
        response = client.get("/help")
        assert b"Frequently Asked Questions" in response.content

    def test_help_contains_support_section(self, client):
        """The page should contain the Contact Support section."""
        response = client.get("/help")
        assert b"Contact Support" in response.content

    def test_help_route_is_registered(self, client):
        """Verify the /help route exists in the app router."""
        response = client.get("/help")
        assert response.status_code != 405


@pytest.mark.unit
class TestHelpViewUnit:
    """Unit tests for the help view module."""

    def test_help_returns_200(self):
        """Verify the help center returns HTTP 200."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from app.views.help import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help")
        assert resp.status_code == 200

    def test_help_page_has_seo_meta(self):
        """Verify SEO meta tags are present in the response."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from app.views.help import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help")
        assert b'name="description"' in resp.content
        assert b'name="robots"' in resp.content

    def test_help_page_has_structured_data(self):
        """Verify JSON-LD structured data is present."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from app.views.help import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help")
        assert b"application/ld+json" in resp.content
        assert b"FAQPage" in resp.content

    def test_docs_build_path_constant(self):
        """Verify _DOCS_BUILD_DIR is resolved relative to the app package."""
        import pathlib

        from app.views.help import _DOCS_BUILD_DIR

        assert isinstance(_DOCS_BUILD_DIR, pathlib.Path)
        # Should point to <repo_root>/docs_build
        assert _DOCS_BUILD_DIR.name == "docs_build"

    def test_zammad_chat_hidden_when_disabled(self):
        """Chat widget markup should not appear when Zammad chat is disabled."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from app.views.help import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help")
        # Default settings: zammad_chat_enabled=False → no chat script
        assert b"ZammadChat" not in resp.content

    def test_zammad_form_hidden_when_disabled(self):
        """Ticket form markup should not appear when Zammad form is disabled."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from app.views.help import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        with TestClient(app) as tc:
            resp = tc.get("/help")
        # Default settings: zammad_form_enabled=False → no form script
        assert b"ZammadForm" not in resp.content


@pytest.mark.integration
class TestHelpNavigationLink:
    """Tests that the Help link appears in the navigation."""

    def test_help_link_in_nav(self, client):
        """The Help navigation link should appear in the base template."""
        response = client.get("/about")
        assert response.status_code == 200
        # The Help link should be present somewhere in the rendered page
        assert b"/help" in response.content

    def test_help_link_has_accessible_text(self, client):
        """The Help link should have visible text for accessibility."""
        response = client.get("/about")
        assert response.status_code == 200
        content = response.text
        # Should include the word "Help" associated with /help
        assert "Help" in content


@pytest.mark.integration
class TestAdminDocsLinks:
    """Tests that admin doc links are in the admin menu markup."""

    def test_api_docs_link_in_admin_menu(self, client):
        """The admin menu HTML should contain the API Docs link."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"/admin/api-docs" in response.content

    def test_developer_docs_link_in_admin_menu(self, client):
        """The admin menu HTML should contain the Developer Docs link."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"/developer-docs/" in response.content
