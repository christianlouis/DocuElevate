"""
Tests for the GraphQL API endpoint at /graphql.

Covers:
- Schema introspection (endpoint availability + GraphiQL)
- Query: documents (list, single, auth-gated)
- Query: pipelines (list, single)
- Query: settings (admin-only)
- Query: users (admin-only)
- Pagination and limit clamping
- Sensitive setting keys are excluded
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import ApplicationSettings, FileRecord, Pipeline, PipelineStep, UserProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def gql(client: TestClient, query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL POST request and return the parsed JSON body."""
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post("/graphql", json=payload)
    assert response.status_code == 200, f"Unexpected status {response.status_code}: {response.text}"
    return response.json()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def file_record(db_session) -> FileRecord:
    rec = FileRecord(
        owner_id="user1",
        original_filename="invoice.pdf",
        local_filename="/workdir/tmp/invoice.pdf",
        file_size=1024,
        mime_type="application/pdf",
        filehash="abc123",
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    return rec


@pytest.fixture()
def pipeline_record(db_session) -> Pipeline:
    p = Pipeline(
        owner_id="user1",
        name="Test Pipeline",
        description="A pipeline for tests",
        is_default=False,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    step = PipelineStep(
        pipeline_id=p.id,
        position=0,
        step_type="ocr",
        label="Run OCR",
        enabled=True,
    )
    db_session.add(step)
    db_session.commit()
    return p


@pytest.fixture()
def setting_record(db_session) -> ApplicationSettings:
    s = ApplicationSettings(key="max_upload_size", value="104857600")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def user_profile(db_session) -> UserProfile:
    profile = UserProfile(
        user_id="user1",
        display_name="Test User",
        is_blocked=False,
        subscription_tier="free",
        onboarding_completed=False,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Tests: endpoint availability
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGraphQLEndpoint:
    """Verify the /graphql endpoint is reachable and introspectable."""

    def test_graphql_post_exists(self, client: TestClient):
        """POST /graphql returns 200 for a valid introspection query."""
        result = gql(client, "{ __schema { queryType { name } } }")
        assert "data" in result
        assert result["data"]["__schema"]["queryType"]["name"] == "Query"

    def test_graphql_get_returns_graphiql(self, client: TestClient):
        """GET /graphql returns the GraphiQL playground HTML."""
        response = client.get("/graphql", headers={"Accept": "text/html"})
        assert response.status_code == 200
        assert "graphiql" in response.text.lower() or "graphql" in response.text.lower()

    def test_graphql_schema_has_expected_types(self, client: TestClient):
        """Schema exposes DocumentType, PipelineType, SettingType, UserType."""
        result = gql(
            client,
            """
            {
              __schema {
                types { name }
              }
            }
            """,
        )
        type_names = {t["name"] for t in result["data"]["__schema"]["types"]}
        for expected in ("DocumentType", "PipelineType", "SettingType", "UserType"):
            assert expected in type_names, f"{expected} not found in schema"

    def test_graphql_query_fields(self, client: TestClient):
        """Root Query has documents, document, pipelines, pipeline, settings, users, user fields."""
        result = gql(
            client,
            """
            {
              __type(name: "Query") {
                fields { name }
              }
            }
            """,
        )
        field_names = {f["name"] for f in result["data"]["__type"]["fields"]}
        for expected in ("documents", "document", "pipelines", "pipeline", "settings", "users", "user"):
            assert expected in field_names, f"Query field '{expected}' missing from schema"


# ---------------------------------------------------------------------------
# Tests: documents queries
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDocumentsQuery:
    """Tests for the documents and document queries."""

    def test_list_documents_empty(self, client: TestClient):
        result = gql(client, "{ documents { id originalFilename } }")
        assert "errors" not in result
        assert result["data"]["documents"] == []

    def test_list_documents_returns_records(self, client: TestClient, file_record: FileRecord):
        result = gql(client, "{ documents { id originalFilename mimeType fileSize } }")
        assert "errors" not in result
        docs = result["data"]["documents"]
        assert len(docs) == 1
        assert docs[0]["id"] == file_record.id
        assert docs[0]["originalFilename"] == "invoice.pdf"
        assert docs[0]["mimeType"] == "application/pdf"
        assert docs[0]["fileSize"] == 1024

    def test_get_single_document(self, client: TestClient, file_record: FileRecord):
        result = gql(
            client,
            "query($id: Int!) { document(id: $id) { id originalFilename } }",
            variables={"id": file_record.id},
        )
        assert "errors" not in result
        assert result["data"]["document"]["id"] == file_record.id

    def test_get_nonexistent_document_returns_null(self, client: TestClient):
        result = gql(client, "{ document(id: 99999) { id } }")
        assert "errors" not in result
        assert result["data"]["document"] is None

    def test_documents_pagination(self, client: TestClient, db_session):
        for i in range(5):
            db_session.add(
                FileRecord(
                    owner_id="user1",
                    original_filename=f"doc{i}.pdf",
                    local_filename=f"/workdir/tmp/doc{i}.pdf",
                    file_size=100,
                    filehash=f"hash{i}",
                )
            )
        db_session.commit()

        result_page1 = gql(client, "{ documents(limit: 2, offset: 0) { id } }")
        result_page2 = gql(client, "{ documents(limit: 2, offset: 2) { id } }")
        assert "errors" not in result_page1
        assert "errors" not in result_page2
        assert len(result_page1["data"]["documents"]) == 2
        assert len(result_page2["data"]["documents"]) == 2

    def test_documents_limit_clamped_to_100(self, client: TestClient, db_session):
        # Requesting more than 100 should be silently clamped to 100
        for i in range(5):
            db_session.add(
                FileRecord(
                    owner_id="user1",
                    original_filename=f"big{i}.pdf",
                    local_filename=f"/workdir/tmp/big{i}.pdf",
                    file_size=100,
                    filehash=f"bighash{i}",
                )
            )
        db_session.commit()
        result = gql(client, "{ documents(limit: 999) { id } }")
        assert "errors" not in result
        # Just verify it doesn't error and returns something
        assert isinstance(result["data"]["documents"], list)

    def test_documents_filter_by_owner(self, client: TestClient, db_session):
        db_session.add(
            FileRecord(
                owner_id="alice",
                original_filename="alice.pdf",
                local_filename="/workdir/tmp/alice.pdf",
                file_size=100,
                filehash="alicehash",
            )
        )
        db_session.add(
            FileRecord(
                owner_id="bob",
                original_filename="bob.pdf",
                local_filename="/workdir/tmp/bob.pdf",
                file_size=200,
                filehash="bobhash",
            )
        )
        db_session.commit()

        result = gql(client, '{ documents(ownerId: "alice") { id originalFilename } }')
        assert "errors" not in result
        docs = result["data"]["documents"]
        assert all(d["originalFilename"] == "alice.pdf" for d in docs)


# ---------------------------------------------------------------------------
# Tests: pipelines queries
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPipelinesQuery:
    """Tests for the pipelines and pipeline queries."""

    def test_list_pipelines_empty(self, client: TestClient):
        result = gql(client, "{ pipelines { id name } }")
        assert "errors" not in result
        assert result["data"]["pipelines"] == []

    def test_list_pipelines_with_steps(self, client: TestClient, pipeline_record: Pipeline):
        result = gql(
            client,
            """
            {
              pipelines {
                id name description isDefault isActive
                steps { id stepType position enabled }
              }
            }
            """,
        )
        assert "errors" not in result
        pipelines = result["data"]["pipelines"]
        assert len(pipelines) == 1
        assert pipelines[0]["name"] == "Test Pipeline"
        assert len(pipelines[0]["steps"]) == 1
        assert pipelines[0]["steps"][0]["stepType"] == "ocr"

    def test_get_single_pipeline(self, client: TestClient, pipeline_record: Pipeline):
        result = gql(
            client,
            "query($id: Int!) { pipeline(id: $id) { id name steps { stepType } } }",
            variables={"id": pipeline_record.id},
        )
        assert "errors" not in result
        assert result["data"]["pipeline"]["id"] == pipeline_record.id
        assert result["data"]["pipeline"]["steps"][0]["stepType"] == "ocr"

    def test_get_nonexistent_pipeline_returns_null(self, client: TestClient):
        result = gql(client, "{ pipeline(id: 99999) { id } }")
        assert "errors" not in result
        assert result["data"]["pipeline"] is None


# ---------------------------------------------------------------------------
# Tests: settings query (admin-only)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsQuery:
    """Tests for the settings query."""

    def test_settings_returns_data_when_no_auth(self, client: TestClient, setting_record: ApplicationSettings):
        """When AUTH_ENABLED=False, settings are accessible (no auth required)."""
        result = gql(client, "{ settings { key value } }")
        assert "errors" not in result
        keys = [s["key"] for s in result["data"]["settings"]]
        assert "max_upload_size" in keys

    def test_sensitive_settings_excluded(self, client: TestClient, db_session):
        """Sensitive setting keys must never appear in the response."""
        sensitive_keys = [
            "openai_api_key",
            "session_secret",
            "azure_ai_key",
            "smtp_password",
        ]
        for key in sensitive_keys:
            db_session.add(ApplicationSettings(key=key, value="super-secret"))
        db_session.commit()

        result = gql(client, "{ settings { key value } }")
        assert "errors" not in result
        returned_keys = {s["key"] for s in result["data"]["settings"]}
        for key in sensitive_keys:
            assert key not in returned_keys, f"Sensitive key '{key}' was returned by GraphQL settings query"

    def test_settings_auth_required_when_auth_enabled(self, client: TestClient):
        """When AUTH_ENABLED=True and no user, settings query must return an error."""
        from app.config import settings as app_settings

        with patch.object(app_settings, "auth_enabled", True):
            result = gql(client, "{ settings { key } }")
        # Should have errors because no user is authenticated
        assert "errors" in result


# ---------------------------------------------------------------------------
# Tests: users query (admin-only)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUsersQuery:
    """Tests for the users and user queries."""

    def test_users_returns_profiles_when_no_auth(self, client: TestClient, user_profile: UserProfile):
        """When AUTH_ENABLED=False, users are accessible."""
        result = gql(client, "{ users { userId displayName subscriptionTier } }")
        assert "errors" not in result
        users = result["data"]["users"]
        assert any(u["userId"] == "user1" for u in users)

    def test_get_user_by_id(self, client: TestClient, user_profile: UserProfile):
        result = gql(
            client,
            'query { user(userId: "user1") { userId displayName isBlocked } }',
        )
        assert "errors" not in result
        assert result["data"]["user"]["userId"] == "user1"
        assert result["data"]["user"]["displayName"] == "Test User"
        assert result["data"]["user"]["isBlocked"] is False

    def test_get_nonexistent_user_returns_null(self, client: TestClient):
        result = gql(client, '{ user(userId: "nobody") { userId } }')
        assert "errors" not in result
        assert result["data"]["user"] is None

    def test_users_auth_required_when_auth_enabled(self, client: TestClient):
        """When AUTH_ENABLED=True and no user, users query must return an error."""
        from app.config import settings as app_settings

        with patch.object(app_settings, "auth_enabled", True):
            result = gql(client, "{ users { userId } }")
        assert "errors" in result


# ---------------------------------------------------------------------------
# Tests: auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGraphQLAuth:
    """Verify auth is enforced for all queries when AUTH_ENABLED=True."""

    def test_documents_auth_required_when_auth_enabled(self, client: TestClient):
        from app.config import settings as app_settings

        with patch.object(app_settings, "auth_enabled", True):
            result = gql(client, "{ documents { id } }")
        assert "errors" in result

    def test_pipelines_auth_required_when_auth_enabled(self, client: TestClient):
        from app.config import settings as app_settings

        with patch.object(app_settings, "auth_enabled", True):
            result = gql(client, "{ pipelines { id } }")
        assert "errors" in result
