"""`python -m inventory` fails fast on bad configuration (`docs/acceptance.md`).

Each subprocess starts from a fully valid environment and breaks
exactly one variable, so a non-zero exit and the named variable in
stderr can only be attributed to that one change. None of these ever
reach `uvicorn.run`, so no port is bound.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(overrides: dict[str, str | None], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DB"] = str(tmp_path / "inventory.db")
    env["SHARED_PASSWORD"] = "correct horse"
    env["SESSION_SECRET"] = "0" * 32
    env["TIMEZONE"] = "UTC"
    env["INSECURE_COOKIES"] = "true"
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    return subprocess.run(
        [sys.executable, "-m", "inventory"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_missing_shared_password_exits_nonzero_naming_it(tmp_path: Path) -> None:
    result = _run({"SHARED_PASSWORD": None}, tmp_path)

    assert result.returncode != 0
    assert "SHARED_PASSWORD" in result.stderr


def test_empty_shared_password_exits_nonzero_naming_it(tmp_path: Path) -> None:
    result = _run({"SHARED_PASSWORD": ""}, tmp_path)

    assert result.returncode != 0
    assert "SHARED_PASSWORD" in result.stderr


def test_short_session_secret_exits_nonzero_naming_it(tmp_path: Path) -> None:
    result = _run({"SESSION_SECRET": "a" * 31}, tmp_path)

    assert result.returncode != 0
    assert "SESSION_SECRET" in result.stderr
