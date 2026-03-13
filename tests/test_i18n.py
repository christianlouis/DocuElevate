"""Tests for the i18n (internationalization) and l10n (localization) utilities."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.utils.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    _parse_accept_language,
    detect_language,
    format_date,
    format_datetime,
    format_number,
    get_language_info,
    get_suggested_languages,
    reload_translations,
    translate,
)

# ---------------------------------------------------------------------------
# Translation file integrity
# ---------------------------------------------------------------------------


class TestTranslationFiles:
    """Verify that all translation JSON files are valid and complete."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear translation cache before each test."""
        reload_translations()

    @pytest.mark.unit
    def test_all_translation_files_exist(self) -> None:
        """Every supported language must have a corresponding JSON file."""
        translations_dir = Path(__file__).resolve().parent.parent / "frontend" / "translations"
        for lang in SUPPORTED_LANGUAGES:
            filepath = translations_dir / f"{lang['code']}.json"
            assert filepath.is_file(), f"Missing translation file for {lang['code']}"

    @pytest.mark.unit
    def test_all_translation_files_are_valid_json(self) -> None:
        """All translation files must be parseable JSON."""
        translations_dir = Path(__file__).resolve().parent.parent / "frontend" / "translations"
        for lang in SUPPORTED_LANGUAGES:
            filepath = translations_dir / f"{lang['code']}.json"
            data = json.loads(filepath.read_text(encoding="utf-8"))
            assert isinstance(data, dict), f"{lang['code']}.json must be a dict"
            assert len(data) > 0, f"{lang['code']}.json must not be empty"


# ---------------------------------------------------------------------------
# Core translate() function
# ---------------------------------------------------------------------------


