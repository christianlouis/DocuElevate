"""OCR language manager for DocuElevate.

Ensures that Tesseract language data files (``.traineddata``) and EasyOCR
model files are present for every language code configured in the
application settings.

**Tesseract** language data is downloaded on demand from the
``tessdata_fast`` GitHub repository
(``https://github.com/tesseract-ocr/tessdata_fast``).  The data files are
written to the tessdata directory discovered at runtime (respects the
``TESSDATA_PREFIX`` environment variable and falls back to common system
paths).

**EasyOCR** models are downloaded via the library's built-in mechanism –
instantiating ``easyocr.Reader([lang])`` triggers the download if the model
files are absent from ``~/.EasyOCR/model/``.

Both functions are idempotent: they skip languages whose data is already
present.

Typical call sites:

* Application startup (``app/main.py`` lifespan) – runs in a background
  thread so it does not delay HTTP server readiness.
* Celery worker startup (``app/celery_worker.py``) – scheduled shortly
  after the worker comes online.
* Settings reload (``app/utils/settings_sync.py``) – triggered whenever the
  ``tesseract_language`` or ``easyocr_languages`` settings change.
* OCR provider ``process()`` methods – last-chance check before actually
  running OCR so a clear error is raised rather than a cryptic pytesseract
  or easyocr exception.
"""

import logging
import os
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: URL template for downloading Tesseract tessdata_fast language data files.
#: ``{lang}`` is replaced with the ISO 639-2 Tesseract language code
#: (e.g. ``eng``, ``deu``, ``fra``).
TESSDATA_FAST_BASE_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"

# ---------------------------------------------------------------------------
# Tesseract helpers
# ---------------------------------------------------------------------------


