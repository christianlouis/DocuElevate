# Internationalization (i18n) & Localization (l10n) Guide

DocuElevate supports **77 languages** for its web UI, with automatic browser
language detection, user-preference persistence, and an AI-powered fallback
translator for strings that haven't been manually translated yet.

## Supported Languages

| Code    | Language           | Native Name        | Flag | Priority |
|---------|--------------------|--------------------|------|----------|
| `en`    | English            | English            | 🇬🇧   | Tier 1   |
| `de`    | German             | Deutsch            | 🇩🇪   | Tier 1   |
| `fr`    | French             | Français           | 🇫🇷   | Tier 1   |
| `es`    | Spanish            | Español            | 🇪🇸   | Tier 1   |
| `it`    | Italian            | Italiano           | 🇮🇹   | Tier 1   |
| `pt`    | Portuguese         | Português          | 🇵🇹   | Tier 1   |
| `nl`    | Dutch              | Nederlands         | 🇳🇱   | Tier 2   |
| `nb`    | Norwegian Bokmål   | Norsk bokmål       | 🇳🇴   | Tier 2   |
| `no`    | Norwegian          | Norsk              | 🇳🇴   | Tier 2   |
| `da`    | Danish             | Dansk              | 🇩🇰   | Tier 2   |
| `sv`    | Swedish            | Svenska            | 🇸🇪   | Tier 2   |
| `fi`    | Finnish            | Suomi              | 🇫🇮   | Tier 2   |
| `is`    | Icelandic          | Íslenska           | 🇮🇸   | Tier 2   |
| `ga`    | Irish              | Gaeilge            | 🇮🇪   | Tier 2   |
| `lb`    | Luxembourgish      | Lëtzebuergesch     | 🇱🇺   | Tier 2   |
| `ca`    | Catalan            | Català             | 🏴    | Tier 2   |
| `cy`    | Welsh              | Cymraeg            | 🏴󠁧󠁢󠁷󠁬󠁳󠁿   | Tier 2   |
| `fy`    | Western Frisian    | Frysk              | 🇳🇱   | Tier 2   |
| `gl`    | Galician           | Galego             | 🇪🇸   | Tier 2   |
| `li`    | Limburgish         | Limburgs           | 🇳🇱   | Tier 2   |
| `vls`   | Flemish            | West-Vlams         | 🇧🇪   | Tier 2   |
| `nds`   | Low German         | Plattdüütsch       | 🇩🇪   | Tier 2   |
| `pl`    | Polish             | Polski             | 🇵🇱   | Tier 3   |
| `cs`    | Czech              | Čeština            | 🇨🇿   | Tier 3   |
| `sk`    | Slovak             | Slovenčina         | 🇸🇰   | Tier 3   |
| `hu`    | Hungarian          | Magyar             | 🇭🇺   | Tier 3   |
| `sl`    | Slovenian          | Slovenščina        | 🇸🇮   | Tier 3   |
| `hr`    | Croatian           | Hrvatski           | 🇭🇷   | Tier 3   |
| `ro`    | Romanian           | Română             | 🇷🇴   | Tier 3   |
| `bg`    | Bulgarian          | Български          | 🇧🇬   | Tier 3   |
| `el`    | Greek              | Ελληνικά           | 🇬🇷   | Tier 3   |
| `et`    | Estonian           | Eesti              | 🇪🇪   | Tier 3   |
| `lv`    | Latvian            | Latviešu           | 🇱🇻   | Tier 3   |
| `lt`    | Lithuanian         | Lietuvių           | 🇱🇹   | Tier 3   |
| `sr`    | Serbian            | Српски             | 🇷🇸   | Tier 3   |
| `tr`    | Turkish            | Türkçe             | 🇹🇷   | Tier 4   |
| `uk`    | Ukrainian          | Українська         | 🇺🇦   | Tier 4   |
| `he`    | Hebrew             | עברית              | 🇮🇱   | Tier 4   |
| `ar`    | Arabic             | العربية            | 🇸🇦   | Tier 4   |
| `fa`    | Persian            | فارسی              | 🇮🇷   | Tier 4   |
| `af`    | Afrikaans          | Afrikaans          | 🇿🇦   | Tier 4   |
| `zh`    | Chinese            | 中文               | 🇨🇳   | Tier 5   |
| `zh-TW` | Traditional Chinese | 繁體中文           | 🇹🇼   | Tier 5   |
| `ja`    | Japanese           | 日本語             | 🇯🇵   | Tier 5   |
| `ko`    | Korean             | 한국어             | 🇰🇷   | Tier 5   |
| `vi`    | Vietnamese         | Tiếng Việt         | 🇻🇳   | Tier 5   |
| `pa`    | Punjabi            | ਪੰਜਾਬੀ             | 🇮🇳   | Tier 5   |
| `kn`    | Kannada            | ಕನ್ನಡ              | 🇮🇳   | Tier 5   |
| `hi`    | Hindi              | हिन्दी             | 🇮🇳   | Tier 5   |
| `bn`    | Bengali            | বাংলা              | 🇧🇩   | Tier 5   |
| `gu`    | Gujarati           | ગુજરાતી            | 🇮🇳   | Tier 5   |
| `ml`    | Malayalam          | മലയാളം             | 🇮🇳   | Tier 5   |
| `mr`    | Marathi            | मराठी              | 🇮🇳   | Tier 5   |
| `ta`    | Tamil              | தமிழ்              | 🇮🇳   | Tier 5   |
| `te`    | Telugu             | తెలుగు             | 🇮🇳   | Tier 5   |
| `ur`    | Urdu               | اردو               | 🇵🇰   | Tier 5   |
| `si`    | Sinhala            | සිංහල              | 🇱🇰   | Tier 5   |
| `ne`    | Nepali             | नेपाली             | 🇳🇵   | Tier 5   |
| `th`    | Thai               | ไทย                | 🇹🇭   | Tier 5   |
| `km`    | Khmer              | ខ្មែរ              | 🇰🇭   | Tier 5   |
| `id`    | Indonesian         | Bahasa Indonesia   | 🇮🇩   | Tier 5   |
| `ms`    | Malay              | Bahasa Melayu      | 🇲🇾   | Tier 5   |
| `jv`    | Javanese           | Basa Jawa          | 🇮🇩   | Tier 5   |
| `tl`    | Tagalog            | Filipino           | 🇵🇭   | Tier 5   |
| `mn`    | Mongolian          | Монгол             | 🇲🇳   | Tier 5   |
| `kk`    | Kazakh             | Қазақ тілі         | 🇰🇿   | Tier 5   |
| `uz`    | Uzbek              | Oʻzbekcha          | 🇺🇿   | Tier 5   |
| `az`    | Azerbaijani        | Azərbaycan dili    | 🇦🇿   | Tier 5   |
| `hy`    | Armenian           | Հայերեն            | 🇦🇲   | Tier 5   |
| `ka`    | Georgian           | ქართული            | 🇬🇪   | Tier 5   |
| `sw`    | Swahili            | Kiswahili          | 🇰🇪   | Tier 6   |
| `am`    | Amharic            | አማርኛ               | 🇪🇹   | Tier 6   |
| `ha`    | Hausa              | Hausa              | 🇳🇬   | Tier 6   |
| `yo`    | Yoruba             | Yorùbá             | 🇳🇬   | Tier 6   |
| `ig`    | Igbo               | Igbo               | 🇳🇬   | Tier 6   |
| `zu`    | Zulu               | isiZulu            | 🇿🇦   | Tier 6   |
| `eo`    | Esperanto          | Esperanto          | 🌍    | Tier 7   |

