"""
Dynamic suggestion providers for autocomplete-enabled settings.

Each provider function returns a list of strings that are valid values
for a particular setting.  Providers try to resolve values dynamically
(e.g. by querying cloud SDKs or scanning installed software) and fall
back to curated static lists when the runtime environment lacks the
required libraries, credentials, or connectivity.

**Fallback guarantee**: Every provider wraps its dynamic resolution in a
``try/except Exception`` so that it *always* returns a usable list.
Missing libraries (``ImportError``), missing credentials, network
failures, or unexpected SDK errors all trigger a graceful fallback to
the bundled static list.
"""

import logging
import subprocess  # noqa: S404 — only used with fixed args, no user input

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AWS regions — fetched from boto3 if available
# ---------------------------------------------------------------------------

_AWS_REGIONS_STATIC: list[str] = [
    "af-south-1",
    "ap-east-1",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ca-central-1",
    "ca-west-1",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "il-central-1",
    "me-central-1",
    "me-south-1",
    "sa-east-1",
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
]


def get_aws_regions() -> list[str]:
    """Return available AWS S3 regions via boto3, falling back to a static list."""
    try:
        import boto3  # noqa: PLC0415

        session = boto3.session.Session()
        regions = sorted(session.get_available_regions("s3"))
        if regions:
            return regions
    except Exception:
        logger.debug("boto3 not available or failed; using static AWS region list")
    return _AWS_REGIONS_STATIC


# ---------------------------------------------------------------------------
# Azure regions — resolved from known Cognitive Services locations
# ---------------------------------------------------------------------------

_AZURE_REGIONS_STATIC: list[str] = [
    "australiacentral",
    "australiaeast",
    "australiasoutheast",
    "brazilsouth",
    "canadacentral",
    "canadaeast",
    "centralindia",
    "centralus",
    "eastasia",
    "eastus",
    "eastus2",
    "francecentral",
    "germanywestcentral",
    "japaneast",
    "japanwest",
    "koreacentral",
    "koreasouth",
    "northcentralus",
    "northeurope",
    "norwayeast",
    "polandcentral",
    "qatarcentral",
    "southafricanorth",
    "southcentralus",
    "southeastasia",
    "swedencentral",
    "switzerlandnorth",
    "uaenorth",
    "uksouth",
    "ukwest",
    "westcentralus",
    "westeurope",
    "westus",
    "westus2",
    "westus3",
]


def get_azure_regions() -> list[str]:
    """Return Azure Cognitive Services regions.

    Falls back to a curated static list because there is no
    unauthenticated public endpoint to enumerate regions.
    """
    return _AZURE_REGIONS_STATIC


# ---------------------------------------------------------------------------
# Tesseract languages — probed from `tesseract --list-langs`
# ---------------------------------------------------------------------------

_TESSERACT_LANGS_STATIC: list[str] = [
    "afr",
    "amh",
    "ara",
    "asm",
    "aze",
    "bel",
    "ben",
    "bod",
    "bos",
    "bre",
    "bul",
    "cat",
    "ceb",
    "ces",
    "chi_sim",
    "chi_tra",
    "chr",
    "cos",
    "cym",
    "dan",
    "deu",
    "div",
    "ell",
    "eng",
    "enm",
    "epo",
    "est",
    "eus",
    "fao",
    "fas",
    "fil",
    "fin",
    "fra",
    "frk",
    "frm",
    "fry",
    "gla",
    "gle",
    "glg",
    "grc",
    "guj",
    "hat",
    "heb",
    "hin",
    "hrv",
    "hun",
    "hye",
    "iku",
    "ind",
    "isl",
    "ita",
    "jav",
    "jpn",
    "kan",
    "kat",
    "kaz",
    "khm",
    "kir",
    "kor",
    "lao",
    "lat",
    "lav",
    "lit",
    "ltz",
    "mal",
    "mar",
    "mkd",
    "mlt",
    "mon",
    "mri",
    "msa",
    "mya",
    "nep",
    "nld",
    "nor",
    "oci",
    "ori",
    "pan",
    "pol",
    "por",
    "pus",
    "que",
    "ron",
    "rus",
    "san",
    "sin",
    "slk",
    "slv",
    "snd",
    "spa",
    "sqi",
    "srp",
    "sun",
    "swa",
    "swe",
    "syr",
    "tam",
    "tat",
    "tel",
    "tgk",
    "tha",
    "tir",
    "ton",
    "tur",
    "uig",
    "ukr",
    "urd",
    "uzb",
    "vie",
    "yid",
    "yor",
]


