"""Acceptance-oriented checks for the Family & Teams browser journey."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE = _ROOT / "frontend/templates/tribes.html"


@pytest.mark.integration
def test_tribes_page_renders_as_self_service_journey(client):
    response = client.get("/tribes")

    assert response.status_code == 200
    assert "Family &amp; Teams" in response.text
    assert "One tenant, owner-controlled privacy" in response.text
    assert "/api/tribes/invitations/accept" in response.text


@pytest.mark.unit
def test_invitation_secret_uses_fragment_and_is_never_put_in_query_string():
    template = _TEMPLATE.read_text(encoding="utf-8")

    assert "/tribes#invite=" in template
    assert "/tribes?invite=" not in template
    assert "window.location.hash.match" in template
    assert "window.history.replaceState" in template


@pytest.mark.unit
def test_tribe_ui_uses_safe_text_binding_for_server_values():
    template = _TEMPLATE.read_text(encoding="utf-8")

    assert 'x-text="tribe.name"' in template
    assert 'x-text="member.user_id"' in template
    assert 'x-text="invitation.invitee_id"' in template
    assert "innerHTML" not in template


@pytest.mark.unit
def test_tribe_journey_exposes_membership_consent_and_owner_privacy_boundary():
    template = _TEMPLATE.read_text(encoding="utf-8")

    required_keys = {
        "tribes.boundary_body",
        "tribes.invite_consent",
        "tribes.invite_member_help",
        "tribes.link_once_help",
        "tribes.remove_confirm",
    }
    assert required_keys.issubset(set(re.findall(r'["\'](tribes\.[a-z0-9_]+)["\']', template)))


@pytest.mark.unit
def test_tribe_copy_is_complete_in_english_and_german():
    template = _TEMPLATE.read_text(encoding="utf-8")
    keys = set(re.findall(r'["\'](tribes\.[a-z0-9_]+)["\']', template))
    keys.add("nav.tribes")

    assert keys
    for locale in ("en", "de"):
        translations = json.loads((_ROOT / f"frontend/translations/{locale}.json").read_text(encoding="utf-8"))
        missing = sorted(keys - translations.keys())
        assert not missing, f"Missing {locale} Tribe translations: {missing}"


@pytest.mark.unit
def test_account_menu_links_to_family_and_teams_on_desktop_and_mobile():
    script = (_ROOT / "frontend/static/js/common.js").read_text(encoding="utf-8")

    assert script.count("'/tribes'") == 2
    assert "window.__i18n.tribes" in script
