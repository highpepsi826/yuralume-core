# Yuralume Development and Deployment Instructions

Read `LOCAL_CUSTOMIZATION_WORKFLOW.md` before modifying this repository or the
local Yuralume deployment.

## Current Hosted Production

The project now has a hosted production runtime in Zeabur. Keep this section
current when the topology changes; the Zeabur dashboard is the final source of
truth for live status, while `deploy/zeabur/README.md` is the detailed
operation runbook.

- The production project is `yuralume-production` on the dedicated Tokyo
  server. The public app domain is `yuralume-prod.zeabur.app`.
- The active app service is the only production runtime and must stay at one
  replica using the default `all` role. It is the sole owner of Telegram
  polling and scheduled background work.
- The active database service is `postgresql` with `pgvector`, reachable from
  the project only through `postgresql.zeabur.internal:5432`. The obsolete
  suspended `postgres` rollback service and its `postgres-data` volume were
  explicitly deleted on 2026-09-04; do not recreate or target them.
- The active object-storage service is `storage`, reachable only through
  `http://storage.zeabur.internal:9000`. It uses the pinned personal-fork image
  `ghcr.io/highpepsi826/yuralume-core/storage-local:sha-347c951`, with
  `YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648`. Its `storage-data` volume is
  mounted at `/data` and contains both `objects/` and `metadata` restored from
  the encrypted migration backup. The temporary migration public domain has
  been removed; never expose the storage or database services publicly.
- The initial admin account has been configured through the hosted `/setup`
  flow. Do not reset it or add bootstrap credentials unless the user asks.
- The database and storage migration has been validated. Keep the local
  encrypted backup and the cloud rollback/restore protection in place until
  the user explicitly approves retention cleanup.

## Hosted Development and Deployment

- Edit source in `C:\Entertainment\yuralume-src` and push reviewed commits on
  `local/customizations`; Zeabur builds the hosted app from that branch. Do
  not edit a running cloud container or treat a manual dashboard build as a
  substitute for a source commit.
- Local development on this computer or another notebook must use an isolated
  local Compose stack. Never point a default local runtime at the hosted
  database or storage, and never run local Telegram polling or schedulers at
  the same time as the hosted app. There must be exactly one Telegram polling
  owner.
- For a production bug, obtain a labelled encrypted cloud snapshot/export and
  restore it into an isolated local stack. Disable Telegram and other external
  connectors there. Reproduce, test, and repair locally; never write a local
  development database back into production.
- Before any production migration or data operation, read the Zeabur runbook,
  check the current service status, obtain explicit user confirmation, and
  create and verify a PostgreSQL custom-format backup. Migrations run once in
  a controlled environment; never run Alembic concurrently from local and
  cloud. Prefer an app-only redeploy when no schema change is involved.
- A storage migration must move `objects/` and `metadata/` together. Use the
  staged encrypted transfer procedure in the runbook; do not use Zeabur
  `Restore from File` for the storage archive, and do not expose plaintext
  storage during transfer.
- Update the hosted `storage` image only when storage-service code changes.
  Pin a personal-fork commit tag (or digest), keep the existing `storage`
  service and `storage-data` volume mounted at `/data`, and verify a known
  media object after restart. Never switch production back to an upstream
  moving `latest` tag merely because the app branch changed.
- After a hosted deployment, verify the app is `Running` with one replica,
  `GET https://yuralume-prod.zeabur.app/health` returns `status=ok` with the
  database overlay active, representative media can be read, and admin login
  works. Only after those checks should Telegram polling be considered
  operational.
- Keep `CONFIG_ENCRYPTION_KEY` stable across deployments so encrypted Admin
  provider configuration remains readable. Store all secrets only in Zeabur
  variables or local ignored environment files; never commit, log, paste, or
  print them.
- Production uploads, deletes, rollback changes, public-port changes, and
  actions that may incur Zeabur charges require explicit confirmation at the
  point of action. Preserve rollback backups until the resulting deployment
  and data have been verified.

## Branches and Upstream

- Work only on `local/customizations` for local changes.
- Treat `main` as an upstream mirror. Do not commit local changes to it.
- `origin` is the personal fork and `upstream` is `Yuralume/yuralume-core`.
- Before an upstream update, fetch both remotes and merge the updated `main`
  into `local/customizations`. Do not discard local commits to make updates
  appear clean.

## Deployment Boundaries

- Runtime files live in `C:\Entertainment\yuralume`.
- Source files live in `C:\Entertainment\yuralume-src`.
- Do not edit code inside a running Docker container.
- Do not overwrite `C:\Entertainment\yuralume\.env.container`, uploads,
  backups, or Docker volumes.
- Treat `C:\Entertainment\yuralume\docker-compose.yml` as the
  installer-managed deployment base. It is not interchangeable with either
  source Compose file. Never replace it with `docker-compose.yml` or
  `docker-compose.container.yml` from this repository: their service and
  volume names differ and can make Docker start a separate, empty database.
- Keep the existing storage port mapping `127.0.0.1:19012:9000` unless the
  user explicitly requests a verified change.

## Local Source Builds

- Use both Compose files for any local-source deployment:

  ```powershell
  docker compose --env-file .env.container `
    -f docker-compose.yml -f docker-compose.local.yml ...
  ```

- Build only `app`; `migrate` must reuse the same `yuralume-local/app:custom`
  image.
- Do not run `docker compose pull` for every service while the local override
  is active. Pull only upstream-managed support services explicitly.
- A source merge does not automatically update the installer-managed Compose
  base. Review upstream self-host release notes separately before changing it.
- After a verified source, deployment, or upstream update, append a concise,
  non-sensitive entry to `UPDATE_PROGRESS_LOG.md`. Do not write secrets,
  message content, or database rows into that log.

## Persistent Change References

- Before starting a non-trivial implementation that spans multiple files,
  services, persistence surfaces, migrations, user-visible behavior, or a
  deployment boundary, create or update a scoped Markdown implementation
  reference in this repository.
- The reference is required before any code, migration, data, or deployment
  operation. Re-read it in the current context before editing; chat history,
  a condensed handoff, or an earlier failed patch is not a durable substitute.
- Include the problem, agreed scope, explicit non-goals, immutable-data rules,
  affected components, migration and compatibility plan, test cases,
  deployment status, and an ordered implementation checklist. Record later
  design decisions there before implementing them.
- Keep the reference factual, non-sensitive, and narrowly scoped. Update it
  when a discovery changes the approved design or execution order.
- For the current post-turn meeting and promise synchronization repair, the
  authoritative reference is
  COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md. Read it before
  changing that behavior, and do not replace it with a large
  context-dependent patch.
- For the current repair's execution state, read `待修.md` and
  `.codex-round.md` after checking `git status` and the latest commit. Update
  `.codex-round.md` after each verified small step with the exact next action,
  test result, changed files, and any blocker. Do not restart completed
  inventory after context compaction.

## Safety Checks

- Before an update that may run migrations, create and verify a PostgreSQL
  custom-format dump in `C:\Entertainment\yuralume\backups`.
- Verify `docker compose ps` and `http://127.0.0.1:8012/health` after every
  deployment.
- Keep changes narrowly scoped. Do not modify character records, chat history,
  schedules, deferred intents, or scheduled promises unless the user
  explicitly asks for that data change.
- Do not expose secrets in `.env.container`, provider connections, logs, or
  command output.
