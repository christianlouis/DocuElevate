"""Unit tests for app.utils.ocr_language_manager.

Tests cover tessdata-directory detection, language availability checks,
download success/failure paths, and the combined orchestration function.
All external calls (filesystem, subprocess, easyocr, app.config) are mocked.
"""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.unit
class TestGetTessdataDir:
    """Tests for get_tessdata_dir()."""

    def test_returns_tessdata_prefix_when_valid(self, tmp_path):
        """TESSDATA_PREFIX env var pointing to an existing dir is used first."""
        from app.utils.ocr_language_manager import get_tessdata_dir

        with patch.dict("os.environ", {"TESSDATA_PREFIX": str(tmp_path)}):
            result = get_tessdata_dir()
        assert result == str(tmp_path)

    def test_ignores_tessdata_prefix_when_not_a_dir(self, tmp_path):
        """TESSDATA_PREFIX pointing to a non-directory path is ignored."""
        non_dir = str(tmp_path / "nonexistent")
        from app.utils.ocr_language_manager import get_tessdata_dir

        with (
            patch.dict("os.environ", {"TESSDATA_PREFIX": non_dir}),
            patch("os.path.isdir", side_effect=lambda p: False),
        ):
            result = get_tessdata_dir()
        assert result is None

    def test_falls_back_to_system_path(self, tmp_path):
        """Returns first existing system candidate path when TESSDATA_PREFIX is absent."""
        from app.utils.ocr_language_manager import get_tessdata_dir

        def isdir_side_effect(path: str) -> bool:
            return path == "/usr/share/tesseract-ocr/5/tessdata"

        with (
            patch.dict("os.environ", {}, clear=False),
            patch("os.environ.get", side_effect=lambda k, d=None: None if k == "TESSDATA_PREFIX" else d),
            patch("os.path.isdir", side_effect=isdir_side_effect),
        ):
            result = get_tessdata_dir()
        assert result == "/usr/share/tesseract-ocr/5/tessdata"

    def test_returns_none_when_no_path_found(self):
        """Returns None when TESSDATA_PREFIX is absent and no system paths exist."""
        from app.utils.ocr_language_manager import get_tessdata_dir

        with (
            patch("os.environ.get", return_value=None),
            patch("os.path.isdir", return_value=False),
        ):
            result = get_tessdata_dir()
        assert result is None


@pytest.mark.unit
class TestIsTesseractLanguageAvailable:
    """Tests for is_tesseract_language_available()."""

    def test_returns_true_when_file_exists(self, tmp_path):
        """Returns True when <lang>.traineddata is present in tessdata dir."""
        (tmp_path / "eng.traineddata").write_bytes(b"fake")
        from app.utils.ocr_language_manager import is_tesseract_language_available

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)):
            assert is_tesseract_language_available("eng") is True

    def test_returns_false_when_file_missing(self, tmp_path):
        """Returns False when the traineddata file is absent."""
        from app.utils.ocr_language_manager import is_tesseract_language_available

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)):
            assert is_tesseract_language_available("deu") is False

    def test_returns_false_when_no_tessdata_dir(self):
        """Returns False when no tessdata directory is found."""
        from app.utils.ocr_language_manager import is_tesseract_language_available

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=None):
            assert is_tesseract_language_available("eng") is False


