"""
Tests for the suggestion providers and the settings suggestions API.

Covers:
- Dynamic suggestion providers (AWS, Azure, Tesseract, EasyOCR, embedding models)
- GET /api/settings/{key}/suggestions endpoint
- Substring filtering and limit enforcement
- Fallback to static lists when SDKs are unavailable
"""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.suggestion_providers import (
    _AZURE_REGIONS_STATIC,
    _EASYOCR_LANGS_STATIC,
    _EMBEDDING_MODELS,
    _TESSERACT_LANGS_STATIC,
    SUGGESTION_PROVIDERS,
    get_aws_regions,
    get_azure_regions,
    get_easyocr_languages,
    get_embedding_models,
    get_suggestions,
    get_tesseract_languages,
)

# ---------------------------------------------------------------------------
# Provider unit tests
# ---------------------------------------------------------------------------


class TestAWSRegionProvider:
    """Tests for get_aws_regions."""

    @pytest.mark.unit
    def test_returns_list(self):
        """Should return a non-empty list of region strings."""
        regions = get_aws_regions()
        assert isinstance(regions, list)
        assert len(regions) > 0
        assert all(isinstance(r, str) for r in regions)

    @pytest.mark.unit
    def test_us_east_1_present(self):
        """us-east-1 should always be in the list."""
        regions = get_aws_regions()
        assert "us-east-1" in regions

    @pytest.mark.unit
    def test_results_are_sorted(self):
        """Region list should be sorted alphabetically."""
        regions = get_aws_regions()
        assert regions == sorted(regions)

    @pytest.mark.unit
    def test_fallback_on_boto3_failure(self):
        """Should fall back to static list when boto3 raises."""
        with patch.dict("sys.modules", {"boto3": None}):
            regions = get_aws_regions()
        # Should still return a list (the static fallback)
        assert isinstance(regions, list)
        assert "us-east-1" in regions


class TestAzureRegionProvider:
    """Tests for get_azure_regions."""

    @pytest.mark.unit
    def test_returns_static_list(self):
        """Should return the curated static list."""
        regions = get_azure_regions()
        assert regions == _AZURE_REGIONS_STATIC
        assert "eastus" in regions

    @pytest.mark.unit
    def test_contains_common_regions(self):
        """Common Azure regions should be present."""
        regions = get_azure_regions()
        for region in ["eastus", "westeurope", "uksouth", "japaneast"]:
            assert region in regions


class TestTesseractLanguageProvider:
    """Tests for get_tesseract_languages."""

    @pytest.mark.unit
    def test_returns_list(self):
        """Should return a non-empty list."""
        langs = get_tesseract_languages()
        assert isinstance(langs, list)
        assert len(langs) > 0

    @pytest.mark.unit
    def test_eng_present(self):
        """English should always be available."""
        langs = get_tesseract_languages()
        assert "eng" in langs

    @pytest.mark.unit
    def test_fallback_on_missing_tesseract(self):
        """Should fall back to static list when tesseract is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            langs = get_tesseract_languages()
        assert langs == _TESSERACT_LANGS_STATIC

    @pytest.mark.unit
    def test_uses_subprocess_output_when_available(self):
        """Should parse subprocess output when tesseract is installed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "List of available languages (4):\neng\ndeu\nfra\nita\n"

        with patch("subprocess.run", return_value=mock_result):
            langs = get_tesseract_languages()

        assert langs == ["deu", "eng", "fra", "ita"]


class TestEasyOCRLanguageProvider:
    """Tests for get_easyocr_languages."""

    @pytest.mark.unit
    def test_returns_list(self):
        """Should return a non-empty list."""
        langs = get_easyocr_languages()
        assert isinstance(langs, list)
        assert len(langs) > 0

    @pytest.mark.unit
    def test_en_present(self):
        """English should always be available."""
        langs = get_easyocr_languages()
        assert "en" in langs

    @pytest.mark.unit
    def test_fallback_when_easyocr_missing(self):
        """Should fall back to static list when easyocr is not installed."""
        # easyocr is not installed in the test env, so this tests the real fallback
        langs = get_easyocr_languages()
        assert langs == _EASYOCR_LANGS_STATIC


class TestEmbeddingModelProvider:
    """Tests for get_embedding_models."""

    @pytest.mark.unit
    def test_returns_list(self):
        """Should return a non-empty list."""
        models = get_embedding_models()
        assert isinstance(models, list)
        assert len(models) > 0

    @pytest.mark.unit
    def test_default_model_present(self):
        """The default model should be in the list."""
        models = get_embedding_models()
        assert "text-embedding-3-small" in models

    @pytest.mark.unit
    def test_returns_static_list(self):
        """Should return the static embedding model list."""
        assert get_embedding_models() == _EMBEDDING_MODELS


