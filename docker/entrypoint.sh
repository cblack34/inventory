#!/bin/sh
# Container entrypoint: migrate, then serve. A failed migration must exit
# non-zero and the server must never start -- `set -e` plus running the
# migration as its own statement (not backgrounded) is enough for that.
#
# `uv run` is used only as the fixed venv's launcher here (`UV_NO_SYNC=1` is
# set in the Dockerfile, so this never re-syncs or touches the network at
# container start; the environment was already built with
# `uv sync --locked --no-dev` when the image was built).
#
# `#!/bin/sh` (dash in this base image), not bash, so no `pipefail`: there
# is no pipeline below for it to guard.
set -eu

uv run alembic upgrade head
exec uv run python -m inventory