@pytest.mark.unit
class TestDownloadTesseractLanguage:
    """Tests for download_tesseract_language()."""

    def test_returns_false_when_no_tessdata_dir(self):
        """Returns False when no tessdata directory is found."""
        from app.utils.ocr_language_manager import download_tesseract_language

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=None):
            result = download_tesseract_language("deu")
        assert result is False

    def test_returns_false_when_no_downloader(self, tmp_path):
        """Returns False when neither wget nor curl is on PATH."""
        from app.utils.ocr_language_manager import download_tesseract_language

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("shutil.which", return_value=None),
        ):
            result = download_tesseract_language("deu")
        assert result is False

    def test_uses_wget_when_available(self, tmp_path):
        """Uses wget when available and returns True on success."""
        from app.utils.ocr_language_manager import download_tesseract_language

        mock_proc = Mock()
        mock_proc.returncode = 0

        def which_side_effect(cmd):
            if cmd == "wget":
                return "/usr/bin/wget"
            return None

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            result = download_tesseract_language("deu")

        assert result is True
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "/usr/bin/wget"
        assert any("deu.traineddata" in arg for arg in called_cmd)

    def test_falls_back_to_curl(self, tmp_path):
        """Falls back to curl when wget is unavailable and returns True on success."""
        from app.utils.ocr_language_manager import download_tesseract_language

        mock_proc = Mock()
        mock_proc.returncode = 0

        def which_side_effect(cmd):
            if cmd == "curl":
                return "/usr/bin/curl"
            return None

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            result = download_tesseract_language("fra")

        assert result is True
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "/usr/bin/curl"

    def test_returns_false_on_nonzero_exit(self, tmp_path):
        """Returns False and removes partial file when download exits non-zero."""
        target = tmp_path / "deu.traineddata"
        target.write_bytes(b"partial")
        from app.utils.ocr_language_manager import download_tesseract_language

        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "404 Not Found"

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("shutil.which", return_value="/usr/bin/wget"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            result = download_tesseract_language("deu")

        assert result is False
        assert not target.exists()

    def test_returns_false_on_timeout(self, tmp_path):
        """Returns False and removes partial file when subprocess times out."""
        target = tmp_path / "deu.traineddata"
        target.write_bytes(b"partial")
        from app.utils.ocr_language_manager import download_tesseract_language

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("shutil.which", return_value="/usr/bin/wget"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="wget", timeout=180)),
        ):
            result = download_tesseract_language("deu")

        assert result is False
        assert not target.exists()


@pytest.mark.unit
class TestEnsureTesseractLanguages:
    """Tests for ensure_tesseract_languages()."""

    def test_skips_already_available_languages(self, tmp_path):
        """No download is attempted for languages that already have traineddata files."""
        (tmp_path / "eng.traineddata").write_bytes(b"fake")
        (tmp_path / "deu.traineddata").write_bytes(b"fake")
        from app.utils.ocr_language_manager import ensure_tesseract_languages

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("app.utils.ocr_language_manager.download_tesseract_language") as mock_dl,
        ):
            missing = ensure_tesseract_languages("eng+deu")

        assert missing == []
        mock_dl.assert_not_called()

    def test_downloads_missing_language(self, tmp_path):
        """Attempts to download a missing language and returns empty list on success."""
        (tmp_path / "eng.traineddata").write_bytes(b"fake")
        from app.utils.ocr_language_manager import ensure_tesseract_languages

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("app.utils.ocr_language_manager.download_tesseract_language", return_value=True) as mock_dl,
        ):
            missing = ensure_tesseract_languages("eng+deu")

        assert missing == []
        mock_dl.assert_called_once_with("deu")

    def test_returns_still_missing_on_download_failure(self, tmp_path):
        """Returns failing language codes when download fails."""
        from app.utils.ocr_language_manager import ensure_tesseract_languages

        with (
            patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)),
            patch("app.utils.ocr_language_manager.download_tesseract_language", return_value=False),
        ):
            missing = ensure_tesseract_languages("eng+fra")

        assert set(missing) == {"eng", "fra"}

    def test_single_language_no_plus(self, tmp_path):
        """Handles single language code without '+' separator."""
        (tmp_path / "eng.traineddata").write_bytes(b"fake")
        from app.utils.ocr_language_manager import ensure_tesseract_languages

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)):
            missing = ensure_tesseract_languages("eng")

        assert missing == []

    def test_ignores_empty_tokens(self, tmp_path):
        """Handles malformed lang strings with extra '+' separators."""
        (tmp_path / "eng.traineddata").write_bytes(b"fake")
        from app.utils.ocr_language_manager import ensure_tesseract_languages

        with patch("app.utils.ocr_language_manager.get_tessdata_dir", return_value=str(tmp_path)):
            missing = ensure_tesseract_languages("+eng+")

        assert missing == []


