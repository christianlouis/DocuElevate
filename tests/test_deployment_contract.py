"""Regression tests for Helm, Terraform, and agentic deployment contracts."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "docuelevate"
TERRAFORM = ROOT / "examples" / "terraform" / "kubernetes"


def test_helm_app_version_matches_product_version():
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert str(chart["appVersion"]) == (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_release_automation_keeps_helm_app_version_in_sync():
    metadata_script = (ROOT / "scripts" / "generate_build_metadata.sh").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert 'HELM_CHART="helm/docuelevate/Chart.yaml"' in metadata_script
    assert 'appVersion: "{os.environ["VERSION"]}"' in metadata_script
    assert "helm/docuelevate/Chart.yaml" in release_workflow


def test_helm_processes_use_the_configurable_runtime_secret():
    templates = [
        "api-deployment.yaml",
        "worker-deployment.yaml",
        "knowledge-research-worker-deployment.yaml",
        "search-index-worker-deployment.yaml",
        "migration-job.yaml",
    ]
    for template in templates:
        content = (CHART / "templates" / template).read_text(encoding="utf-8")
        assert 'include "docuelevate.secretName"' in content
        assert 'include "docuelevate.fullname" . }}-secret' not in content


def test_agentic_helm_hook_plans_before_apply_and_scopes_setup_credentials():
    template = (CHART / "templates" / "agentic-setup.yaml").read_text(encoding="utf-8")
    plan = "python -m app.agentic_setup plan /config/setup.json"
    apply = "python -m app.agentic_setup apply /config/setup.json"
    assert template.index(plan) < template.index(apply)
    assert '"helm.sh/hook": post-install,post-upgrade' in template
    assert ".Values.agenticSetup.existingSecret" in template

    for template_name in ("api-deployment.yaml", "worker-deployment.yaml"):
        long_running_template = (CHART / "templates" / template_name).read_text(encoding="utf-8")
        assert "agenticSetup.existingSecret" not in long_running_template


def test_terraform_accepts_secret_names_but_not_secret_values():
    variables = (TERRAFORM / "variables.tf").read_text(encoding="utf-8")
    main = (TERRAFORM / "main.tf").read_text(encoding="utf-8")
    assert 'variable "bootstrap_secret_name"' in variables
    assert 'variable "setup_secret_name"' in variables
    assert 'variable "database_url"' not in variables.lower()
    assert 'variable "session_secret"' not in variables.lower()
    assert "existingSecret = var.bootstrap_secret_name" in main
    assert "existingSecret = var.setup_secret_name" in main