# ---------------------------------------------------------------------------
# get_suggestions() tests
# ---------------------------------------------------------------------------


class TestGetSuggestions:
    """Tests for the get_suggestions aggregator function."""

    @pytest.mark.unit
    def test_all_providers_registered(self):
        """All expected keys should be registered."""
        expected_keys = {"aws_region", "azure_region", "tesseract_language", "easyocr_languages", "embedding_model"}
        assert expected_keys == set(SUGGESTION_PROVIDERS.keys())

    @pytest.mark.unit
    def test_unregistered_key_raises(self):
        """Requesting suggestions for an unknown key raises KeyError."""
        with pytest.raises(KeyError, match="no_such_setting"):
            get_suggestions("no_such_setting")

    @pytest.mark.unit
    def test_empty_query_returns_all(self):
        """Empty query returns all suggestions up to the limit."""
        results = get_suggestions("embedding_model", query="", limit=100)
        assert len(results) == len(_EMBEDDING_MODELS)

    @pytest.mark.unit
    def test_substring_filtering(self):
        """Query filters by case-insensitive substring."""
        results = get_suggestions("aws_region", query="east", limit=50)
        assert all("east" in r.lower() for r in results)
        assert len(results) > 0

    @pytest.mark.unit
    def test_case_insensitive(self):
        """Filtering should be case-insensitive."""
        results = get_suggestions("aws_region", query="EAST", limit=50)
        assert len(results) > 0
        assert "us-east-1" in results

    @pytest.mark.unit
    def test_limit_respected(self):
        """Results should not exceed the limit."""
        results = get_suggestions("tesseract_language", query="", limit=3)
        assert len(results) == 3

    @pytest.mark.unit
    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace in the query should be trimmed."""
        results = get_suggestions("aws_region", query="  us-east  ", limit=10)
        assert all("us-east" in r.lower() for r in results)


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------


class TestSuggestionsEndpoint:
    """Tests for GET /api/settings/{key}/suggestions."""

    @pytest.mark.integration
    def test_aws_region_suggestions(self, client):
        """AWS region endpoint returns suggestions."""
        response = client.get("/api/settings/aws_region/suggestions?q=east")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert data["key"] == "aws_region"
        assert len(data["suggestions"]) > 0
        assert all("east" in s.lower() for s in data["suggestions"])

    @pytest.mark.integration
    def test_azure_region_suggestions(self, client):
        """Azure region endpoint returns suggestions."""
        response = client.get("/api/settings/azure_region/suggestions?q=europe")
        assert response.status_code == 200
        data = response.json()
        assert "westeurope" in data["suggestions"]

    @pytest.mark.integration
    def test_tesseract_language_suggestions(self, client):
        """Tesseract language endpoint returns suggestions."""
        response = client.get("/api/settings/tesseract_language/suggestions?q=eng")
        assert response.status_code == 200
        data = response.json()
        assert "eng" in data["suggestions"]

    @pytest.mark.integration
    def test_easyocr_language_suggestions(self, client):
        """EasyOCR language endpoint returns suggestions."""
        response = client.get("/api/settings/easyocr_languages/suggestions?q=de")
        assert response.status_code == 200
        data = response.json()
        assert "de" in data["suggestions"]

    @pytest.mark.integration
    def test_embedding_model_suggestions(self, client):
        """Embedding model endpoint returns suggestions."""
        response = client.get("/api/settings/embedding_model/suggestions?q=embed")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) > 0

    @pytest.mark.integration
    def test_unknown_key_returns_404(self, client):
        """Unknown setting key returns 404."""
        response = client.get("/api/settings/nonexistent_setting/suggestions")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_empty_query_returns_results(self, client):
        """Empty query returns all suggestions up to limit."""
        response = client.get("/api/settings/embedding_model/suggestions?q=")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) > 0

    @pytest.mark.integration
    def test_limit_parameter(self, client):
        """Limit parameter restricts the number of results."""
        response = client.get("/api/settings/aws_region/suggestions?q=&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) <= 3

    @pytest.mark.integration
    def test_limit_clamped_to_max(self, client):
        """Limit over 50 should be clamped to 50."""
        response = client.get("/api/settings/tesseract_language/suggestions?q=&limit=999")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) <= 50