@pytest.mark.unit
class TestEnsureEasyOCRModels:
    """Tests for ensure_easyocr_models()."""

    def test_no_op_when_easyocr_not_installed(self):
        """Returns empty list silently when easyocr cannot be imported."""
        from app.utils.ocr_language_manager import ensure_easyocr_models

        with patch("builtins.__import__", side_effect=ImportError("No module named 'easyocr'")):
            result = ensure_easyocr_models(["en"])
        # The function should handle import error gracefully
        assert isinstance(result, list)

    def test_returns_empty_list_on_success(self):
        """Returns empty list when all models download successfully."""
        mock_reader_cls = MagicMock()
        from app.utils.ocr_language_manager import ensure_easyocr_models

        with patch.dict("sys.modules", {"easyocr": MagicMock(Reader=mock_reader_cls)}):
            result = ensure_easyocr_models(["en", "de"])

        assert result == []

    def test_returns_failed_langs_on_error(self):
        """Returns failing language codes when easyocr.Reader raises an exception."""
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.side_effect = RuntimeError("download failed")
        from app.utils.ocr_language_manager import ensure_easyocr_models

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            result = ensure_easyocr_models(["fr"])

        assert "fr" in result

    def test_skips_successfully_downloads_partially(self):
        """Returns only the failing codes when some languages succeed and others fail."""
        call_count = {"n": 0}

        def reader_side_effect(langs, gpu=False, verbose=False):
            call_count["n"] += 1
            if langs == ["ja"]:
                raise RuntimeError("model download failed")

        mock_easyocr = MagicMock()
        mock_easyocr.Reader.side_effect = reader_side_effect
        from app.utils.ocr_language_manager import ensure_easyocr_models

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            result = ensure_easyocr_models(["en", "ja"])

        assert result == ["ja"]
        assert call_count["n"] == 2


