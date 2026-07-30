from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
LEGACY_BUILD_SCRIPT = ROOT / "deploy" / "scripts" / "build-all.sh"
ENGINE_REVISION = "815c5d057dc87d8babcc7839c35ccec83435ae13"


def _workflow(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text)
    assert isinstance(value, dict)
    for boolean_key in (True, False):
        if boolean_key in value:
            value["on"] = value.pop(boolean_key)
    return value


def test_all_hosted_workflows_are_manual_only() -> None:
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = _workflow(path)
        assert set(workflow["on"]) == {"workflow_dispatch"}


def test_release_is_main_only_least_privilege_and_immutable() -> None:
    workflow = _workflow(RELEASE_WORKFLOW)
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow["permissions"] == {"contents": "read"}
    release = workflow["jobs"]["release"]
    assert release["if"] == "github.ref == 'refs/heads/main'"
    assert release["environment"] == "production-release"
    assert release["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert "persist-credentials: false" in text
    references = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", text)
    assert references
    assert all(re.fullmatch(r"[a-f0-9]{40}", item) for item in references)


def test_release_signs_and_attests_exact_gateway_digest() -> None:
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "docker/build-push-action@" in text
    assert "platforms: linux/amd64" in text
    assert "push: true" in text
    assert "${{ steps.push.outputs.digest }}" in text
    assert "cosign sign --yes" in text
    assert "cosign attest --yes --type cyclonedx" in text
    assert "cosign attest --yes --type slsaprovenance" in text
    assert "cosign attest --yes --type vuln" in text
    assert "--format cosign-vuln" in text
    assert "--severity HIGH,CRITICAL" in text
    assert "--exit-code 1" in text
    assert ":latest" not in text


def test_runtime_build_is_locked_nonroot_and_source_independent() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert text.count(
        "python:3.12-slim@sha256:"
    ) == 2
    assert "uv==0.11.21" in text
    assert "uv sync --frozen --no-dev --extra otel --no-editable" in text
    assert "COPY uv.lock pyproject.toml README.md ./" in text
    assert "COPY _mcp-oci" not in text
    assert "USER 10001:10001" in text
    assert "HEALTHCHECK" in text and "http://127.0.0.1:9000/health" in text
    assert ENGINE_REVISION in project
    assert ENGINE_REVISION in lock


def test_ci_actions_are_pinned_after_manual_pause() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    references = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", text)

    assert references
    assert all(re.fullmatch(r"[a-f0-9]{40}", item) for item in references)


def test_legacy_remote_build_uses_an_explicit_immutable_tag() -> None:
    text = LEGACY_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'TAG="${TAG:-$(git -C "$PROJECT_ROOT" rev-parse HEAD)}"' in text
    assert '"$TAG" =~ ^[a-f0-9]{40}$' in text
    assert ":latest" not in text
    assert "docker push $OCIR/$name:$TAG" in text
