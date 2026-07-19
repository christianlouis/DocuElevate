"""Explainable, Tribe-scoped recipient classification.

Deterministic signals decide first.  An administrator may enable a bounded AI
fallback for ambiguous documents; AI output can only select known active
profiles and therefore cannot cross a Tribe boundary.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.models import (
    DocumentRecipientDecision,
    FileRecord,
    RecipientIdentityProfile,
    RecipientRoutingPolicy,
    TribeMembership,
)

logger = logging.getLogger(__name__)
CLASSIFIER_VERSION = "recipient-v1"
_MAX_AI_CONTEXT_CHARS = 6000
_MAX_AI_PROFILES = 100


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.sub(r"[^\w@.+-]+", " ", text).split())


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and (haystack == needle or f" {needle} " in f" {haystack} ")


@dataclass(frozen=True)
class RecipientResult:
    status: str
    recipient_user_ids: list[str]
    matched_profile_ids: list[int]
    candidates: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    confidence: int
    strategy: str = "deterministic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recipient_user_ids": self.recipient_user_ids,
            "matched_profile_ids": self.matched_profile_ids,
            "candidates": self.candidates,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "classifier_version": CLASSIFIER_VERSION,
        }


def _score_profile(profile: RecipientIdentityProfile, recipient_text: str, document_text: str) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []

    def add(field: str, value: Any, score: int, *, target: str) -> None:
        needle = _normalise(value)
        haystack = recipient_text if target == "recipient" else document_text
        if _contains(haystack, needle):
            signals.append({"field": field, "value": str(value), "score": score, "target": target})

    for value in _json_list(profile.identifiers):
        add("identifier", value, 100, target="document")
    for value in _json_list(profile.email_addresses):
        add("email", value, 98, target="document")
    for value in _json_list(profile.postal_addresses):
        add("postal_address", value, 92, target="document")
    for value in [profile.display_name, *_json_list(profile.aliases)]:
        add("name", value, 90, target="recipient")
        add("name_in_text", value, 68, target="document")

    strongest = max((item["score"] for item in signals), default=0)
    return {
        "profile_id": profile.id,
        "display_name": profile.display_name,
        "profile_type": profile.profile_type,
        "user_ids": [str(value) for value in _json_list(profile.user_ids) if str(value).strip()],
        "score": strongest,
        "signals": signals,
    }


def _deterministic_result(
    profiles: Iterable[RecipientIdentityProfile],
    *,
    metadata: dict[str, Any],
    text: str,
    policy: RecipientRoutingPolicy,
) -> RecipientResult:
    recipient = metadata.get("empfaenger") or metadata.get("recipient") or metadata.get("recipient_name") or ""
    recipient_text = _normalise(recipient)
    document_text = _normalise(" ".join(str(value) for value in metadata.values()) + " " + (text or ""))
    candidates = sorted(
        (_score_profile(profile, recipient_text, document_text) for profile in profiles),
        key=lambda item: (-item["score"], item["profile_id"]),
    )
    candidates = [item for item in candidates if item["score"] > 0]
    if not candidates:
        return RecipientResult("unmatched", [], [], [], [], 0)

    matched = [item for item in candidates if item["score"] >= policy.auto_assign_threshold]
    top_score = candidates[0]["score"]
    if matched:
        # Explicit joint addressees and household labels intentionally yield a
        # set.  A weak incidental mention cannot join a strong recipient hit.
        matched = [item for item in matched if top_score - item["score"] <= policy.minimum_margin]
        user_ids = sorted({user_id for item in matched for user_id in item["user_ids"]})
        status = "matched" if user_ids else "ambiguous"
        return RecipientResult(
            status,
            user_ids,
            [item["profile_id"] for item in matched],
            candidates,
            [signal | {"profile_id": item["profile_id"]} for item in matched for signal in item["signals"]],
            top_score,
        )

    status = "ambiguous" if top_score >= policy.review_threshold else "unmatched"
    return RecipientResult(status, [], [], candidates, candidates[0]["signals"], top_score)


def _default_ai_resolver(prompt: str, model: str) -> dict[str, Any]:
    from app.utils.ai_provider import get_ai_provider

    response = get_ai_provider().chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "Select every recipient profile explicitly addressed by the document. "
                    'Return JSON only: {"profile_ids":[1],"confidence":0-100,"reason":"short"}.'
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
    )
    payload = json.loads(response)
    return payload if isinstance(payload, dict) else {}


def classify_recipient(
    db: Session,
    file_record: FileRecord,
    metadata: dict[str, Any] | None,
    text: str | None,
    *,
    ai_resolver: Callable[[str, str], dict[str, Any]] | None = None,
) -> RecipientResult:
    """Classify a file without ever considering profiles outside its Tribe."""
    profiles = (
        db.query(RecipientIdentityProfile)
        .filter(
            RecipientIdentityProfile.tenant_id == file_record.tenant_id,
            RecipientIdentityProfile.tribe_id == file_record.tribe_id,
            RecipientIdentityProfile.is_active.is_(True),
        )
        .order_by(RecipientIdentityProfile.id.asc())
        .all()
    )
    policy = db.query(RecipientRoutingPolicy).filter_by(tribe_id=file_record.tribe_id).first()
    if policy is None:
        policy = RecipientRoutingPolicy(
            tenant_id=file_record.tenant_id,
            tribe_id=file_record.tribe_id,
            auto_assign_threshold=80,
            review_threshold=45,
            minimum_margin=15,
            ai_fallback_enabled=False,
            updated_by=file_record.owner_id or "system",
        )

    result = _deterministic_result(profiles, metadata=metadata or {}, text=text or "", policy=policy)
    if result.status == "matched" or not policy.ai_fallback_enabled or not profiles or not policy.ai_model:
        return result

    resolver = ai_resolver or _default_ai_resolver
    # Keep the optional fallback deliberately small. Metadata may contain
    # arbitrary provider payloads, so only recipient-relevant scalar fields
    # enter the prompt and every value is bounded.
    safe_metadata = {
        key: str((metadata or {}).get(key, ""))[:1000]
        for key in ("empfaenger", "recipient", "recipient_name", "sender", "title", "filename")
        if (metadata or {}).get(key)
    }
    fallback_profiles = profiles[:_MAX_AI_PROFILES]
    prompt = json.dumps(
        {
            "profiles": [
                {
                    "id": profile.id,
                    "name": profile.display_name[:255],
                    "aliases": [str(alias)[:255] for alias in _json_list(profile.aliases)[:10]],
                }
                for profile in fallback_profiles
            ],
            "metadata": safe_metadata,
            "document_excerpt": (text or "")[:_MAX_AI_CONTEXT_CHARS],
        },
        ensure_ascii=False,
    )
    try:
        ai_payload = resolver(prompt, policy.ai_model)
    except Exception as exc:
        logger.warning("Recipient AI fallback failed for file %s: %s", file_record.id, exc)
        return result

    allowed_profiles = {profile.id: profile for profile in fallback_profiles}
    selected_ids = sorted(
        {
            int(profile_id)
            for profile_id in ai_payload.get("profile_ids", [])
            if str(profile_id).isdigit() and int(profile_id) in allowed_profiles
        }
    )
    member_ids = {
        row.user_id for row in db.query(TribeMembership).filter(TribeMembership.tribe_id == file_record.tribe_id).all()
    }
    selected_users = sorted(
        {
            str(user_id)
            for profile_id in selected_ids
            for user_id in _json_list(allowed_profiles[profile_id].user_ids)
            if str(user_id) in member_ids
        }
    )
    confidence = max(0, min(100, int(ai_payload.get("confidence", 0) or 0)))
    if not selected_users or confidence < policy.auto_assign_threshold:
        return result
    return RecipientResult(
        "matched",
        selected_users,
        selected_ids,
        result.candidates,
        [{"field": "ai_fallback", "reason": str(ai_payload.get("reason", ""))[:500]}],
        confidence,
        "ai_fallback",
    )


def classify_and_persist_recipient(
    db: Session,
    file_record: FileRecord,
    metadata: dict[str, Any] | None,
    text: str | None,
) -> DocumentRecipientDecision:
    """Classify and upsert the explainable decision in the caller's transaction."""
    result = classify_recipient(db, file_record, metadata, text)
    decision = db.query(DocumentRecipientDecision).filter_by(file_id=file_record.id).first()
    if decision is None:
        decision = DocumentRecipientDecision(
            file_id=file_record.id,
            tenant_id=file_record.tenant_id,
            tribe_id=file_record.tribe_id,
        )
        db.add(decision)
    decision.status = result.status
    decision.recipient_user_ids = json.dumps(result.recipient_user_ids)
    decision.matched_profile_ids = json.dumps(result.matched_profile_ids)
    decision.candidates = json.dumps(result.candidates, ensure_ascii=False)
    decision.evidence = json.dumps(result.evidence, ensure_ascii=False)
    decision.confidence = result.confidence
    decision.strategy = result.strategy
    decision.classifier_version = CLASSIFIER_VERSION
    db.flush()
    return decision