@pytest.mark.unit
class TestEnsureOCRLanguagesFromSettings:
    """Tests for ensure_ocr_languages_from_settings()."""

    def _mock_settings(self, providers="tesseract", tesseract_lang="eng", easyocr_langs="en"):
        mock_settings = MagicMock()
        mock_settings.ocr_providers = providers
        mock_settings.tesseract_language = tesseract_lang
        mock_settings.easyocr_languages = easyocr_langs
        return mock_settings

    def test_runs_tesseract_check_when_provider_active(self):
        """Calls ensure_tesseract_languages when 'tesseract' is in ocr_providers."""
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="tesseract", tesseract_lang="eng+deu")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=[]) as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models", return_value=[]) as mock_easy,
            patch("app.config.settings", mock_settings),
        ):
            result = ensure_ocr_languages_from_settings()

        mock_tess.assert_called_once_with("eng+deu")
        mock_easy.assert_not_called()
        assert result == {"tesseract_missing": [], "easyocr_failed": []}

    def test_runs_easyocr_check_when_provider_active(self):
        """Calls ensure_easyocr_models when 'easyocr' is in ocr_providers.

        When ocrmypdf is absent, only easyocr language checks run.
        """
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="easyocr", easyocr_langs="en,de")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=[]) as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models", return_value=[]) as mock_easy,
            patch("app.config.settings", mock_settings),
            patch("shutil.which", return_value=None),
        ):
            result = ensure_ocr_languages_from_settings()

        mock_tess.assert_not_called()
        mock_easy.assert_called_once_with(["en", "de"])
        assert result["easyocr_failed"] == []

    def test_skips_both_when_only_azure_and_no_ocrmypdf(self):
        """Neither Tesseract nor EasyOCR checks run when only Azure is configured and ocrmypdf is absent."""
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="azure")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages") as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models") as mock_easy,
            patch("app.config.settings", mock_settings),
            patch("shutil.which", return_value=None),
        ):
            result = ensure_ocr_languages_from_settings()

        mock_tess.assert_not_called()
        mock_easy.assert_not_called()
        assert result == {"tesseract_missing": [], "easyocr_failed": []}

    def test_runs_tesseract_when_ocrmypdf_available_with_non_tesseract_provider(self):
        """Tesseract language check runs when ocrmypdf is on PATH even without the tesseract provider.

        embed_text_layer() uses ocrmypdf internally regardless of the active OCR
        provider.  Pre-downloading language data on startup prevents code-3 failures.
        """
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="azure", tesseract_lang="eng+deu+fra")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=[]) as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models") as mock_easy,
            patch("app.config.settings", mock_settings),
            patch("shutil.which", return_value="/usr/local/bin/ocrmypdf"),
        ):
            result = ensure_ocr_languages_from_settings()

        mock_tess.assert_called_once_with("eng+deu+fra")
        mock_easy.assert_not_called()
        assert result == {"tesseract_missing": [], "easyocr_failed": []}

    def test_runs_both_when_both_providers_active(self):
        """Both checks run when both 'tesseract' and 'easyocr' are in ocr_providers."""
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="tesseract,easyocr")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=[]) as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models", return_value=[]) as mock_easy,
            patch("app.config.settings", mock_settings),
        ):
            ensure_ocr_languages_from_settings()

        mock_tess.assert_called_once()
        mock_easy.assert_called_once()

    def test_returns_missing_and_failed_on_partial_failure(self):
        """Returns correct missing/failed lists on partial failures."""
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = self._mock_settings(providers="tesseract,easyocr")
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=["deu"]),
            patch("app.utils.ocr_language_manager.ensure_easyocr_models", return_value=["ja"]),
            patch("app.config.settings", mock_settings),
        ):
            result = ensure_ocr_languages_from_settings()

        assert result["tesseract_missing"] == ["deu"]
        assert result["easyocr_failed"] == ["ja"]

    def test_uses_defaults_when_settings_are_none(self):
        """Falls back to 'eng' / 'en' when language settings are None."""
        from app.utils.ocr_language_manager import ensure_ocr_languages_from_settings

        mock_settings = MagicMock()
        mock_settings.ocr_providers = "tesseract,easyocr"
        mock_settings.tesseract_language = None
        mock_settings.easyocr_languages = None
        with (
            patch("app.utils.ocr_language_manager.ensure_tesseract_languages", return_value=[]) as mock_tess,
            patch("app.utils.ocr_language_manager.ensure_easyocr_models", return_value=[]) as mock_easy,
            patch("app.config.settings", mock_settings),
        ):
            ensure_ocr_languages_from_settings()

        mock_tess.assert_called_once_with("eng")
        mock_easy.assert_called_once_with(["en"])


@pytest.mark.unit
class TestEnsureOCRLanguagesAsync:
    """Tests for ensure_ocr_languages_async() background thread helper."""

    def test_starts_daemon_thread(self):
        """ensure_ocr_languages_async starts a daemon thread."""
        import threading

        from app.utils.ocr_language_manager import ensure_ocr_languages_async

        started_threads: list[threading.Thread] = []
        original_start = threading.Thread.start

        def track_start(self_thread):
            started_threads.append(self_thread)
            original_start(self_thread)

        with (
            patch.object(threading.Thread, "start", track_start),
            patch("app.utils.ocr_language_manager.ensure_ocr_languages_from_settings", return_value={}),
        ):
            ensure_ocr_languages_async()

        assert any(t.name == "ocr-language-manager" for t in started_threads)
        assert all(t.daemon for t in started_threads if t.name == "ocr-language-manager")
