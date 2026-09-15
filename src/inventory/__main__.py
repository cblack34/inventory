"""Container entrypoint: ``python -m inventory`` loads settings and runs uvicorn.

Fails fast on bad configuration: a missing or invalid environment
variable exits 1 with the offending variable named on stderr, before
the app or its database engine is ever built.
"""

import sys

import uvicorn

from inventory.app import create_app
from inventory.settings import SettingsError, load_settings


def main() -> None:
    try:
        settings = load_settings()
    except SettingsError as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc

    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
