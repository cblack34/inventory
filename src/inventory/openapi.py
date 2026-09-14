"""Dumps the FastAPI app's OpenAPI schema as JSON.

The app itself serves no OpenAPI route (``openapi_url=None``); this module
exists solely so ``make check`` can generate frontend API types from
``create_app(settings).openapi()`` without starting a server or reading
the real environment -- the settings below are dummy values good enough
to build the app, never used to serve traffic.
"""

import json
import sys
import tempfile
from pathlib import Path

from pydantic import SecretStr

from inventory.app import create_app
from inventory.settings import Settings


def _dummy_settings() -> Settings:
    return Settings(
        DB=str(Path(tempfile.gettempdir()) / "inventory-openapi-dummy.db"),
        SHARED_PASSWORD=SecretStr("dummy-password"),
        SESSION_SECRET=SecretStr("0" * 32),
        TIMEZONE="UTC",
        INSECURE_COOKIES=True,
    )


if __name__ == "__main__":
    sys.stdout.write(json.dumps(create_app(_dummy_settings()).openapi()))