def get_tesseract_languages() -> list[str]:
    """Return installed Tesseract language codes, falling back to a static list."""
    try:
        result = subprocess.run(  # noqa: S603, S607
            ["tesseract", "--list-langs"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # First line is the header ("List of available languages ...")
            langs = sorted(line.strip() for line in lines[1:] if line.strip())
            if langs:
                return langs
    except Exception:
        logger.debug("tesseract not available; using static language list")
    return _TESSERACT_LANGS_STATIC


# ---------------------------------------------------------------------------
# EasyOCR languages — probed from the easyocr module
# ---------------------------------------------------------------------------

_EASYOCR_LANGS_STATIC: list[str] = [
    "abq",
    "ady",
    "af",
    "ang",
    "ar",
    "as",
    "ava",
    "az",
    "be",
    "bg",
    "bh",
    "bn",
    "bs",
    "ch_sim",
    "ch_tra",
    "che",
    "cs",
    "cy",
    "da",
    "dar",
    "de",
    "en",
    "es",
    "et",
    "fa",
    "fi",
    "fr",
    "ga",
    "gom",
    "hi",
    "hr",
    "hu",
    "id",
    "inh",
    "is",
    "it",
    "ja",
    "ka",
    "kk",
    "km",
    "kn",
    "ko",
    "ku",
    "la",
    "lbe",
    "lez",
    "lt",
    "lv",
    "mah",
    "mai",
    "mi",
    "mn",
    "mr",
    "ms",
    "mt",
    "ne",
    "new",
    "nl",
    "no",
    "oc",
    "pi",
    "pl",
    "pt",
    "ro",
    "ru",
    "rs_cyrillic",
    "rs_latin",
    "sa",
    "sck",
    "sk",
    "sl",
    "sq",
    "sv",
    "sw",
    "ta",
    "tab",
    "te",
    "th",
    "tjk",
    "tl",
    "tr",
    "ug",
    "uk",
    "ur",
    "uz",
    "vi",
]


def get_easyocr_languages() -> list[str]:
    """Return supported EasyOCR language codes, falling back to a static list."""
    try:
        import easyocr  # noqa: PLC0415

        # easyocr stores the language list internally
        if hasattr(easyocr, "config") and hasattr(easyocr.config, "all_lang_list"):
            return sorted(easyocr.config.all_lang_list)
    except Exception:
        logger.debug("easyocr not available; using static language list")
    return _EASYOCR_LANGS_STATIC


# ---------------------------------------------------------------------------
# Embedding models — static list (no standard discovery API)
# ---------------------------------------------------------------------------

_EMBEDDING_MODELS: list[str] = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
    "nomic-embed-text",
    "nomic-embed-text-v1.5",
    "mxbai-embed-large",
    "mxbai-embed-large-v1",
    "all-MiniLM-L6-v2",
    "all-MiniLM-L12-v2",
    "bge-small-en-v1.5",
    "bge-base-en-v1.5",
    "bge-large-en-v1.5",
    "e5-small-v2",
    "e5-base-v2",
    "e5-large-v2",
    "gte-small",
    "gte-base",
    "gte-large",
    "voyage-3",
    "voyage-3-lite",
    "voyage-code-3",
]


def get_embedding_models() -> list[str]:
    """Return known embedding model names."""
    return _EMBEDDING_MODELS


# ---------------------------------------------------------------------------
# Registry — maps setting keys to their provider functions
# ---------------------------------------------------------------------------

SUGGESTION_PROVIDERS: dict[str, callable] = {
    "aws_region": get_aws_regions,
    "azure_region": get_azure_regions,
    "tesseract_language": get_tesseract_languages,
    "easyocr_languages": get_easyocr_languages,
    "embedding_model": get_embedding_models,
}


def get_suggestions(key: str, query: str = "", limit: int = 10) -> list[str]:
    """
    Return autocomplete suggestions for the given setting key.

    Fetches the full list from the registered provider, filters by
    case-insensitive substring match on *query*, and returns at most
    *limit* results.

    Args:
        key: The setting key (must be registered in SUGGESTION_PROVIDERS).
        query: Substring to filter by (case-insensitive).
        limit: Maximum number of results to return.

    Returns:
        Filtered list of suggestion strings.

    Raises:
        KeyError: If no provider is registered for *key*.
    """
    provider = SUGGESTION_PROVIDERS.get(key)
    if provider is None:
        raise KeyError(f"No suggestion provider registered for setting '{key}'")

    all_values = provider()
    q = query.strip().lower()

    if q:
        filtered = [v for v in all_values if q in v.lower()]
    else:
        filtered = list(all_values)

    return filtered[:limit]