> **Tier 1** languages (major European) have complete, manually-reviewed
> translations. **Tier 2–3** languages have complete translations but may
> receive less frequent updates. **Tier 4** covers Non-EU European, Middle
> Eastern, and South African (Afrikaans) languages. **Tier 5** covers Asian
> and Central Asian languages. **Tier 6** covers African languages. **Tier 7**
> covers constructed languages.

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
├── af.json    # Afrikaans
├── ar.json    # Arabic
├── bg.json    # Bulgarian
├── ca.json    # Catalan
├── cs.json    # Czech
├── cy.json    # Welsh
├── da.json    # Danish
├── de.json    # German
├── el.json    # Greek
├── eo.json    # Esperanto
├── es.json    # Spanish
├── et.json    # Estonian
├── fa.json    # Persian
├── fi.json    # Finnish
├── fr.json    # French
├── fy.json    # Frisian
├── ga.json    # Irish
├── gl.json    # Galician
├── he.json    # Hebrew
├── hr.json    # Croatian
├── hu.json    # Hungarian
├── is.json    # Icelandic
├── it.json    # Italian
├── ja.json    # Japanese
├── kn.json    # Kannada
├── ko.json    # Korean
├── lb.json    # Luxembourgish
├── li.json    # Limburgish
├── lt.json    # Lithuanian
├── lv.json    # Latvian
├── nb.json    # Norwegian Bokmål
├── nds.json   # Low German (Plattdeutsch)
├── nl.json    # Dutch
├── no.json    # Norwegian
├── pa.json    # Punjabi
├── pl.json    # Polish
├── pt.json    # Portuguese
├── ro.json    # Romanian
├── ru.json    # Russian
├── sk.json    # Slovak
├── sl.json    # Slovenian
├── sr.json    # Serbian
├── sv.json    # Swedish
├── tr.json    # Turkish
├── uk.json    # Ukrainian
├── vi.json    # Vietnamese
├── vls.json   # West Flemish
└── zh.json    # Chinese
```

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
2. Use `{{ _("your.new.key") }}` in templates or `translate("your.new.key", locale)` in Python

That's it. An external automation script picks up new keys in `en.json` and propagates
translations to all other language files. You never need to touch the non-English JSON
files manually — the translate-and-sync pipeline takes care of it.

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
