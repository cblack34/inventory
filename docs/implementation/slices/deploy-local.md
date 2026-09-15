# Slice plan — deploy-local

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md).
- **Human approval:** repository owner, 2026-09-15, after slice `web-shell` merged; the owner asked for the Compose shape now so the app can be seen running, pulling the brief's step 5 ahead of the entry screens.
- **Final acceptance advanced:** Login and deployment: `docker compose up` on a clean machine starts one container serving the app on a documented port with the SQLite file on a named volume, the entrypoint runs `alembic upgrade head` idempotently and a failed migration exits non-zero; deployment notes document the backup command and where the backup goes; sets up the owner's human backup verification.

## Outcome

One `Dockerfile`, one `compose.yaml`, an entrypoint that migrates then serves, a `.env.example`, and `docs/deployment.md`. `docker compose up --build` on a clean machine yields a running app on port 8000 with the database on a named volume and `./backups` bind-mounted for the documented `sqlite3 .backup` command.

## Why this slice is next

The brief lists container, Compose, and deployment notes last because the hosting target is open, but it also says the single-container plus persistent-volume shape works on either candidate host and nothing in code depends on the choice. The owner wants to see the shipped shell and home screen running as they would in production, and the Compose criterion is required by acceptance regardless of hosting. Doing it now costs nothing later; only Caddy, TLS, cron, and object storage wait on the gate.

## Scope

### In scope

- Multi-stage `Dockerfile`: Node stage builds the frontend; Python 3.14 slim runtime with `uv` and the `sqlite3` CLI, non-root user, dependencies installed from the lockfile without dev extras.
- Entrypoint: `alembic upgrade head` then `python -m inventory`; migration failure exits non-zero and the server never starts.
- `compose.yaml`: one service, port 8000, `.env` for secrets, `DB` on a named volume, `./backups` bind-mounted, restart policy.
- `.env.example`, `.dockerignore`, `docs/deployment.md` (env, run, port, volume, backup command and destination, `INSECURE_COOKIES` absent in production, secret rotation invalidating sessions, uvicorn `FORWARDED_ALLOW_IPS` behind a proxy), a README pointer.

### Out of scope

- Caddy, TLS, host provisioning, the cron entry, object-storage upload (hosting gate open).
- Building or pushing the image in CI; any change to `make check` or `make e2e`.
- Any Python, schema, API, or frontend change.
- Entry screens (next slice, `web-entry`).

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Deployment shape: one container serving API and built frontend, SQLite on a persistent volume, documented nightly file backup, runs locally with Compose | Exactly this slice's artifacts. |
| Entrypoint runs `alembic upgrade head` idempotently, never `create_all`; failed migration exits non-zero | Entrypoint script with `set -e`, migration before `exec` of the server. |
| Fail fast on missing or short secrets; no default in code or Compose | Compose supplies values only from `.env`; the app's existing settings validation exits 1 naming the variable. |
| `Secure` cookies by default, `INSECURE_COOKIES` only for local HTTP | Deployment notes state the variable must be absent in production and that TLS terminates at a proxy. |
| Per-IP login throttle behind a proxy (tech-stack uvicorn row) | Notes document `FORWARDED_ALLOW_IPS`; verified against current uvicorn docs during execution. |
| Backup command (tech-stack Shipping row) | Notes carry the exact command; `./backups` is the bind-mounted boundary. |

## Gates and dependencies

### Hard gates

- None. Depends only on `main` at 9d6aabc.

### Sequencing recommendations

- One leaf; nothing to order.

## Architecture and contracts

- **Affected seams:** repository root packaging files and `docs/deployment.md`. No source change. The static mount path `src/web/dist` relative to the package is the one contract the image layout must honor.
- **Public contracts:** none changed. Port 8000 and the `.env` variable names become the documented operator contract.
- **Data and migration considerations:** none; the entrypoint runs the existing migration chain.

## High-level approach

