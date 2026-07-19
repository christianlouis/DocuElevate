"""Deterministic owner privacy-rule matching.

Privacy rules deliberately have one output: whether a document should carry
the canonical ``FileRecord.is_private`` flag.  They never route, move, assign,
or distribute documents.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

RULE_TYPE_FILENAME = "filename_pattern"
RULE_TYPE_CONTENT = "content_keyword"
RULE_TYPE_METADATA = "metadata_match"
VALID_RULE_TYPES = {RULE_TYPE_FILENAME, RULE_TYPE_CONTENT, RULE_TYPE_METADATA}
SINGLE_USER_PRIVACY_OWNER = "__single_user__"


@dataclass(frozen=True)
class PrivacyMatch:
    matched: bool
    evidence: str | None = None
    confidence: int | None = None


def parse_metadata(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def match_privacy_rule(
    *,
    rule_type: str,
    pattern: str,
    case_sensitive: bool,
    filename: str | None,
    text: str | None,
    metadata: dict[str, Any] | None,
) -> PrivacyMatch:
    """Match one structured rule and return minimal owner-only evidence."""
    if rule_type not in VALID_RULE_TYPES:
        return PrivacyMatch(False)

    if rule_type == RULE_TYPE_FILENAME:
        if not filename:
            return PrivacyMatch(False)
        try:
            match = re.search(pattern, filename, 0 if case_sensitive else re.IGNORECASE)
        except re.error:
            return PrivacyMatch(False)
        if match:
            return PrivacyMatch(True, f"filename matched {match.group(0)!r}", 70)
        return PrivacyMatch(False)

    if rule_type == RULE_TYPE_CONTENT:
        haystack = text or ""
        comparable = haystack if case_sensitive else haystack.lower()
        for keyword in (part.strip() for part in pattern.split("|")):
            if keyword and (keyword if case_sensitive else keyword.lower()) in comparable:
                return PrivacyMatch(True, f"content contained {keyword!r}", 80)
        return PrivacyMatch(False)

    if not metadata or "=" not in pattern:
        return PrivacyMatch(False)
    field, expected = (part.strip() for part in pattern.split("=", 1))
    actual = metadata.get(field)
    if actual is None:
        return PrivacyMatch(False)
    actual_text = str(actual)
    matched = actual_text == expected if case_sensitive else actual_text.casefold() == expected.casefold()
    if matched:
        return PrivacyMatch(True, f"metadata {field!r} matched {expected!r}", 95)
    return PrivacyMatch(False)


def match_rule_to_file(rule: Any, file_record: Any) -> PrivacyMatch:
    return match_privacy_rule(
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        case_sensitive=bool(rule.case_sensitive),
        filename=file_record.original_filename,
        text=file_record.ocr_text,
        metadata=parse_metadata(file_record.ai_metadata),
    )
