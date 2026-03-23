"""Tests for the document comments and annotations API."""

import pytest

from app.models import DocumentAnnotation, DocumentComment, FileRecord, UserProfile


def _create_file(db_session, owner_id="testuser") -> FileRecord:
    """Helper to create a minimal FileRecord for testing."""
    f = FileRecord(
        owner_id=owner_id,
        filehash="abc123",
        original_filename="test.pdf",
        local_filename="test.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


# ---------------------------------------------------------------------------
# Comment tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListComments:
    """Tests for GET /api/files/{file_id}/comments."""

    def test_list_comments_empty(self, client, db_session):
        f = _create_file(db_session)
        resp = client.get(f"/api/files/{f.id}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_id"] == f.id
        assert data["comments"] == []
        assert data["total"] == 0

    def test_list_comments_file_not_found(self, client):
        resp = client.get("/api/files/99999/comments")
        assert resp.status_code == 404

    def test_list_comments_threaded(self, client, db_session):
        f = _create_file(db_session)
        # Root comment
        c1 = DocumentComment(file_id=f.id, user_id="alice", body="Hello")
        db_session.add(c1)
        db_session.commit()
        db_session.refresh(c1)
        # Reply
        c2 = DocumentComment(file_id=f.id, user_id="bob", parent_id=c1.id, body="Hi back")
        db_session.add(c2)
        db_session.commit()

        resp = client.get(f"/api/files/{f.id}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["comments"]) == 1  # only root
        assert len(data["comments"][0]["replies"]) == 1
        assert data["comments"][0]["replies"][0]["body"] == "Hi back"


@pytest.mark.unit
class TestCreateComment:
    """Tests for POST /api/files/{file_id}/comments."""

    def test_create_comment(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "Great document!"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == "Great document!"
        assert data["file_id"] == f.id
        assert data["parent_id"] is None

    def test_create_comment_with_mention(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "Hey @alice please review"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["mentions"] == ["alice"]

    def test_create_comment_with_parent(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="user1", body="root")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "reply", "parent_id": c.id},
        )
        assert resp.status_code == 201
        assert resp.json()["parent_id"] == c.id

    def test_create_comment_parent_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "reply", "parent_id": 99999},
        )
        assert resp.status_code == 404

    def test_create_comment_empty_body(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "   "},
        )
        assert resp.status_code == 422

    def test_create_comment_file_not_found(self, client):
        resp = client.post(
            "/api/files/99999/comments",
            json={"body": "test"},
        )
        assert resp.status_code == 404

    def test_create_comment_body_too_long(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "x" * 10_001},
        )
        assert resp.status_code == 422


