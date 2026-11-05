"""Source pins from the 2026-11 repo security audit. No network."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MERMAID_SHA256 = "616a109f19cd186842e11d45b35ac07456b3a75513310f6ea075351aa430b1e2"
SETUP_UV = "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2"


def _job_source(workflow: str, job_name: str) -> str:
    lines = workflow.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f"  {job_name}:":
            start = index
            break
    if start is None:
        raise AssertionError(f"job {job_name} not found")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def test_go_module_tag_uses_release_tag_commit_not_github_sha() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = _job_source(workflow, "tag-go-module")
    assert "GITHUB_SHA" not in job
    assert 'git rev-parse "${RELEASE_TAG}^{commit}"' in job
    claim = (ROOT / "scripts/claim-release-processed.sh").read_text(encoding="utf-8")
    assert "GITHUB_SHA" not in claim
    assert 'git rev-parse HEAD' in claim


def test_pages_installs_mkdocs_from_uv_lock() -> None:
    pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "mkdocs-material>=" not in pages
    assert "pip install" not in pages
    assert SETUP_UV in pages
    assert "uv sync --frozen --only-group dev --no-install-project" in pages


def test_release_wheel_job_does_not_pipe_uv_installer() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = _job_source(workflow, "build-wheels")
    assert "astral.sh/uv/install.sh" not in job
    assert "curl" not in job
    assert SETUP_UV in job
    assert 'version: "0.13.6"' in job


def test_mkdocs_vendors_mermaid_same_origin() -> None:
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "unpkg.com" not in mkdocs
    assert "javascripts/mermaid.min.js" in mkdocs
    bundle = ROOT / "docs/javascripts/mermaid.min.js"
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert digest == MERMAID_SHA256
    loader = (ROOT / "docs/javascripts/mermaid.js").read_text(encoding="utf-8")
    assert MERMAID_SHA256 in loader
