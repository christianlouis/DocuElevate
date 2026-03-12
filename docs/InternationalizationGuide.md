# Internationalization (i18n) & Localization (l10n) Guide

DocuElevate supports **31 languages** for its web UI, with automatic browser
language detection, user-preference persistence, and an AI-powered fallback
translator for strings that haven't been manually translated yet.

## Supported Languages

Key supported languages include:

| Code | Language    | Native Name | Priority |
|------|------------|-------------|----------|
| `en` | English    | English     | Tier 1   |
| `de` | German     | Deutsch     | Tier 1   |
| `fr` | French     | Français    | Tier 1   |
| `es` | Spanish    | Español     | Tier 1   |
| `it` | Italian    | Italiano    | Tier 1   |
| `pt` | Portuguese | Português   | Tier 1   |
| `nl` | Dutch      | Nederlands  | Tier 2   |
| `pl` | Polish     | Polski      | Tier 2   |
| `zh` | Chinese    | 中文         | Tier 2   |
| `ru` | Russian    | Русский     | Tier 2   |

> DocuElevate currently ships one translation JSON file per supported locale in
> `frontend/translations/`. English (`en`) is the reference file, and every
> other locale must keep the exact same keys and placeholders.

## How Language Is Detected

DocuElevate resolves the display language in the following priority order:

1. **User profile preference** — stored in the database (`UserProfile.preferred_language`)
   and loaded into the session on login
2. **Cookie** — `docuelevate_lang` cookie (30-day expiry, set when user selects a language)
3. **Browser `Accept-Language` header** — the highest-priority match among supported languages
4. **Default** — English (`en`)

## Selecting Your Language

### Via the Navigation Bar

Click the 🌐 **globe icon** in the top navigation bar. A dropdown menu shows all
available languages with their native names and flag emoji. The current language
is highlighted with a blue checkmark.

### Via the API

```bash
# Set language to German
curl -X POST http://localhost:8000/api/i18n/language \
  -H "Content-Type: application/json" \
  -d '{"language": "de"}'

# List all available languages
curl http://localhost:8000/api/i18n/languages
```

### Via Cookie (Programmatic)

Set the `docuelevate_lang` cookie to any supported language code:

```javascript
document.cookie = "docuelevate_lang=fr; max-age=2592000; path=/";
location.reload();
```

## For Developers

### Translation File Structure

Translations are stored as flat JSON files in `frontend/translations/`:

```
frontend/translations/
├── en.json    # English (base / reference)
├── de.json    # German
├── fr.json    # French
├── ...
└── uk.json    # Ukrainian
```

There are currently **31** locale files. Every locale file must contain the
same translation keys as `en.json`.

Each file is a flat key-value dictionary with dot-notation namespacing:

```json
{
  "nav.dashboard": "Dashboard",
  "nav.upload": "Upload",
  "upload.max_size": "Maximum file size: {size}",
  "footer.copyright": "DocuElevate {year}"
}
```

### Using Translations in Templates

The `_()` function is available globally in all Jinja2 templates:

```jinja2
{# Simple translation #}
<h1>{{ _("dashboard.title") }}</h1>

{# Translation with placeholders #}
<p>{{ _("upload.max_size", size="50 MB") }}</p>

{# Translation in attributes #}
<button aria-label="{{ _('common.save') }}">{{ _("common.save") }}</button>
```

### Using Translations in Python

```python
from app.utils.i18n import translate

# Basic translation
text = translate("nav.dashboard", "de")  # → "Übersicht"

# With placeholders
text = translate("footer.copyright", "fr", year="2025")  # → "DocuElevate 2025"
```

### Localization Helpers

Format dates, times, and numbers according to locale conventions:

```jinja2
{# In templates — locale is automatically detected #}
<span>{{ format_date_l10n(document.created_at) }}</span>
<span>{{ format_number_l10n(file_count) }}</span>
```

```python
# In Python
from app.utils.i18n import format_date, format_number

format_date(date(2025, 3, 15), "de")      # → "15. March 2025"
format_date(date(2025, 3, 15), "de", short=True)  # → "15.03.2025"
format_number(1234567, "de")                # → "1.234.567"
format_number(1234.56, "en")                # → "1,234.56"
```

### Adding a New Translation Key

1. Add the key and English text to `frontend/translations/en.json`
2. Add translations for all other languages in their respective files
3. Use `{{ _("your.new.key") }}` in templates

### Translation Integrity Gate

DocuElevate treats translation completeness as a required quality gate:

```bash
# Fast validation for translation file hygiene
python -m pytest tests/test_i18n.py::TestTranslationFiles -q -o addopts=

# Equivalent pre-commit hook
pre-commit run translation-integrity --all-files
```

The translation integrity checks enforce that:

- every supported locale file exists
- every locale has the exact same keys as `en.json`
- every locale preserves the same placeholders as English

When you remove or rename a key, update **all** locale files in the same PR so
no locale-specific orphan keys remain.

### AI Fallback Translation

When a translation key exists in English but not in the target language,
DocuElevate can use the configured AI provider (OpenAI, Anthropic, etc.)
to translate the string on-the-fly:

```python
from app.utils.i18n import translate_with_ai_fallback

# Falls back to AI if no manual translation exists
translated = translate_with_ai_fallback("Welcome to our platform", "de")
```

The AI fallback:
- Uses the `AI_MODEL` or `OPENAI_MODEL` setting
- Caches results in memory for the process lifetime
- Returns the original English text if the AI call fails
- Is designed for graceful degradation — the UI never breaks

### Adding a New Language

1. Create a new JSON file in `frontend/translations/` (e.g., `ja.json`)
2. Copy the structure from `en.json` and translate all values
3. Add the language to `SUPPORTED_LANGUAGES` in `app/utils/i18n.py`:
   ```python
   {"code": "ja", "name": "Japanese", "native": "日本語", "flag": "🇯🇵"},
   ```
4. Add locale formatting rules to `_LOCALE_FORMATS` in the same file
5. Create a database migration if needed (the `preferred_language` column
   already accepts any string up to 10 characters)

### Database Migration

Migration `027_add_user_language_preference` adds a `preferred_language`
column to the `user_profiles` table. This column stores the user's chosen
UI language as an ISO 639-1 code (e.g., `"de"`, `"fr"`). A `NULL` value
means "auto-detect from browser settings."

### API Reference

#### `GET /api/i18n/languages`

Returns all supported languages and the current active language.

**Response:**
```json
{
  "languages": [
    {"code": "en", "name": "English", "native": "English", "flag": "🇬🇧"},
    {"code": "de", "name": "German", "native": "Deutsch", "flag": "🇩🇪"}
  ],
  "current": "en",
  "default": "en"
}
```

#### `POST /api/i18n/language`

Set the preferred UI language. Persists in session, cookie, and database.

**Request:**
```json
{"language": "de"}
```

**Response:**
```json
{
  "language": "de",
  "message": "Language changed to Deutsch"
}
```

## Configuration

No additional configuration is required. The i18n system works out of the box
with the default English language and automatically detects browser preferences.

| Setting | Default | Description |
|---------|---------|-------------|
| Browser `Accept-Language` | Auto-detected | Used when no explicit preference is set |
| `docuelevate_lang` cookie | Not set | Set when user selects a language via the UI |
| `UserProfile.preferred_language` | `NULL` | Stored in DB for authenticated users |