One leaf PR into `slice/deploy-local`, delegated to a standard-tier agent with its issue as the packet. Base images and the `uv` Docker pattern are verified against current official docs before writing. Verification is a real `docker compose up --build` from a clean checkout followed by curl checks, the documented backup command, and a negative start with the session secret missing. Copilot is requested by hand on the leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` and `make e2e` exit 0 and are unchanged.
- From a clean checkout with `.env` from the example plus `INSECURE_COOKIES=true`: `docker compose up -d --build` serves `/login` (200), redirects `/` (303), answers `/api/v1/stock` 401 unauthenticated and 200 after login; the documented backup command produces `./backups/inventory.db` containing the five built-in locations; removing `SESSION_SECRET` makes startup exit non-zero naming it.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- `python:3.14-slim` or a matching `uv` image tag is unavailable; stop and report rather than lowering the Python floor.
- uvicorn's proxy-header handling requires a code change to honor `FORWARDED_ALLOW_IPS`; stop and report, since Python is out of scope here.
- Image build pulls dev dependencies or the Playwright browser by accident; keep `--no-dev` and the Node stage separate.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#39](https://github.com/cblack34/inventory/issues/39) — deploy-local/compose: Dockerfile, entrypoint, compose.yaml, .env.example, deployment notes | The whole slice | None |

## Delivery shape

- **Topology:** per-slice spine with one leaf PR.
- **Branch or spine:** `slice/deploy-local`; leaf `deploy-local/compose`.
- **Final PR:** [#41](https://github.com/cblack34/inventory/pull/41).
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** Delivered 2026-09-15. `Dockerfile` (Node 24 build stage; `python:3.14-slim` runtime with `uv` 0.12.15 copied from its official image, the `sqlite3` CLI, `uv sync --locked --no-dev` under BuildKit cache mounts, non-root UID 1000, `/data` pre-owned for the named volume), `docker/entrypoint.sh` (`alembic upgrade head` then `exec python -m inventory`), `compose.yaml` (one service on port 8000, `env_file: .env`, `DB=/data/inventory.db` on volume `data`, `./backups:/backups`, stdlib healthcheck), `.env.example`, `.dockerignore`, `/backups/` gitignored, and `docs/deployment.md`.
- **Verification:** `make check` exit 0 and `make e2e` exit 0 on code head b121e49 (unchanged by this slice). Real `docker compose up -d --build` on b121e49: health 200 within 3 s, `/login` 200, `/` 303 to `/login`, `/api/v1/stock` 401 Problem then 200 after a 204 login, the documented backup command produced `backups/inventory.db` holding the five built-in locations, image 372 MB, `down -v` clean. Negative start without `SESSION_SECRET` exits 1 naming it (leaf verification on 7b8b0d8). Leaf evidence on [#40](https://github.com/cblack34/inventory/pull/40): green CI and a HEAD-matched "Approval recommended" Copilot pass. Issue [#39](https://github.com/cblack34/inventory/issues/39) carries the trail. The commits after the code head are this record and one deployment-notes sentence (the nightly cron job runs as root so it can read the mode-700 backup directory), added after the spine PR's third Copilot pass recommended approval.
- **Deviations:** Pulled ahead of the entry screens at the owner's request. The first container start failed because a fresh named volume inherits the image's root-owned mount point; fixed by creating `/data` owned by `app` in the image. uvicorn 0.52.4 honors `FORWARDED_ALLOW_IPS` from the environment inside `uvicorn.run()`, so the tech-stack uvicorn row was corrected from CLI flags to that variable. Two suppressed docs nits from the leaf's final pass (`.env` mode 600; the tech-stack row) were applied on the spine. The spine PR's first Copilot pass added one hardening nit, applied on the spine: `/app` stays root-owned and read-only to the runtime user, with only `/data` and `/backups` writable (verified by a fresh compose run). Its second pass added two more, also applied on the spine: the port is published on loopback only so the TLS proxy is the sole production ingress, and the restart policy is `on-failure:3` so a bad `.env` or failed migration leaves a stopped container to diagnose (verified: exits 1 and stays stopped).
- **Unresolved gates or risks:** Hosting target open; Caddy, TLS, the cron entry, and object-storage upload wait on it. The owner's human backup verification against a running instance is still to be done. Backlog [#37](https://github.com/cblack34/inventory/issues/37) is untouched.
- **Final PR:** [#41](https://github.com/cblack34/inventory/pull/41).
- **Merge state:** Ready for the human to merge; agents do not merge to `main`.
