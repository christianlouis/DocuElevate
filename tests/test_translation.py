"""Tests for document translation feature.

Covers:
- translate_to_default_language Celery task
- /api/files/{id}/translate on-the-fly translation endpoint
- /api/files/{id}/translation/default stored translation endpoint
- /files/{id}/text/default-language view endpoint
- _resolve_default_language helper
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord, UserProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def file_with_ocr(db_session):
    """Create a FileRecord with OCR text and detected language."""
    record = FileRecord(
        filehash="abc123translationtest",
        local_filename="/tmp/test_translate.pdf",
        file_size=1024,
        mime_type="application/pdf",
        original_filename="test_translate.pdf",
        ocr_text="Dies ist ein Testdokument in deutscher Sprache.",
        detected_language="de",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def file_with_translation(db_session):
    """Create a FileRecord with a persisted default-language translation."""
    record = FileRecord(
        filehash="def456translationtest",
        local_filename="/tmp/test_translated.pdf",
        file_size=2048,
        mime_type="application/pdf",
        original_filename="test_translated.pdf",
        ocr_text="Ceci est un document de test en français.",
        detected_language="fr",
        default_language_text="This is a test document in French.",
        default_language_code="en",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def file_without_ocr(db_session):
    """Create a FileRecord without OCR text."""
    record = FileRecord(
        filehash="ghi789translationtest",
        local_filename="/tmp/test_no_ocr.pdf",
        file_size=512,
        mime_type="application/pdf",
        original_filename="test_no_ocr.pdf",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def user_profile_with_language(db_session):
    """Create a UserProfile with a custom default_document_language."""
    profile = UserProfile(
        user_id="test-user-lang",
        default_document_language="de",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFileRecordTranslationFields:
    """Verify that the new translation columns exist on FileRecord."""

    @pytest.mark.unit
    def test_detected_language_column(self, file_with_ocr):
        assert file_with_ocr.detected_language == "de"

    @pytest.mark.unit
    def test_default_language_text_column(self, file_with_translation):
        assert file_with_translation.default_language_text == "This is a test document in French."

    @pytest.mark.unit
    def test_default_language_code_column(self, file_with_translation):
        assert file_with_translation.default_language_code == "en"

    @pytest.mark.unit
    def test_translation_columns_nullable(self, file_with_ocr):
        """Translation columns should be NULL when no translation exists."""
        assert file_with_ocr.default_language_text is None
        assert file_with_ocr.default_language_code is None


class TestUserProfileDefaultLanguage:
    """Verify UserProfile.default_document_language column."""

    @pytest.mark.unit
    def test_default_document_language_set(self, user_profile_with_language):
        assert user_profile_with_language.default_document_language == "de"

    @pytest.mark.unit
    def test_default_document_language_nullable(self, db_session):
        profile = UserProfile(user_id="test-user-no-lang")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
        assert profile.default_document_language is None


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------


class TestTranslateToDefaultLanguageTask:
    """Tests for the translate_to_default_language Celery task."""

    @pytest.mark.unit
    @patch("app.tasks.translate_to_default_language.get_ai_provider")
    def test_translate_stores_result(self, mock_provider_fn, db_session, file_with_ocr):
        """Successful translation is persisted to the FileRecord."""
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "This is a test document in German."
        mock_provider_fn.return_value = mock_provider

        from app.tasks.translate_to_default_language import translate_to_default_language

        # Patch SessionLocal to use our test session
        with patch("app.tasks.translate_to_default_language.SessionLocal") as mock_session_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=db_session)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_ctx

            task = translate_to_default_language
            # Call the underlying function (not .delay) for synchronous testing
            result = task.apply(
                args=[file_with_ocr.id, file_with_ocr.ocr_text, "de"],
                kwargs={"owner_id": None},
            ).get()

        assert result["status"] == "success"
        assert result["target_language"] == "en"

        # Verify it was stored
        db_session.refresh(file_with_ocr)
        assert file_with_ocr.default_language_text == "This is a test document in German."
        assert file_with_ocr.default_language_code == "en"
        assert file_with_ocr.detected_language == "de"

    @pytest.mark.unit
    @patch("app.tasks.translate_to_default_language.get_ai_provider")
    def test_skip_when_already_in_target_language(self, mock_provider_fn, db_session, file_with_ocr):
        """No translation when document language matches default target."""
        file_with_ocr.detected_language = "en"
        db_session.commit()

        from app.tasks.translate_to_default_language import translate_to_default_language

        with patch("app.tasks.translate_to_default_language.SessionLocal") as mock_session_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=db_session)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_ctx

            result = translate_to_default_language.apply(
                args=[file_with_ocr.id, file_with_ocr.ocr_text, "en"],
            ).get()

        assert result["status"] == "skipped"
        mock_provider_fn.assert_not_called()

    @pytest.mark.unit
    def test_resolve_default_language_global(self):
        """Falls back to the global setting when no user profile override."""
        from app.tasks.translate_to_default_language import _resolve_default_language

        with patch("app.tasks.translate_to_default_language.settings") as mock_settings:
            mock_settings.default_document_language = "en"
            assert _resolve_default_language(None) == "en"

    @pytest.mark.unit
    def test_resolve_default_language_user_override(self, db_session, user_profile_with_language):
        """Per-user override is used when available."""
        from app.tasks.translate_to_default_language import _resolve_default_language

        with patch("app.tasks.translate_to_default_language.SessionLocal") as mock_session_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=db_session)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_ctx

            result = _resolve_default_language("test-user-lang")

        assert result == "de"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDefaultTranslationEndpoint:
    """Tests for GET /api/files/{id}/translation/default."""

    @pytest.mark.integration
    def test_returns_default_translation(self, client: TestClient, file_with_translation):
        response = client.get(f"/api/files/{file_with_translation.id}/translation/default")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "This is a test document in French."
        assert data["default_language_code"] == "en"
        assert data["detected_language"] == "fr"
        assert data["file_id"] == file_with_translation.id

    @pytest.mark.integration
    def test_404_when_no_translation(self, client: TestClient, file_with_ocr):
        response = client.get(f"/api/files/{file_with_ocr.id}/translation/default")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_404_for_nonexistent_file(self, client: TestClient):
        response = client.get("/api/files/999999/translation/default")
        assert response.status_code == 404


class TestOnTheFlyTranslateEndpoint:
    """Tests for GET /api/files/{id}/translate?lang=xx."""

    @pytest.mark.integration
    @patch("app.api.translation.get_ai_provider")
    def test_translate_on_the_fly(self, mock_provider_fn, client: TestClient, file_with_ocr):
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "This is a test document in German language."
        mock_provider_fn.return_value = mock_provider

        response = client.get(f"/api/files/{file_with_ocr.id}/translate?lang=en")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "This is a test document in German language."
        assert data["target_language"] == "en"
        assert data["cached"] is False

    @pytest.mark.integration
    def test_returns_cached_default_language(self, client: TestClient, file_with_translation):
        """If the requested language matches the stored default, return cached text."""
        response = client.get(f"/api/files/{file_with_translation.id}/translate?lang=en")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "This is a test document in French."
        assert data["cached"] is True

    @pytest.mark.integration
    def test_returns_original_when_same_language(self, client: TestClient, file_with_ocr):
        """Return the original text when target matches detected language."""
        response = client.get(f"/api/files/{file_with_ocr.id}/translate?lang=de")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == file_with_ocr.ocr_text
        assert data["cached"] is True

    @pytest.mark.integration
    def test_400_when_no_ocr_text(self, client: TestClient, file_without_ocr):
        response = client.get(f"/api/files/{file_without_ocr.id}/translate?lang=en")
        assert response.status_code == 400

    @pytest.mark.integration
    def test_missing_lang_param(self, client: TestClient, file_with_ocr):
        response = client.get(f"/api/files/{file_with_ocr.id}/translate")
        assert response.status_code == 422  # validation error

    @pytest.mark.integration
    def test_404_for_nonexistent_file(self, client: TestClient):
        response = client.get("/api/files/999999/translate?lang=en")
        assert response.status_code == 404

    @pytest.mark.integration
    @patch("app.api.translation.get_ai_provider")
    def test_502_on_provider_error(self, mock_provider_fn, client: TestClient, file_with_ocr):
        mock_provider = MagicMock()
        mock_provider.chat_completion.side_effect = RuntimeError("AI error")
        mock_provider_fn.return_value = mock_provider

        response = client.get(f"/api/files/{file_with_ocr.id}/translate?lang=fr")
        assert response.status_code == 502


# ---------------------------------------------------------------------------
# View endpoint tests
# ---------------------------------------------------------------------------


class TestDefaultLanguageTextView:
    """Tests for GET /files/{id}/text/default-language."""

    @pytest.mark.integration
    def test_returns_default_language_text(self, client: TestClient, file_with_translation):
        response = client.get(f"/files/{file_with_translation.id}/text/default-language")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "This is a test document in French."
        assert data["language_code"] == "en"
        assert data["detected_language"] == "fr"

    @pytest.mark.integration
    def test_404_when_no_default_text(self, client: TestClient, file_with_ocr):
        response = client.get(f"/files/{file_with_ocr.id}/text/default-language")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_404_for_nonexistent_file(self, client: TestClient):
        response = client.get("/files/999999/text/default-language")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestDefaultDocumentLanguageConfig:
    """Verify the DEFAULT_DOCUMENT_LANGUAGE setting."""

    @pytest.mark.unit
    def test_default_value_is_english(self):
        from app.config import settings

        assert settings.default_document_language == "en"


# ---------------------------------------------------------------------------
# Profile API integration tests
# ---------------------------------------------------------------------------


class TestProfileDefaultDocumentLanguage:
    """Tests for default_document_language in the profile API."""

    @pytest.fixture
    def prof_engine(self):
        """In-memory SQLite engine for profile tests."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from app.database import Base

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        yield engine

    @pytest.fixture
    def prof_session(self, prof_engine):
        """DB session for profile tests."""
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=self.prof_engine if hasattr(self, "prof_engine") else prof_engine)
        session = Session()
        yield session
        session.close()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_profile_includes_default_document_language(self, prof_engine):
        """GET handler returns default_document_language in response."""
        from unittest.mock import MagicMock

        from sqlalchemy.orm import sessionmaker

        from app.api.profile import get_profile

        Session = sessionmaker(bind=prof_engine)
        session = Session()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "languser", "email": "lang@test.com"}}

        result = await get_profile(req, session)
        assert hasattr(result, "default_document_language")
        session.close()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_default_document_language(self, prof_engine):
        """PATCH handler updates default_document_language."""
        from unittest.mock import MagicMock

        from sqlalchemy.orm import sessionmaker

        from app.api.profile import ProfileUpdateRequest, update_profile

        Session = sessionmaker(bind=prof_engine)
        session = Session()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "languser2", "email": "lang2@test.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(default_document_language="de")
        result = await update_profile(body, req, resp, session)
        assert result.default_document_language == "de"
        session.close()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_clear_default_document_language(self, prof_engine):
        """Setting default_document_language to empty string clears it."""
        from unittest.mock import MagicMock

        from sqlalchemy.orm import sessionmaker

        from app.api.profile import ProfileUpdateRequest, update_profile

        Session = sessionmaker(bind=prof_engine)
        session = Session()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "languser3", "email": "lang3@test.com"}}
        resp = MagicMock()

        # Set
        body = ProfileUpdateRequest(default_document_language="fr")
        await update_profile(body, req, resp, session)
        # Clear
        body = ProfileUpdateRequest(default_document_language="")
        result = await update_profile(body, req, resp, session)
        assert result.default_document_language is None
        session.close()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reject_invalid_default_document_language(self, prof_engine):
        """Invalid language codes are rejected with 422."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException
        from sqlalchemy.orm import sessionmaker

        from app.api.profile import ProfileUpdateRequest, update_profile

        Session = sessionmaker(bind=prof_engine)
        session = Session()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "languser4", "email": "lang4@test.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(default_document_language="xx_invalid")
        with pytest.raises(HTTPException) as exc_info:
            await update_profile(body, req, resp, session)
        assert exc_info.value.status_code == 422
        session.close()
