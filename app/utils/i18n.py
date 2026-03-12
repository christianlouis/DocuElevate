"""Internationalization (i18n) and localization (l10n) utilities.

Provides a JSON-based translation system for the DocuElevate UI with:

* **31 supported languages** covering all major European languages plus ZH
* Browser ``Accept-Language`` detection with cookie & user-profile persistence
* AI-powered fallback translation via the configured LLM provider
* Locale-aware date, number, and file-size formatting helpers
* Jinja2 integration via a ``_()`` global function

Language resolution order:
    1. User profile ``preferred_language`` (persisted in DB)
    2. ``docuelevate_lang`` cookie
    3. ``Accept-Language`` HTTP header
    4. Default (``en``)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from starlette.requests import Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported languages (ordered by priority)
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    # --- Tier 1: Primary European languages ---
    {"code": "en", "name": "English", "native": "English", "flag": "🇬🇧"},
    {"code": "de", "name": "German", "native": "Deutsch", "flag": "🇩🇪"},
    {"code": "fr", "name": "French", "native": "Français", "flag": "🇫🇷"},
    {"code": "es", "name": "Spanish", "native": "Español", "flag": "🇪🇸"},
    {"code": "it", "name": "Italian", "native": "Italiano", "flag": "🇮🇹"},
    {"code": "pt", "name": "Portuguese", "native": "Português", "flag": "🇵🇹"},
    # --- Tier 2: Western & Northern European ---
    {"code": "nl", "name": "Dutch", "native": "Nederlands", "flag": "🇳🇱"},
    {"code": "nb", "name": "Norwegian", "native": "Norsk", "flag": "🇳🇴"},
    {"code": "da", "name": "Danish", "native": "Dansk", "flag": "🇩🇰"},
    {"code": "sv", "name": "Swedish", "native": "Svenska", "flag": "🇸🇪"},
    {"code": "fi", "name": "Finnish", "native": "Suomi", "flag": "🇫🇮"},
    {"code": "is", "name": "Icelandic", "native": "Íslenska", "flag": "🇮🇸"},
    {"code": "ga", "name": "Irish", "native": "Gaeilge", "flag": "🇮🇪"},
    {"code": "lb", "name": "Luxembourgish", "native": "Lëtzebuergesch", "flag": "🇱🇺"},
    {"code": "ca", "name": "Catalan", "native": "Català", "flag": "🏴"},
    # --- Tier 3: Central & Eastern European ---
    {"code": "pl", "name": "Polish", "native": "Polski", "flag": "🇵🇱"},
    {"code": "cs", "name": "Czech", "native": "Čeština", "flag": "🇨🇿"},
    {"code": "sk", "name": "Slovak", "native": "Slovenčina", "flag": "🇸🇰"},
    {"code": "hu", "name": "Hungarian", "native": "Magyar", "flag": "🇭🇺"},
    {"code": "sl", "name": "Slovenian", "native": "Slovenščina", "flag": "🇸🇮"},
    {"code": "hr", "name": "Croatian", "native": "Hrvatski", "flag": "🇭🇷"},
    {"code": "ro", "name": "Romanian", "native": "Română", "flag": "🇷🇴"},
    {"code": "bg", "name": "Bulgarian", "native": "Български", "flag": "🇧🇬"},
    {"code": "el", "name": "Greek", "native": "Ελληνικά", "flag": "🇬🇷"},
    {"code": "et", "name": "Estonian", "native": "Eesti", "flag": "🇪🇪"},
    {"code": "lv", "name": "Latvian", "native": "Latviešu", "flag": "🇱🇻"},
    {"code": "lt", "name": "Lithuanian", "native": "Lietuvių", "flag": "🇱🇹"},
    # --- Tier 4: Non-EU European & Other ---
    {"code": "tr", "name": "Turkish", "native": "Türkçe", "flag": "🇹🇷"},
    {"code": "uk", "name": "Ukrainian", "native": "Українська", "flag": "🇺🇦"},
    {"code": "ru", "name": "Russian", "native": "Русский", "flag": "🇷🇺"},
    {"code": "zh", "name": "Chinese", "native": "中文", "flag": "🇨🇳"},
]

SUPPORTED_LANGUAGE_CODES: set[str] = {lang["code"] for lang in SUPPORTED_LANGUAGES}
DEFAULT_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# Translation file loading
# ---------------------------------------------------------------------------

_TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "translations"
_translation_cache: dict[str, dict[str, str]] = {}


def _load_translations(locale: str) -> dict[str, str]:
    """Load the translation JSON file for *locale*, with caching."""
    if locale in _translation_cache:
        return _translation_cache[locale]

    filepath = _TRANSLATIONS_DIR / f"{locale}.json"
    if not filepath.is_file():
        logger.warning("Translation file not found for locale '%s'", locale)
        _translation_cache[locale] = {}
        return {}

    try:
        data: dict[str, str] = json.loads(filepath.read_text(encoding="utf-8"))
        _translation_cache[locale] = data
        return data
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load translations for '%s'", locale)
        _translation_cache[locale] = {}
        return {}


def reload_translations() -> None:
    """Clear the translation cache so files are re-read on next access."""
    _translation_cache.clear()


# ---------------------------------------------------------------------------
# Core translation function
# ---------------------------------------------------------------------------


def translate(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """Return the translated string for *key* in *locale*.

    Falls back through:
        1. Requested *locale*
        2. English (``en``)
        3. The raw key itself (to keep the UI functional)

    Positional placeholders ``{0}``, ``{1}`` or named placeholders
    ``{name}`` in the translated string are interpolated via *kwargs*.
    """
    locale = locale if locale and locale in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE

    translations = _load_translations(locale)
    value = translations.get(key)

    # Fallback to English
    if value is None and locale != DEFAULT_LANGUAGE:
        en_translations = _load_translations(DEFAULT_LANGUAGE)
        value = en_translations.get(key)

    # Fallback to key itself
    if value is None:
        value = key

    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, IndexError):
            pass  # Return unformatted string rather than crash

    return value


# ---------------------------------------------------------------------------
# AI fallback translation (best-effort, non-blocking)
# ---------------------------------------------------------------------------

_ai_translation_cache: dict[tuple[str, str], str] = {}


def translate_with_ai_fallback(text: str, target_locale: str) -> str:
    """Translate *text* using the configured AI provider as a fallback.

    Returns the original *text* unchanged when:
    * The target locale is English (source language)
    * The AI provider is unavailable or returns an error
    * The translation has already been cached

    Results are cached in-memory for the lifetime of the process.
    """
    if target_locale == DEFAULT_LANGUAGE or target_locale not in SUPPORTED_LANGUAGE_CODES:
        return text

    cache_key = (text, target_locale)
    if cache_key in _ai_translation_cache:
        return _ai_translation_cache[cache_key]

    target_name = next(
        (lang["name"] for lang in SUPPORTED_LANGUAGES if lang["code"] == target_locale),
        target_locale,
    )

    try:
        from litellm import completion  # type: ignore[import-untyped]

        from app.config import settings

        model = getattr(settings, "ai_model", None) or getattr(settings, "openai_model", "gpt-4o-mini")
        response = completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. Translate the following UI text "
                        f"from English to {target_name}. Return ONLY the translated text, "
                        f"nothing else. Keep any HTML tags, placeholders like {{name}}, "
                        f"and special characters intact."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=256,
            temperature=0.1,
        )
        translated = response.choices[0].message.content.strip()
        _ai_translation_cache[cache_key] = translated
        return translated
    except Exception:
        logger.debug("AI fallback translation failed for '%s' → %s", text[:50], target_locale)
        return text


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def detect_language(request: Request) -> str:
    """Determine the preferred UI language from the request context.

    Resolution order:
        1. ``preferred_language`` stored in the user session
        2. ``docuelevate_lang`` cookie
        3. ``Accept-Language`` HTTP header (best match)
        4. Default → ``en``
    """
    # 1. User session preference
    if hasattr(request, "session"):
        session_lang = request.session.get("preferred_language")
        if isinstance(session_lang, str) and session_lang in SUPPORTED_LANGUAGE_CODES:
            return session_lang

    # 2. Cookie
    if hasattr(request, "cookies"):
        cookie_lang = request.cookies.get("docuelevate_lang")
        if isinstance(cookie_lang, str) and cookie_lang in SUPPORTED_LANGUAGE_CODES:
            return cookie_lang

    # 3. Accept-Language header
    accept = ""
    if hasattr(request, "headers"):
        accept = request.headers.get("accept-language", "")
    lang = _parse_accept_language(accept)
    if lang:
        return lang

    return DEFAULT_LANGUAGE


def _parse_accept_language(header: str) -> str | None:
    """Extract the best matching language from an ``Accept-Language`` header.

    Parses quality values and returns the highest-priority match among
    :data:`SUPPORTED_LANGUAGE_CODES`, or ``None`` if nothing matches.
    """
    if not header:
        return None

    entries: list[tuple[float, str]] = []
    for raw_part in header.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ";q=" in part:
            lang_tag, _, q_str = part.partition(";q=")
            try:
                quality = float(q_str.strip())
            except ValueError:
                quality = 0.0
        else:
            lang_tag = part
            quality = 1.0
        entries.append((quality, lang_tag.strip().lower()))

    # Sort by quality descending
    entries.sort(key=lambda e: e[0], reverse=True)

    for _quality, tag in entries:
        # Try exact match first (e.g., "de", "zh")
        code = tag.split("-")[0]
        if code in SUPPORTED_LANGUAGE_CODES:
            return code

    return None


# ---------------------------------------------------------------------------
# Localization helpers (l10n)
# ---------------------------------------------------------------------------

# Locale-specific formatting rules for date/number display
_LOCALE_FORMATS: dict[str, dict[str, Any]] = {
    "en": {
        "date": "%B %d, %Y",
        "date_short": "%m/%d/%Y",
        "datetime": "%B %d, %Y %I:%M %p",
        "thousands_sep": ",",
        "decimal_sep": ".",
    },
    "de": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "fr": {
        "date": "%d %B %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u202f",
        "decimal_sep": ",",
    },
    "es": {
        "date": "%d de %B de %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d de %B de %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "it": {
        "date": "%d %B %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "pt": {
        "date": "%d de %B de %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d de %B de %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "nl": {
        "date": "%d %B %Y",
        "date_short": "%d-%m-%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "nb": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "da": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "sv": {
        "date": "%d %B %Y",
        "date_short": "%Y-%m-%d",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "fi": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "is": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "ga": {
        "date": "%d %B %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ",",
        "decimal_sep": ".",
    },
    "lb": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "ca": {
        "date": "%d de %B de %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d de %B de %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "pl": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "cs": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "sk": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "hu": {
        "date": "%Y. %B %d.",
        "date_short": "%Y.%m.%d.",
        "datetime": "%Y. %B %d. %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "sl": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "hr": {
        "date": "%d. %B %Y.",
        "date_short": "%d.%m.%Y.",
        "datetime": "%d. %B %Y. %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "ro": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "bg": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "el": {
        "date": "%d %B %Y",
        "date_short": "%d/%m/%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "et": {
        "date": "%d. %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d. %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "lv": {
        "date": "%Y. gada %d. %B",
        "date_short": "%d.%m.%Y.",
        "datetime": "%Y. gada %d. %B %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "lt": {
        "date": "%Y m. %B %d d.",
        "date_short": "%Y-%m-%d",
        "datetime": "%Y m. %B %d d. %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "tr": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": ".",
        "decimal_sep": ",",
    },
    "uk": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
    "zh": {
        "date": "%Y年%m月%d日",
        "date_short": "%Y/%m/%d",
        "datetime": "%Y年%m月%d日 %H:%M",
        "thousands_sep": ",",
        "decimal_sep": ".",
    },
    "ru": {
        "date": "%d %B %Y",
        "date_short": "%d.%m.%Y",
        "datetime": "%d %B %Y %H:%M",
        "thousands_sep": "\u00a0",
        "decimal_sep": ",",
    },
}


def format_date(value: date | datetime | None, locale: str = DEFAULT_LANGUAGE, short: bool = False) -> str:
    """Format a date/datetime value according to the locale conventions."""
    if value is None:
        return ""
    fmt_key = "date_short" if short else "date"
    fmt = _LOCALE_FORMATS.get(locale, _LOCALE_FORMATS[DEFAULT_LANGUAGE])[fmt_key]
    return value.strftime(fmt)


def format_datetime(value: datetime | None, locale: str = DEFAULT_LANGUAGE) -> str:
    """Format a datetime value according to the locale conventions."""
    if value is None:
        return ""
    fmt = _LOCALE_FORMATS.get(locale, _LOCALE_FORMATS[DEFAULT_LANGUAGE])["datetime"]
    return value.strftime(fmt)


def format_number(value: int | float, locale: str = DEFAULT_LANGUAGE) -> str:
    """Format a number with locale-appropriate thousand separators."""
    lf = _LOCALE_FORMATS.get(locale, _LOCALE_FORMATS[DEFAULT_LANGUAGE])
    if isinstance(value, float):
        int_part, _, dec_part = f"{value:,.2f}".partition(".")
        formatted_int = int_part.replace(",", lf["thousands_sep"])
        return f"{formatted_int}{lf['decimal_sep']}{dec_part}"
    return f"{value:,}".replace(",", lf["thousands_sep"])


@lru_cache(maxsize=32)
def get_language_info(code: str) -> dict[str, str] | None:
    """Return the metadata dict for a supported language code, or ``None``."""
    for lang in SUPPORTED_LANGUAGES:
        if lang["code"] == code:
            return lang
    return None
