"""Canonical file privacy mutations shared by manual and rule workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import FileRecord, PrivacyDecisionAudit, PrivacyRuleModel, SharedLink
from app.utils.privacy_rules import SINGLE_USER_PRIVACY_OWNER, PrivacyMatch, match_rule_to_file

logger = logging.getLogger(__name__)


def apply_privacy_decision(
    db: Session,
    file_record: FileRecord,
    *,
    is_private: bool,
    source: str,
    manual_override: bool | None,
    rule: PrivacyRuleModel | None = None,
    match: PrivacyMatch | None = None,
    decision_owner_id: str | None = None,
) -> int:
    """Set only privacy state, revoke unsafe links, and append an audit row.

    The caller owns the transaction.  Routing and storage fields are not
    accepted as inputs, making accidental reclassification impossible here.
    """
    audit_owner_id = decision_owner_id or file_record.owner_id
    if not audit_owner_id:
        raise ValueError("Privacy decisions require an owned file")

    revoked_links = 0
    if is_private and not file_record.is_private:
        revoked_links = (
            db.query(SharedLink)
            .filter(SharedLink.file_id == file_record.id, SharedLink.is_active.is_(True))
            .update(
                {SharedLink.is_active: False, SharedLink.revoked_at: datetime.now(timezone.utc)},
                synchronize_session="fetch",
            )
        )

    file_record.is_private = is_private
    file_record.privacy_manual_override = manual_override
    db.add(
        PrivacyDecisionAudit(
            file_id=file_record.id,
            owner_id=audit_owner_id,
            rule_id=rule.id if rule else None,
            source=source,
            is_private=is_private,
            policy_version=rule.policy_version if rule else None,
            evidence=match.evidence if match else None,
            confidence=match.confidence if match else None,
        )
    )
    return revoked_links


def queue_privacy_reconciliation(file_ids: list[int]) -> None:
    """Refresh derived search payloads after the database commit."""
    if not file_ids:
        return
    from app.tasks.reconcile_file_privacy import reconcile_file_privacy

    for file_id in file_ids:
        try:
            reconcile_file_privacy.delay(file_id)
        except Exception:
            # Database authorization always reads the canonical flag.  A queue
            # outage may delay search-payload convergence but must not roll
            # back an owner's privacy decision.
            logger.exception("Could not queue privacy-index reconciliation for file %s", file_id)


def apply_first_matching_privacy_rule(db: Session, file_record: FileRecord) -> bool:
    """Mark a newly processed file private when its owner's first rule matches."""
    if file_record.privacy_manual_override is not None:
        return False
    rule_owner_id = file_record.owner_id or SINGLE_USER_PRIVACY_OWNER
    rules = (
        db.query(PrivacyRuleModel)
        .filter(PrivacyRuleModel.owner_id == rule_owner_id, PrivacyRuleModel.enabled.is_(True))
        .order_by(PrivacyRuleModel.priority.desc(), PrivacyRuleModel.id)
        .all()
    )
    for rule in rules:
        match = match_rule_to_file(rule, file_record)
        if match.matched:
            if file_record.is_private:
                return False
            apply_privacy_decision(
                db,
                file_record,
                is_private=True,
                source="rule",
                manual_override=None,
                rule=rule,
                match=match,
                decision_owner_id=rule_owner_id,
            )
            return True
    return False
