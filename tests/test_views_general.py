"""Tests for app/views/general.py module."""

import pytest


@pytest.mark.integration
class TestGeneralViews:
    """Tests for general view routes."""

    def test_index_page(self, client):
        """Test the index/home page returns 200 or redirects to setup."""
        response = client.get("/", follow_redirects=False)
        # Should either render or redirect to setup
        assert response.status_code in (200, 303, 307)

    def test_about_page(self, client):
        """Test the about page."""
        response = client.get("/about")
        assert response.status_code == 200

    def test_privacy_page(self, client):
        """Test the privacy page."""
        response = client.get("/privacy")
        assert response.status_code == 200

    def test_privacy_page_contains_gdpr_rights(self, client):
        """Test the privacy page includes GDPR rights section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"gdpr-rights" in response.content or b"GDPR" in response.content or b"gdpr" in response.content.lower()

    def test_privacy_page_contains_ccpa_section(self, client):
        """Test the privacy page includes US/CCPA section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"CCPA" in response.content or b"California" in response.content

    def test_privacy_page_contains_canada_section(self, client):
        """Test the privacy page includes Canada/PIPEDA section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"PIPEDA" in response.content or b"Canada" in response.content

    def test_privacy_page_contains_latam_section(self, client):
        """Test the privacy page includes Latin America/LGPD section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"LGPD" in response.content or b"Latin America" in response.content

    def test_privacy_page_contains_apj_section(self, client):
        """Test the privacy page includes Asia-Pacific & Japan section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"Japan" in response.content or b"Asia-Pacific" in response.content

    def test_privacy_page_contains_international_transfers_section(self, client):
        """Test the privacy page includes international data transfers section."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"International Data Transfer" in response.content or b"international-transfers" in response.content

    def test_imprint_page(self, client):
        """Test the imprint page."""
        response = client.get("/imprint")
        assert response.status_code == 200

    def test_upload_page(self, client):
        """Test the upload page."""
        response = client.get("/upload")
        assert response.status_code == 200

    def test_cookies_page(self, client):
        """Test the cookies page."""
        response = client.get("/cookies")
        assert response.status_code == 200

    def test_cookies_page_essential_only(self, client):
        """Test the cookies page states only essential cookies are used."""
        response = client.get("/cookies")
        assert response.status_code == 200
        content = response.content
        assert b"strictly necessary" in content.lower() or b"essential" in content.lower()

    def test_cookies_page_no_tracking_claim(self, client):
        """Test the cookies page claims no third-party/tracking cookies are used."""
        response = client.get("/cookies")
        assert response.status_code == 200
        assert b"No Third-Party" in response.content or b"no third-party" in response.content.lower()

    def test_base_template_cookie_notice(self, client):
        """Test that the cookie notice banner is present in the base template."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"cookieNotice" in response.content

    def test_base_template_cookie_notice_links_to_policies(self, client):
        """Test that the cookie notice banner links to cookie and privacy pages."""
        response = client.get("/about")
        assert response.status_code == 200
        assert b"/cookies" in response.content
        assert b"/privacy" in response.content

    def test_terms_page(self, client):
        """Test the terms page."""
        response = client.get("/terms")
        assert response.status_code == 200

    def test_license_page(self, client):
        """Test the license page."""
        response = client.get("/license")
        assert response.status_code == 200

    def test_favicon(self, client):
        """Test the favicon endpoint."""
        response = client.get("/favicon.ico")
        # May be 200 or 404 depending on whether the file exists
        assert response.status_code in (200, 404)

    def test_index_with_setup_complete(self, client):
        """Test index page with setup=complete query param."""
        response = client.get("/?setup=complete", follow_redirects=False)
        assert response.status_code == 200