@pytest.mark.unit
class TestUpdateComment:
    """Tests for PUT /api/files/{file_id}/comments/{comment_id}."""

    def test_update_comment(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="anonymous", body="old body")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.put(
            f"/api/files/{f.id}/comments/{c.id}",
            json={"body": "new body @bob"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["body"] == "new body @bob"
        assert data["mentions"] == ["bob"]

    def test_update_comment_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.put(
            f"/api/files/{f.id}/comments/99999",
            json={"body": "new"},
        )
        assert resp.status_code == 404

    def test_update_comment_forbidden(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="other_user", body="old")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.put(
            f"/api/files/{f.id}/comments/{c.id}",
            json={"body": "new"},
        )
        assert resp.status_code == 403


@pytest.mark.unit
class TestDeleteComment:
    """Tests for DELETE /api/files/{file_id}/comments/{comment_id}."""

    def test_delete_comment(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="anonymous", body="to delete")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.delete(f"/api/files/{f.id}/comments/{c.id}")
        assert resp.status_code == 204

        # Verify deleted
        assert db_session.query(DocumentComment).filter(DocumentComment.id == c.id).first() is None

    def test_delete_comment_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.delete(f"/api/files/{f.id}/comments/99999")
        assert resp.status_code == 404

    def test_delete_comment_forbidden(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="other_user", body="mine")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.delete(f"/api/files/{f.id}/comments/{c.id}")
        assert resp.status_code == 403


@pytest.mark.unit
class TestResolveComment:
    """Tests for PATCH /api/files/{file_id}/comments/{comment_id}/resolve."""

    def test_resolve_comment(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="anonymous", body="issue")
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.patch(
            f"/api/files/{f.id}/comments/{c.id}/resolve",
            json={"is_resolved": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_resolved"] is True

    def test_unresolve_comment(self, client, db_session):
        f = _create_file(db_session)
        c = DocumentComment(file_id=f.id, user_id="anonymous", body="issue", is_resolved=True)
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)

        resp = client.patch(
            f"/api/files/{f.id}/comments/{c.id}/resolve",
            json={"is_resolved": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_resolved"] is False

    def test_resolve_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.patch(
            f"/api/files/{f.id}/comments/99999/resolve",
            json={"is_resolved": True},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Annotation tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListAnnotations:
    """Tests for GET /api/files/{file_id}/annotations."""

    def test_list_annotations_empty(self, client, db_session):
        f = _create_file(db_session)
        resp = client.get(f"/api/files/{f.id}/annotations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_id"] == f.id
        assert data["annotations"] == []
        assert data["total"] == 0

    def test_list_annotations_file_not_found(self, client):
        resp = client.get("/api/files/99999/annotations")
        assert resp.status_code == 404


@pytest.mark.unit
class TestCreateAnnotation:
    """Tests for POST /api/files/{file_id}/annotations."""

    def test_create_annotation(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={
                "page": 1,
                "x": 100.0,
                "y": 200.0,
                "content": "Important note",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["page"] == 1
        assert data["x"] == 100.0
        assert data["y"] == 200.0
        assert data["content"] == "Important note"
        assert data["annotation_type"] == "note"

    def test_create_annotation_with_all_fields(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={
                "page": 2,
                "x": 50.0,
                "y": 100.0,
                "width": 200.0,
                "height": 30.0,
                "content": "Highlighted text",
                "annotation_type": "highlight",
                "color": "#ffff00",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["annotation_type"] == "highlight"
        assert data["color"] == "#ffff00"
        assert data["width"] == 200.0
        assert data["height"] == 30.0

    def test_create_annotation_file_not_found(self, client):
        resp = client.post(
            "/api/files/99999/annotations",
            json={"page": 1, "x": 0, "y": 0, "content": "test"},
        )
        assert resp.status_code == 404

    def test_create_annotation_empty_content(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={"page": 1, "x": 0, "y": 0, "content": "   "},
        )
        assert resp.status_code == 422

    def test_create_annotation_invalid_page(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={"page": 0, "x": 0, "y": 0, "content": "test"},
        )
        assert resp.status_code == 422

    def test_create_annotation_invalid_type(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={"page": 1, "x": 0, "y": 0, "content": "test", "annotation_type": "invalid"},
        )
        assert resp.status_code == 422

    def test_create_annotation_content_too_long(self, client, db_session):
        f = _create_file(db_session)
        resp = client.post(
            f"/api/files/{f.id}/annotations",
            json={"page": 1, "x": 0, "y": 0, "content": "x" * 5_001},
        )
        assert resp.status_code == 422


@pytest.mark.unit
class TestUpdateAnnotation:
    """Tests for PUT /api/files/{file_id}/annotations/{annotation_id}."""

    def test_update_annotation(self, client, db_session):
        f = _create_file(db_session)
        a = DocumentAnnotation(file_id=f.id, user_id="anonymous", page=1, x=0, y=0, width=0, height=0, content="old")
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)

        resp = client.put(
            f"/api/files/{f.id}/annotations/{a.id}",
            json={"content": "updated note", "color": "#00ff00"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "updated note"
        assert data["color"] == "#00ff00"

    def test_update_annotation_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.put(
            f"/api/files/{f.id}/annotations/99999",
            json={"content": "new"},
        )
        assert resp.status_code == 404

    def test_update_annotation_forbidden(self, client, db_session):
        f = _create_file(db_session)
        a = DocumentAnnotation(file_id=f.id, user_id="other_user", page=1, x=0, y=0, width=0, height=0, content="mine")
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)

        resp = client.put(
            f"/api/files/{f.id}/annotations/{a.id}",
            json={"content": "hijack"},
        )
        assert resp.status_code == 403

    def test_update_annotation_invalid_type(self, client, db_session):
        f = _create_file(db_session)
        a = DocumentAnnotation(file_id=f.id, user_id="anonymous", page=1, x=0, y=0, width=0, height=0, content="old")
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)

        resp = client.put(
            f"/api/files/{f.id}/annotations/{a.id}",
            json={"annotation_type": "invalid"},
        )
        assert resp.status_code == 422


@pytest.mark.unit
class TestDeleteAnnotation:
    """Tests for DELETE /api/files/{file_id}/annotations/{annotation_id}."""

    def test_delete_annotation(self, client, db_session):
        f = _create_file(db_session)
        a = DocumentAnnotation(
            file_id=f.id, user_id="anonymous", page=1, x=0, y=0, width=0, height=0, content="to delete"
        )
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)

        resp = client.delete(f"/api/files/{f.id}/annotations/{a.id}")
        assert resp.status_code == 204
        assert db_session.query(DocumentAnnotation).filter(DocumentAnnotation.id == a.id).first() is None

    def test_delete_annotation_not_found(self, client, db_session):
        f = _create_file(db_session)
        resp = client.delete(f"/api/files/{f.id}/annotations/99999")
        assert resp.status_code == 404

    def test_delete_annotation_forbidden(self, client, db_session):
        f = _create_file(db_session)
        a = DocumentAnnotation(file_id=f.id, user_id="other_user", page=1, x=0, y=0, width=0, height=0, content="mine")
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)

        resp = client.delete(f"/api/files/{f.id}/annotations/{a.id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Mentionable users tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListMentionableUsers:
    """Tests for GET /api/users/mentionable."""

    def test_list_mentionable_empty(self, client, db_session):
        resp = client.get("/api/users/mentionable")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_mentionable_users(self, client, db_session):
        p1 = UserProfile(user_id="alice", display_name="Alice A")
        p2 = UserProfile(user_id="bob", display_name="Bob B")
        db_session.add_all([p1, p2])
        db_session.commit()

        resp = client.get("/api/users/mentionable")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["user_id"] == "alice"
        assert data[1]["user_id"] == "bob"

    def test_blocked_users_excluded(self, client, db_session):
        p1 = UserProfile(user_id="alice", display_name="Alice A", is_blocked=False)
        p2 = UserProfile(user_id="blocked", display_name="Blocked", is_blocked=True)
        db_session.add_all([p1, p2])
        db_session.commit()

        resp = client.get("/api/users/mentionable")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "alice"


# ---------------------------------------------------------------------------
# Mention extraction helper tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractMentions:
    """Tests for the _extract_mentions helper function."""

    def test_no_mentions(self):
        from app.api.comments import _extract_mentions

        assert _extract_mentions("Hello world") == []

    def test_single_mention(self):
        from app.api.comments import _extract_mentions

        assert _extract_mentions("Hey @alice check this") == ["alice"]

    def test_multiple_mentions(self):
        from app.api.comments import _extract_mentions

        assert _extract_mentions("@alice @bob @charlie") == ["alice", "bob", "charlie"]

    def test_duplicate_mentions(self):
        from app.api.comments import _extract_mentions

        result = _extract_mentions("@alice and @alice again")
        assert result == ["alice"]

    def test_mention_with_dots_and_dashes(self):
        from app.api.comments import _extract_mentions

        result = _extract_mentions("@user.name @user-name")
        assert result == ["user.name", "user-name"]
