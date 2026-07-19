"""Integration tests for tenant-safe Tribe invitations and membership roles."""

from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from app.models import Tribe, TribeInvitation, TribeMembership
from app.utils.tribe_scope import ensure_personal_scope, ensure_tribe_membership, shared_tribe_id


def _session(user: dict):
    return patch(
        "starlette.requests.Request.session",
        new_callable=lambda: property(lambda self: {"user": user}),
    )


def _shared_tribe(db_session, *, admin_id: str = "admin", name: str = "Family Krakau") -> Tribe:
    tenant_id, _personal = ensure_personal_scope(db_session, admin_id)
    tribe = Tribe(id=shared_tribe_id(name, tenant_id), tenant_id=tenant_id, name=name)
    db_session.add(tribe)
    db_session.flush()
    ensure_tribe_membership(
        db_session,
        tenant_id=tenant_id,
        tribe_id=tribe.id,
        user_id=admin_id,
        role="admin",
    )
    db_session.commit()
    return tribe


@pytest.mark.integration
class TestTribeInvitations:
    def test_invitation_token_is_returned_once_hashed_at_rest_and_accepts_exact_identity(self, client, db_session):
        tribe = _shared_tribe(db_session)
        with _session({"sub": "admin", "email": "admin@example.com"}):
            created = client.post(
                f"/api/tribes/{tribe.id}/invitations",
                json={"invitee_id": "julia@example.com", "role": "routing_manager", "expires_hours": 24},
            )

        assert created.status_code == 201
        token = created.json()["token"]
        invitation = db_session.query(TribeInvitation).one()
        assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert invitation.token_hash != token

        with _session({"sub": "oauth-julia", "email": "julia@example.com"}):
            pending = client.get("/api/tribes/invitations/pending")
            accepted = client.post("/api/tribes/invitations/accept", json={"token": token})
            replay = client.post("/api/tribes/invitations/accept", json={"token": token})

        assert pending.status_code == 200
        assert len(pending.json()) == 1
        assert "token" not in pending.json()[0]
        assert accepted.status_code == 200
        assert accepted.json()["role"] == "routing_manager"
        assert replay.status_code == 404
        membership = db_session.query(TribeMembership).filter_by(tribe_id=tribe.id, user_id="oauth-julia").one()
        assert membership.tenant_id == tribe.tenant_id
        assert membership.role == "routing_manager"

    def test_invitation_cannot_be_accepted_by_a_different_identity(self, client, db_session):
        tribe = _shared_tribe(db_session)
        with _session({"id": "admin"}):
            created = client.post(
                f"/api/tribes/{tribe.id}/invitations",
                json={"invitee_id": "julia@example.com"},
            )
        token = created.json()["token"]

        with _session({"id": "mallory", "email": "mallory@example.com"}):
            response = client.post("/api/tribes/invitations/accept", json={"token": token})

        assert response.status_code == 404
        assert db_session.query(TribeMembership).filter_by(tribe_id=tribe.id, user_id="mallory").count() == 0

    def test_platform_admin_bit_cannot_invite_without_tribe_membership(self, client, db_session):
        tribe = _shared_tribe(db_session, admin_id="alice")
        ensure_personal_scope(db_session, "platform-admin", tribe.tenant_id)
        db_session.commit()

        with _session({"id": "platform-admin", "is_admin": True}):
            response = client.post(
                f"/api/tribes/{tribe.id}/invitations",
                json={"invitee_id": "outsider"},
            )

        assert response.status_code == 404
        assert db_session.query(TribeInvitation).count() == 0

    def test_revoked_invitation_cannot_be_accepted(self, client, db_session):
        tribe = _shared_tribe(db_session)
        with _session({"id": "admin"}):
            created = client.post(
                f"/api/tribes/{tribe.id}/invitations",
                json={"invitee_id": "julia"},
            )
            revoked = client.post(f"/api/tribes/{tribe.id}/invitations/{created.json()['id']}/revoke")

        with _session({"id": "julia"}):
            accepted = client.post(
                "/api/tribes/invitations/accept",
                json={"token": created.json()["token"]},
            )

        assert revoked.status_code == 200
        assert accepted.status_code == 404


@pytest.mark.integration
class TestTribeMembershipAdministration:
    def test_members_can_list_only_their_own_tribes(self, client, db_session):
        family = _shared_tribe(db_session)
        other = _shared_tribe(db_session, admin_id="mallory", name="Other Family")
        ensure_tribe_membership(
            db_session,
            tenant_id=family.tenant_id,
            tribe_id=family.id,
            user_id="julia",
            role="member",
        )
        db_session.commit()

        with _session({"id": "julia"}):
            response = client.get("/api/tribes")

        assert response.status_code == 200
        ids = {item["tribe_id"] for item in response.json()}
        assert family.id in ids
        assert other.id not in ids

    def test_last_admin_cannot_be_demoted_or_removed(self, client, db_session):
        tribe = _shared_tribe(db_session)
        with _session({"id": "admin"}):
            demote = client.patch(
                f"/api/tribes/{tribe.id}/members/admin",
                json={"role": "member"},
            )
            remove = client.delete(f"/api/tribes/{tribe.id}/members/admin")

        assert demote.status_code == 409
        assert remove.status_code == 409

    def test_admin_can_promote_member_then_transfer_administration(self, client, db_session):
        tribe = _shared_tribe(db_session)
        ensure_tribe_membership(
            db_session,
            tenant_id=tribe.tenant_id,
            tribe_id=tribe.id,
            user_id="julia",
            role="member",
        )
        db_session.commit()

        with _session({"id": "admin"}):
            promote = client.patch(
                f"/api/tribes/{tribe.id}/members/julia",
                json={"role": "admin"},
            )
            demote = client.patch(
                f"/api/tribes/{tribe.id}/members/admin",
                json={"role": "member"},
            )

        assert promote.status_code == 200
        assert demote.status_code == 200
        assert _role(db_session, tribe.id, "julia") == "admin"
        assert _role(db_session, tribe.id, "admin") == "member"


def _role(db_session, tribe_id: str, user_id: str) -> str:
    return db_session.query(TribeMembership.role).filter_by(tribe_id=tribe_id, user_id=user_id).scalar()
