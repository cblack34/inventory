# Deployment

How to configure, run, back up, and rotate secrets for the one-container
Compose deployment. The hosting target (a VPS with Caddy, or an AWS
Lightsail instance with an attached block disk) is still an open decision
-- see `docs/acceptance.md`'s research gates -- but everything below runs
identically on a laptop and on either host, since neither Caddy nor TLS is
part of this container.

## Configure

Copy the example environment file, readable only by you since it will hold
both secrets, and fill in real values:

```bash
install -m 600 .env.example .env
```

- `SHARED_PASSWORD` -- the one password both users log in with. No default
  anywhere in code or in `compose.yaml`; startup exits non-zero naming this
  variable if it is unset or empty.
- `SESSION_SECRET` -- at least 32 bytes, used to sign the session cookie.
  Generate one with:

  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

  Startup exits non-zero naming this variable if it is unset, empty, or
  shorter than 32 bytes.
- `TIMEZONE` -- the business's IANA timezone name (for example
  `America/Chicago`), used to compute "today" for batches and visits.
- `INSECURE_COOKIES` -- leave commented out (absent) in production.
  Session cookies are `Secure` by default, which requires HTTPS; uncomment
  `INSECURE_COOKIES=true` only for local HTTP testing on a laptop with no
  TLS-terminating proxy in front. A production deployment needs a reverse
  proxy (Caddy, per the open hosting decision) terminating TLS in front of
  this container.

`.env` is already gitignored; never commit a real one. `docker compose up`
fails outright if `.env` does not exist, because `compose.yaml` reads
`SHARED_PASSWORD` and `SESSION_SECRET` only through `env_file: .env` --
there is no fallback value in `compose.yaml` for either.

## Run

First, on a Linux host, create the bind-mounted backup directory owned by
the container's fixed non-root user (UID and GID 1000, set in the
`Dockerfile`) and readable by nobody else. Do this before the first
`docker compose up`: Docker creates a missing bind-mount source as root,
and the non-root container user could not write backups into it.

```bash
sudo install -d -m 700 -o 1000 -g 1000 backups
```

`backups/inventory.db` holds real business data once a backup has run, so
the directory must not be world-readable; it is gitignored, same as
`.env`. On Docker Desktop for macOS a plain `mkdir -p backups` is enough,
since the bind mount is already writable by the container user.

Then:

```bash
docker compose up -d --build
```

This builds one image (a Node stage builds the frontend; the runtime stage
is `python:3.14-slim`) and starts one container. The entrypoint runs
`alembic upgrade head` and only then starts the server; a failed migration
exits non-zero and the server never starts. The app serves on
**port 8000, bound to loopback only** (`127.0.0.1:8000`): on a laptop that
is `http://localhost:8000`, and in production the TLS-terminating proxy on
the same host forwards to it, so no plaintext path exists around the proxy.
If startup fails (a missing or short secret, a failed migration), the
container stops after three attempts rather than looping; read the cause
with `docker compose logs app`. The SQLite file lives at `/data/inventory.db` inside the
container, on the named volume `data`, so it survives `docker compose
down` (without `-v`) and image rebuilds.

Check it came up:

```bash
curl -i http://localhost:8000/login
```

## Back up

The container has the `sqlite3` CLI installed (the base image ships the
library but not the binary) and `./backups` on the host is bind-mounted to
`/backups` in the container. From the project directory that holds
`compose.yaml` and `.env` (adjust the path for your host; `/srv/inventory`
is this project's convention):

```bash
cd /srv/inventory && docker compose exec -T app sh -c 'sqlite3 "$DB" ".backup /backups/inventory.db"'
```

`-T` disables the TTY a cron job lacks. The single quotes matter: they
defer `$DB` expansion to the container's shell, where `DB` is actually
set, rather than expanding an unset variable on the host first.

That produces `./backups/inventory.db` on the host. A nightly host cron
entry runs the same command and then uploads that file to object storage;
the cron entry and the upload credentials belong to the host, not this
repository (out of scope until the hosting gate closes -- see
`docs/tech-stack.md`'s Shipping table). Run that cron job as root: it
already needs Docker access for `docker compose exec`, and root can read
the `backups` directory below even though it is mode 700 and owned by the
container's UID 1000.

## Rotate secrets

Rotating `SESSION_SECRET` and restarting (`docker compose up -d` again
after editing `.env`) invalidates every outstanding session cookie --
existing cookies fail the signature check and every user is logged out.

Login checks `SHARED_PASSWORD` only at the moment a session is issued, not
on every request, so changing the password alone does not invalidate
cookies already issued under the old one. After a suspected password
compromise, rotate **both** `SHARED_PASSWORD` and `SESSION_SECRET` and
restart, so old sessions are invalidated along with the old password.

## Running behind a proxy

A production deployment puts a TLS-terminating reverse proxy (Caddy, per
the open hosting decision) in front of this container. Without more
configuration, every request would appear to uvicorn as coming from the
proxy's own IP, which collapses the per-IP login-failure throttle
(`docs/acceptance.md`'s login criterion) into one shared counter across
every real client.

Verified against uvicorn's own `Config` (`uvicorn/config.py`,
`uvicorn.run`'s parameters, checked against the pinned version in
`uv.lock`): `uvicorn.run()` (what `python -m inventory` calls) leaves
`proxy_headers` at its default of `True` and `forwarded_allow_ips` at its
default of `None`. When `forwarded_allow_ips` is `None`, `Config.__init__`
itself -- not just the CLI -- reads the `FORWARDED_ALLOW_IPS` environment
variable (falling back to `127.0.0.1` if it, too, is unset). So no Python
change is needed: set `FORWARDED_ALLOW_IPS` to the proxy's address as a
regular environment variable for the container (add it to `compose.yaml`'s
`environment:` block, the same way `DB` is set, once the proxy's address is
known) and uvicorn honors it automatically.

## Everything else

`make check` and `make e2e` (see `AGENTS.md`) remain the definition of done
for code changes; this document only covers running the already-built
image.