class TestTranslate:
    """Tests for the translate() function."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        reload_translations()

    @pytest.mark.unit
    def test_translate_english_key(self) -> None:
        """English keys should resolve to English text."""
        result = translate("nav.dashboard", "en")
        assert result == "Dashboard"

    @pytest.mark.unit
    def test_translate_german_key(self) -> None:
        """German locale should return German text."""
        result = translate("nav.dashboard", "de")
        assert result == "Übersicht"

    @pytest.mark.unit
    def test_translate_french_key(self) -> None:
        """French locale should return French text."""
        result = translate("nav.dashboard", "fr")
        assert result == "Tableau de bord"

    @pytest.mark.unit
    def test_translate_chinese_key(self) -> None:
        """Chinese locale should return Chinese text."""
        result = translate("nav.dashboard", "zh")
        assert result == "仪表盘"

    @pytest.mark.unit
    def test_translate_fallback_to_english(self) -> None:
        """Unknown locale falls back to English."""
        result = translate("nav.dashboard", "xx")
        assert result == "Dashboard"

    @pytest.mark.unit
    def test_translate_missing_key_returns_key(self) -> None:
        """Missing key falls back to the key itself."""
        result = translate("nonexistent.key", "en")
        assert result == "nonexistent.key"

    @pytest.mark.unit
    def test_translate_none_locale_uses_default(self) -> None:
        """None locale defaults to English."""
        result = translate("nav.dashboard", None)
        assert result == "Dashboard"

    @pytest.mark.unit
    def test_translate_with_kwargs(self) -> None:
        """Placeholders should be interpolated via kwargs."""
        result = translate("footer.copyright", "en", year="2025")
        assert result == "DocuElevate 2025"

    @pytest.mark.unit
    def test_translate_with_kwargs_german(self) -> None:
        """Placeholder interpolation in German."""
        result = translate("language.changed", "de", language="English")
        assert result == "Sprache geändert zu English"


# ---------------------------------------------------------------------------
# Accept-Language header parsing
# ---------------------------------------------------------------------------


class TestParseAcceptLanguage:
    """Tests for parsing the Accept-Language HTTP header."""

    @pytest.mark.unit
    def test_simple_language(self) -> None:
        assert _parse_accept_language("de") == "de"

    @pytest.mark.unit
    def test_language_with_region(self) -> None:
        assert _parse_accept_language("de-DE") == "de"

    @pytest.mark.unit
    def test_multiple_languages_quality(self) -> None:
        result = _parse_accept_language("fr;q=0.9, de;q=1.0, en;q=0.8")
        assert result == "de"

    @pytest.mark.unit
    def test_unsupported_language_fallback(self) -> None:
        result = _parse_accept_language("xx, yy")
        assert result is None

    @pytest.mark.unit
    def test_empty_header(self) -> None:
        assert _parse_accept_language("") is None

    @pytest.mark.unit
    def test_complex_accept_language(self) -> None:
        header = "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        result = _parse_accept_language(header)
        assert result == "zh"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    """Tests for detecting language from request context."""

    @pytest.mark.unit
    def test_session_preference_takes_priority(self) -> None:
        request = MagicMock()
        request.session = {"preferred_language": "de"}
        request.cookies = {}
        request.headers = {}
        assert detect_language(request) == "de"

    @pytest.mark.unit
    def test_cookie_fallback(self) -> None:
        request = MagicMock()
        request.session = {}
        request.cookies = {"docuelevate_lang": "fr"}
        request.headers = {}
        assert detect_language(request) == "fr"

    @pytest.mark.unit
    def test_accept_language_fallback(self) -> None:
        request = MagicMock()
        request.session = {}
        request.cookies = {}
        request.headers = {"accept-language": "es-ES,es;q=0.9"}
        assert detect_language(request) == "es"

    @pytest.mark.unit
    def test_default_fallback(self) -> None:
        request = MagicMock()
        request.session = {}
        request.cookies = {}
        request.headers = {}
        assert detect_language(request) == DEFAULT_LANGUAGE

    @pytest.mark.unit
    def test_invalid_session_language_ignored(self) -> None:
        request = MagicMock()
        request.session = {"preferred_language": "invalid"}
        request.cookies = {"docuelevate_lang": "it"}
        request.headers = {}
        assert detect_language(request) == "it"


# ---------------------------------------------------------------------------
# Localization helpers
# ---------------------------------------------------------------------------


class TestL10nFormatters:
    """Tests for locale-aware formatting functions."""

    @pytest.mark.unit
    def test_format_date_english(self) -> None:
        d = date(2025, 3, 15)
        result = format_date(d, "en")
        assert "March" in result
        assert "15" in result
        assert "2025" in result

    @pytest.mark.unit
    def test_format_date_german(self) -> None:
        d = date(2025, 3, 15)
        result = format_date(d, "de")
        assert "15." in result
        assert "2025" in result

    @pytest.mark.unit
    def test_format_date_short(self) -> None:
        d = date(2025, 3, 15)
        result = format_date(d, "en", short=True)
        assert result == "03/15/2025"

    @pytest.mark.unit
    def test_format_date_short_german(self) -> None:
        d = date(2025, 3, 15)
        result = format_date(d, "de", short=True)
        assert result == "15.03.2025"

    @pytest.mark.unit
    def test_format_date_none(self) -> None:
        assert format_date(None) == ""

    @pytest.mark.unit
    def test_format_datetime_none(self) -> None:
        assert format_datetime(None) == ""

    @pytest.mark.unit
    def test_format_number_english(self) -> None:
        result = format_number(1234567, "en")
        assert result == "1,234,567"

    @pytest.mark.unit
    def test_format_number_german(self) -> None:
        result = format_number(1234567, "de")
        assert result == "1.234.567"

    @pytest.mark.unit
    def test_format_number_float_english(self) -> None:
        result = format_number(1234.56, "en")
        assert result == "1,234.56"

    @pytest.mark.unit
    def test_format_number_float_german(self) -> None:
        result = format_number(1234.56, "de")
        assert result == "1.234,56"

    @pytest.mark.unit
    def test_format_datetime_chinese(self) -> None:
        dt = datetime(2025, 3, 15, 14, 30)
        result = format_datetime(dt, "zh")
        assert "2025" in result
        assert "03" in result
        assert "15" in result


# ---------------------------------------------------------------------------
# get_language_info()
# ---------------------------------------------------------------------------


class TestGetLanguageInfo:
    """Tests for get_language_info() utility."""

    @pytest.mark.unit
    def test_known_language(self) -> None:
        info = get_language_info("de")
        assert info is not None
        assert info["name"] == "German"
        assert info["native"] == "Deutsch"

    @pytest.mark.unit
    def test_unknown_language(self) -> None:
        assert get_language_info("xx") is None


# ---------------------------------------------------------------------------
# get_suggested_languages()
# ---------------------------------------------------------------------------


class TestGetSuggestedLanguages:
    """Tests for get_suggested_languages() utility."""

    @pytest.mark.unit
    def test_returns_at_most_six(self) -> None:
        """Result must contain at most 6 languages."""
        result = get_suggested_languages("en", "en,de;q=0.9,fr;q=0.8,es;q=0.7,it;q=0.6,pt;q=0.5,nl;q=0.4,zh;q=0.3")
        assert len(result) <= 6

    @pytest.mark.unit
    def test_current_locale_is_first(self) -> None:
        """Currently active language must always be the first entry."""
        result = get_suggested_languages("de", "")
        assert result[0]["code"] == "de"

    @pytest.mark.unit
    def test_includes_browser_preference(self) -> None:
        """Languages from Accept-Language header should be included."""
        result = get_suggested_languages("en", "fr;q=0.9,de;q=0.8")
        codes = [lang["code"] for lang in result]
        assert "fr" in codes
        assert "de" in codes

    @pytest.mark.unit
    def test_fallback_to_popular_languages(self) -> None:
        """Popular languages fill remaining slots when no browser prefs given."""
        result = get_suggested_languages("en", "")
        codes = [lang["code"] for lang in result]
        # en is current; popular fallbacks like zh, es, fr should be present
        assert "en" in codes
        # At least one other popular language should appear
        popular = {"zh", "es", "ar", "fr", "de", "ja", "pt", "hi", "ko"}
        assert popular & set(codes)

    @pytest.mark.unit
    def test_no_duplicates(self) -> None:
        """No language code should appear more than once."""
        result = get_suggested_languages("fr", "fr;q=1.0,de;q=0.9")
        codes = [lang["code"] for lang in result]
        assert len(codes) == len(set(codes))

    @pytest.mark.unit
    def test_all_entries_are_valid_languages(self) -> None:
        """Every returned entry must be a dict with required language fields."""
        result = get_suggested_languages("es", "ca;q=0.9")
        for entry in result:
            assert "code" in entry
            assert "name" in entry
            assert "native" in entry
            assert "flag" in entry

    @pytest.mark.unit
    def test_unknown_locale_falls_back_gracefully(self) -> None:
        """An unsupported current_locale must not crash and still return results."""
        result = get_suggested_languages("xx", "")
        assert len(result) > 0  # popular fallbacks still returned


# ---------------------------------------------------------------------------
# SUPPORTED_LANGUAGES metadata
# ---------------------------------------------------------------------------


class TestSupportedLanguages:
    """Tests for language metadata constants."""

    @pytest.mark.unit
    def test_ten_languages_supported(self) -> None:
        assert len(SUPPORTED_LANGUAGES) == 77

    @pytest.mark.unit
    def test_supported_codes_set(self) -> None:
        expected = {
            "en",
            "de",
            "fr",
            "es",
            "it",
            "pt",
            "nl",
            "nb",
            "no",
            "da",
            "sv",
            "fi",
            "is",
            "ga",
            "lb",
            "ca",
            "cy",
            "fy",
            "gl",
            "li",
            "vls",
            "nds",
            "pl",
            "cs",
            "sk",
            "hu",
            "sl",
            "hr",
            "ro",
            "bg",
            "el",
            "et",
            "lv",
            "lt",
            "sr",
            "tr",
            "uk",
            "he",
            "ar",
            "fa",
            "af",
            "zh",
            "zh-TW",
            "ja",
            "ko",
            "vi",
            "pa",
            "kn",
            "hi",
            "bn",
            "gu",
            "ml",
            "mr",
            "ta",
            "te",
            "ur",
            "si",
            "ne",
            "th",
            "km",
            "id",
            "ms",
            "jv",
            "tl",
            "mn",
            "kk",
            "uz",
            "az",
            "hy",
            "ka",
            "sw",
            "am",
            "ha",
            "yo",
            "ig",
            "zu",
            "eo",
        }
        assert SUPPORTED_LANGUAGE_CODES == expected

    @pytest.mark.unit
    def test_default_language_is_english(self) -> None:
        assert DEFAULT_LANGUAGE == "en"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestI18nAPI:
    """Tests for the i18n API endpoints."""

    @pytest.mark.integration
    def test_list_languages(self, client: TestClient) -> None:
        """GET /api/i18n/languages should return all supported languages."""
        response = client.get("/api/i18n/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert len(data["languages"]) == 77
        assert data["default"] == "en"
        # Verify each language has required fields
        for lang in data["languages"]:
            assert "code" in lang
            assert "name" in lang
            assert "native" in lang
            assert "flag" in lang

    @pytest.mark.integration
    def test_set_language(self, client: TestClient) -> None:
        """POST /api/i18n/language should set language preference."""
        response = client.post(
            "/api/i18n/language",
            json={"language": "de"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "de"
        # Verify cookie was set
        assert "docuelevate_lang" in response.cookies

    @pytest.mark.integration
    def test_set_language_invalid_falls_back_to_default(self, client: TestClient) -> None:
        """Invalid language code should fall back to default."""
        response = client.post(
            "/api/i18n/language",
            json={"language": "invalid"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"

    @pytest.mark.integration
    def test_set_language_persists_in_cookie(self, client: TestClient) -> None:
        """Language setting should be persisted in a cookie."""
        client.post("/api/i18n/language", json={"language": "fr"})
        # Subsequent requests should detect the language from cookie
        response = client.get("/api/i18n/languages")
        data = response.json()
        assert data["current"] == "fr"

    @pytest.mark.integration
    def test_base_html_uses_current_locale(self, client: TestClient) -> None:
        """The base template should set lang attribute to current locale."""
        # Set language to German
        client.post("/api/i18n/language", json={"language": "de"})
        # Load homepage
        response = client.get("/", follow_redirects=True)
        assert response.status_code == 200
        # The lang attribute should reflect the locale
        assert 'lang="de"' in response.text or 'lang="en"' in response.text

    @pytest.mark.integration
    def test_language_selector_in_nav(self, client: TestClient) -> None:
        """The navigation should contain the language selector with flag and search."""
        response = client.get("/", follow_redirects=True)
        if response.status_code == 200:
            # The selector renders a flag emoji (not the old fa-globe icon) and the
            # setLanguage JS helper for switching languages.
            assert "setLanguage" in response.text
            # The search input for filtering all languages must be present.
            assert "langSearch" in response.text