def get_tessdata_dir() -> Optional[str]:
    """Return the tessdata directory that Tesseract will use at runtime.

    Resolution order:

    1. ``TESSDATA_PREFIX`` environment variable (if it points to an existing
       directory).
    2. Common Debian/Ubuntu system paths (``/usr/share/tesseract-ocr/*/tessdata``).
    3. ``/usr/share/tessdata`` and ``/usr/local/share/tessdata`` as fallback.

    Returns:
        Absolute path to the tessdata directory, or ``None`` when none of the
        candidate paths exist.
    """
    # 1. Honour explicit TESSDATA_PREFIX
    tessdata_prefix = os.environ.get("TESSDATA_PREFIX")
    if tessdata_prefix:
        if os.path.isdir(tessdata_prefix):
            return tessdata_prefix
        logger.debug(f"TESSDATA_PREFIX={tessdata_prefix!r} is set but not a directory; ignoring")

    # 2. Common Debian/Ubuntu APT install paths (ordered by preference)
    candidates = [
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
        "/usr/local/share/tessdata",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path

    return None


def is_tesseract_language_available(lang_code: str) -> bool:
    """Return ``True`` if the ``<lang_code>.traineddata`` file exists.

    Args:
        lang_code: Tesseract language code, e.g. ``"eng"`` or ``"deu"``.
    """
    tessdata_dir = get_tessdata_dir()
    if not tessdata_dir:
        return False
    return os.path.isfile(os.path.join(tessdata_dir, f"{lang_code}.traineddata"))


def download_tesseract_language(lang_code: str) -> bool:
    """Download a Tesseract ``.traineddata`` file from the tessdata_fast repo.

    Uses ``wget`` if available, otherwise falls back to ``curl``.  The file
    is written directly into the tessdata directory so Tesseract can find it
    without any additional configuration.

    Args:
        lang_code: Tesseract language code, e.g. ``"eng"`` or ``"deu"``.

    Returns:
        ``True`` on success, ``False`` when the download fails or neither
        ``wget`` nor ``curl`` is available.
    """
    tessdata_dir = get_tessdata_dir()
    if not tessdata_dir:
        logger.warning(
            "No tessdata directory found; cannot download language data for '%s'. "
            "Set TESSDATA_PREFIX to a writable directory or install the Tesseract "
            "language pack manually.",
            lang_code,
        )
        return False

    target_path = os.path.join(tessdata_dir, f"{lang_code}.traineddata")
    url = f"{TESSDATA_FAST_BASE_URL}/{lang_code}.traineddata"

    wget_bin = shutil.which("wget")
    curl_bin = shutil.which("curl")

    if wget_bin:
        cmd = [wget_bin, "-q", "--show-progress", "-O", target_path, url]
    elif curl_bin:
        cmd = [curl_bin, "-fsSL", "-o", target_path, url]
    else:
        logger.warning(
            "Neither wget nor curl is available; cannot download Tesseract language data for '%s'. "
            "Install wget or curl, or add the language data manually to %s.",
            lang_code,
            tessdata_dir,
        )
        return False

    logger.info("Downloading Tesseract language data for '%s' from %s", lang_code, url)
    try:
        proc = subprocess.run(  # noqa: S603  # args are trusted paths/URLs
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timed out downloading Tesseract language data for '%s'", lang_code)
        # Remove partial download to avoid a corrupt tessdata file
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        return False

    if proc.returncode != 0:
        stderr_snippet = (proc.stderr or "").strip()[:300]
        logger.warning(
            "Failed to download Tesseract language data for '%s' (exit %d): %s",
            lang_code,
            proc.returncode,
            stderr_snippet,
        )
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        return False

    logger.info("Tesseract language data for '%s' downloaded successfully to %s", lang_code, target_path)
    return True


def ensure_tesseract_languages(lang_str: str) -> list[str]:
    """Ensure Tesseract language data files are available for all languages in *lang_str*.

    Language codes are separated by ``+`` (Tesseract convention), e.g.
    ``"eng+deu+fra"``.  For each code the function checks whether the
    ``.traineddata`` file already exists; if not it attempts to download it
    from the tessdata_fast repository.

    Args:
        lang_str: Tesseract-style language string, e.g. ``"eng"`` or ``"eng+deu"``.

    Returns:
        A list of language codes that are still unavailable after the download
        attempt.  An empty list means all languages are ready.
    """
    lang_codes = [code.strip() for code in lang_str.split("+") if code.strip()]
    still_missing: list[str] = []

    for lang_code in lang_codes:
        if is_tesseract_language_available(lang_code):
            logger.debug("Tesseract language '%s' is already available", lang_code)
            continue
        logger.info("Tesseract language '%s' not found locally; attempting download", lang_code)
        if not download_tesseract_language(lang_code):
            still_missing.append(lang_code)

    if still_missing:
        logger.warning(
            "The following Tesseract language(s) could not be installed: %s. "
            "OCR quality may be degraded or processing may fail.",
            ", ".join(still_missing),
        )

    return still_missing


# ---------------------------------------------------------------------------
# EasyOCR helpers
# ---------------------------------------------------------------------------


def ensure_easyocr_models(lang_list: list[str]) -> list[str]:
    """Pre-download EasyOCR model files for *lang_list*.

    Instantiates a temporary ``easyocr.Reader`` for each language to trigger
    the built-in model-download mechanism.  Models are cached in
    ``~/.EasyOCR/model/`` and reused on subsequent calls, so this function is
    safe to call repeatedly.

    This function is a no-op when ``easyocr`` is not installed.

    Args:
        lang_list: List of EasyOCR language codes, e.g. ``["en", "de"]``.

    Returns:
        A list of language codes whose models could not be downloaded.  An
        empty list means all models are ready.
    """
    try:
        import easyocr  # noqa: PLC0415
    except ImportError:
        logger.debug("easyocr is not installed; skipping model pre-download")
        return []

    failed: list[str] = []
    for lang in lang_list:
        try:
            logger.info("Pre-downloading EasyOCR model for '%s'", lang)
            easyocr.Reader([lang], gpu=False, verbose=False)
            logger.info("EasyOCR model for '%s' is ready", lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to pre-download EasyOCR model for '%s': %s", lang, exc)
            failed.append(lang)

    if failed:
        logger.warning(
            "The following EasyOCR language model(s) could not be downloaded: %s. "
            "OCR processing for these languages may fail.",
            ", ".join(failed),
        )

    return failed


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------


def ensure_ocr_languages_from_settings() -> dict[str, list[str]]:
    """Ensure OCR language data is available for all configured languages.

    Reads ``ocr_providers``, ``tesseract_language``, and ``easyocr_languages``
    from the application settings and ensures the required language data is
    present.  Missing Tesseract tessdata files are downloaded automatically;
    missing EasyOCR models are downloaded via the library's built-in mechanism.

    Tesseract language data is always ensured when ``ocrmypdf`` is available on
    the system, regardless of which OCR providers are active.  This is required
    because :func:`~app.utils.ocr_provider.embed_text_layer` uses ``ocrmypdf``
    (and therefore Tesseract) as a post-processing fallback for **all** OCR
    providers – not only the ``tesseract`` provider.

    This function is idempotent – calling it multiple times is safe.

    Returns:
        A dict with keys:

        * ``"tesseract_missing"`` – Tesseract language codes that could not
          be installed.
        * ``"easyocr_failed"`` – EasyOCR language codes whose models could
          not be downloaded.
    """
    # Import inside function to avoid circular imports at module load time
    from app.config import settings  # noqa: PLC0415

    result: dict[str, list[str]] = {"tesseract_missing": [], "easyocr_failed": []}

    providers_raw = getattr(settings, "ocr_providers", None) or "azure"
    active_providers = {p.strip().lower() for p in providers_raw.split(",") if p.strip()}

    # Always ensure Tesseract language data when ocrmypdf is on the system PATH.
    # embed_text_layer() calls ocrmypdf as a text-layer post-processor for every
    # OCR provider that does not natively produce a searchable PDF (azure,
    # easyocr, mistral, google_docai, aws_textract).  If the tessdata files are
    # absent, ocrmypdf exits with code 3 and the text layer is silently skipped.
    if "tesseract" in active_providers or shutil.which("ocrmypdf") is not None:
        lang_str = getattr(settings, "tesseract_language", None) or "eng"
        logger.info("Ensuring Tesseract language data for configured languages: %s", lang_str)
        result["tesseract_missing"] = ensure_tesseract_languages(lang_str)

    if "easyocr" in active_providers:
        lang_raw = getattr(settings, "easyocr_languages", None) or "en"
        lang_list = [stripped for lang in lang_raw.split(",") if (stripped := lang.strip())]
        logger.info("Ensuring EasyOCR models for configured languages: %s", lang_list)
        result["easyocr_failed"] = ensure_easyocr_models(lang_list)

    return result


def ensure_ocr_languages_async() -> None:
    """Run :func:`ensure_ocr_languages_from_settings` in a background thread.

    This is the preferred startup call so that language downloads do not block
    the HTTP server or Celery worker from becoming ready.
    """
    thread = threading.Thread(
        target=_run_ensure_languages,
        name="ocr-language-manager",
        daemon=True,
    )
    thread.start()


def _run_ensure_languages() -> None:
    """Internal target function for the background thread."""
    try:
        result = ensure_ocr_languages_from_settings()
        missing = result.get("tesseract_missing", []) + result.get("easyocr_failed", [])
        if missing:
            logger.warning(
                "OCR language setup incomplete – the following language(s) are still unavailable: %s",
                ", ".join(missing),
            )
        else:
            logger.info("OCR language setup complete – all configured languages are available")
    except Exception as exc:  # noqa: BLE001
        logger.error("Error during OCR language setup: %s", exc)
