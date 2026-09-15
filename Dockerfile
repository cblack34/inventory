# syntax=docker/dockerfile:1

# ---- Frontend build stage --------------------------------------------------
# node:24-slim matches src/web/.node-version (major 24, the current Node LTS).
FROM node:24-slim AS web-build

WORKDIR /app/src/web

COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci

COPY src/web/ ./
RUN npm run build

# ---- Python runtime stage --------------------------------------------------
# python:3.14-slim matches pyproject.toml's `requires-python = ">=3.14"`.
FROM python:3.14-slim AS runtime

# Slim ships libsqlite3 but not the `sqlite3` CLI; docs/deployment.md's
# nightly backup command runs it inside the container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# uv, per its own Docker docs: copy the static binaries from its distroless
# image rather than run the installer script. Pinned (not `:latest`) for a
# reproducible build.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /usr/local/bin/

# One fixed, non-root UID/GID so ownership is stable across rebuilds.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies before the rest of the source, so an image rebuild after a
# source-only change reuses this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src/inventory/ src/inventory/
COPY alembic.ini ./
COPY alembic/ alembic/
RUN uv sync --locked --no-dev

# The built frontend, at the path inventory.api.static expects relative to
# the installed package: src/web/dist next to src/inventory/.
COPY --from=web-build /app/src/web/dist src/web/dist

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN chown -R app:app /app

# The mount point for the `data` named volume (compose.yaml). Docker
# Compose seeds a brand-new named volume from whatever already exists at
# its mount path in the image, ownership included, so this must be
# `app`-owned before the volume is ever attached -- otherwise the first
# mount would be root-owned and the non-root process below could not open
# the database file.
RUN mkdir -p /data && chown app:app /data

USER app

# The venv was fully built with `--locked --no-dev` above; `uv run` in the
# entrypoint must never re-sync (that would touch the network at container
# start and could pull dev dependencies back in), so it just launches from
# the venv that already exists.
ENV UV_NO_SYNC=1

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
