"""Dumps the FastAPI app's OpenAPI schema as JSON.

The app itself serves no OpenAPI route (``openapi_url=None``); this module
exists solely so ``make check`` can generate frontend API types from
``create_app().openapi()`` without starting a server.
"""

import json
import sys

from inventory.app import create_app

if __name__ == "__main__":
    sys.stdout.write(json.dumps(create_app().openapi()))
