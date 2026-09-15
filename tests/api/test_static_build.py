"""A partial frontend build must not break app construction (static.py)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inventory.app import create_app
from inventory.settings import Settings


@pytest.mark.parametrize("present", ["index.html", "assets"], ids=["index-only", "assets-only"])
def test_partial_build_is_skipped_not_served(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: str
) -> None:
    dist = tmp_path / "partial-dist"
    dist.mkdir()
    if present == "index.html":
        (dist / "index.html").write_text("<html></html>")
    else:
        (dist / "assets").mkdir()
    monkeypatch.setattr("inventory.api.static._DIST_DIR", dist)

    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/login").status_code == 404
        assert client.get("/api/v1/health").status_code == 200
