"""Contracts for the zero-configuration Docker Compose installation."""

from pathlib import Path

import yaml

COMPOSE_FILE = Path(__file__).parents[1] / "docker-compose.yaml"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_fresh_install_includes_complete_runtime_stack():
    services = set(_compose()["services"])

    assert {
        "api",
        "worker",
        "beat",
        "knowledge-research-worker",
        "search-index-worker",
        "postgres",
        "redis",
        "gotenberg",
        "meilisearch",
        "qdrant",
    } <= services


def test_api_port_and_public_urls_follow_canary_port():
    compose = _compose()
    environment = compose["x-docuelevate-service"]["environment"]

    assert compose["services"]["api"]["ports"] == ["${DOCUELEVATE_PORT:-8000}:8000"]
    assert environment["EXTERNAL_HOSTNAME"] == "localhost:${DOCUELEVATE_PORT:-8000}"
    assert environment["PUBLIC_BASE_URL"] == "http://localhost:${DOCUELEVATE_PORT:-8000}"


def test_fresh_install_uses_named_workdir_volume_by_default():
    compose = _compose()

    assert "workdir-data" in compose["volumes"]
    assert "${DOCUELEVATE_WORKDIR:-workdir-data}:/workdir" in compose["x-docuelevate-service"]["volumes"]


def test_all_application_processes_share_one_image_built_once():
    compose = _compose()
    service_defaults = compose["x-docuelevate-service"]

    assert service_defaults["image"] == "${DOCUELEVATE_IMAGE:-docuelevate:local}"
    assert "build" not in service_defaults
    assert compose["services"]["api"]["build"] == {"context": ".", "dockerfile": "Dockerfile"}


def test_default_worker_concurrency_fits_small_fresh_install_hosts():
    command = _compose()["services"]["worker"]["command"]

    assert "--concurrency=${DOCUELEVATE_WORKER_CONCURRENCY:-1}" in command


def test_default_worker_consumes_all_queues_without_optional_scale_workers():
    compose = _compose()
    command = compose["services"]["worker"]["command"]
    queues = command[command.index("-Q") + 1].split(",")

    assert {
        "document_processor",
        "default",
        "celery",
        "knowledge_research",
        "search_index",
    } <= set(queues)
    assert compose["services"]["knowledge-research-worker"]["profiles"] == ["scale"]
    assert compose["services"]["search-index-worker"]["profiles"] == ["scale"]


def test_celery_redis_routes_keep_local_defaults_and_allow_operator_overrides():
    environment = _compose()["x-docuelevate-service"]["environment"]

    assert environment["REDIS_URL"] == "redis://redis:6379/0"
    assert environment["CELERY_BROKER_URL"] == "${CELERY_BROKER_URL:-redis://redis:6379/0}"
    assert environment["CELERY_RESULT_BACKEND"] == "${CELERY_RESULT_BACKEND:-redis://redis:6379/0}"
