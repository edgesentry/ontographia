"""Unit tests for scripts/litellm/check_encrypted_env.sh (no real secrets)."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "litellm" / "check_encrypted_env.sh"


def _run_check(cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(CHECK)],
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_script_exists_and_is_executable_bits() -> None:
    assert CHECK.is_file()
    # Executable bit is nice-to-have; CI invokes via `bash path`.
    assert CHECK.read_text(encoding="utf-8").startswith("#!/")


def test_repo_check_passes_without_ciphertext_yet() -> None:
    """Until the maintainer commits .env.encrypted, the guard must succeed."""
    result = _run_check(ROOT)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ok:" in result.stdout


def test_guard_rejects_plaintext_values(tmp_path: Path) -> None:
    """In a throwaway git repo, a tracked env file with plaintext must fail."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    litellm = tmp_path / "scripts" / "litellm"
    litellm.mkdir(parents=True)
    # Copy the real check script into the fixture tree so relative ROOT resolves.
    check_dst = litellm / "check_encrypted_env.sh"
    check_dst.write_text(CHECK.read_text(encoding="utf-8"), encoding="utf-8")

    env_file = litellm / ".env.encrypted"
    env_file.write_text(
        textwrap.dedent(
            """\
            # banner
            DOTENV_PUBLIC_KEY_ENCRYPTED="abc123"
            GEMINI_API_KEY=plaintext-not-allowed
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "scripts/litellm/.env.encrypted"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add bad env"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["bash", str(check_dst)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "not dotenvx ciphertext" in result.stderr


def test_guard_accepts_encrypted_prefix(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    litellm = tmp_path / "scripts" / "litellm"
    litellm.mkdir(parents=True)
    check_dst = litellm / "check_encrypted_env.sh"
    check_dst.write_text(CHECK.read_text(encoding="utf-8"), encoding="utf-8")

    env_file = litellm / ".env.encrypted"
    env_file.write_text(
        textwrap.dedent(
            """\
            DOTENV_PUBLIC_KEY_ENCRYPTED="abc123"
            GEMINI_API_KEY="encrypted:BGfakeCiphertextOnlyForUnitTest=="
            LITELLM_PORT=encrypted:BGanotherFakeValue==
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "scripts/litellm/.env.encrypted"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add good env"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["bash", str(check_dst)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ok:" in result.stdout
