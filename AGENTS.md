# Yuralume Development and Deployment Instructions

Read `LOCAL_CUSTOMIZATION_WORKFLOW.md` before modifying this repository or the
local Yuralume deployment.

## Current Hosted Production

OVHcloud/Coolify is the accepted production runtime as of 2026-10-18. Read
`C:\Users\high_\Documents\ChatGPT\ai_livelife\deployment\ovh-yuralume\PLAN.md`
and `OVHCLOUD_DEPLOYMENT_STATUS.md` before a production operation.

- Public application: `https://yuralume.tototoproject.com`.
- Coolify service: `yuralume` (`lg4wotyohbnhgs5y2mlhwb5z`) with six services:
  `postgresql`, `storage`, `app`, `coordinator`, `worker`, and `connector`.
- The four app roles use an explicitly selected immutable GHCR image digest.
  Database/storage volumes and secrets must be preserved for an app update.
- Zeabur program services are stopped and retained for rollback evidence only.
  Do not restart them or treat the historical Zeabur workflow step as a deploy.

## Hosted Development and Deployment

- Edit source in `C:\Entertainment\yuralume-src` and push reviewed commits on
  `local/customizations`. GitHub Actions `Publish container images` publishes
  the moving `local` tag and an immutable `sha-<commit>` tag to GHCR. It does
  not deploy Coolify. Do not edit a running cloud container or treat a manual
  dashboard build as a substitute for a source commit.
- After image publication succeeds, resolve the new immutable digest. Updating
  Coolify's `app`, `coordinator`, `worker`, and `connector` services to that
  digest and deploying them is a separate production action. A later GitHub
  push never changes services pinned to an earlier digest. Preserve the
  `postgresql` and `storage` images, volumes, secrets, and role environments
  for a no-migration app release.
- Once the user authorizes deployment of a named reviewed commit, continue
  through publication, digest selection, Coolify deployment, and verification
  without repeatedly asking which stage to perform. Stop for a new
  migration/data/destructive approval boundary, a material discrepancy, or a
  failed check.
- At each material stage, report and persist: source commit, GitHub Actions
  run/result, published immutable digest, Coolify configuration/deployment
  state, and health/login/representative-media checks. Update
  `UPDATE_PROGRESS_LOG.md` after verified completion; do not wait for the user
  to ask which deployment stage has been reached.
- Local development on this computer or another notebook must use an isolated
  local Compose stack. Never point a default local runtime at the hosted
  database or storage, and never run local Telegram polling or schedulers at
  the same time as the hosted app. There must be exactly one Telegram polling
  owner.
- For a production bug, obtain a labelled encrypted cloud snapshot/export and
  restore it into an isolated local stack. Disable Telegram and other external
  connectors there. Reproduce, test, and repair locally; never write a local
  development database back into production.
- Before any production migration or data operation, read the OVHcloud runbook,
  check the current service status, obtain explicit user confirmation, and
  create and verify a PostgreSQL custom-format backup. Migrations run once in
  a controlled environment; never run Alembic concurrently from local and
  cloud. Prefer an app-only redeploy when no schema change is involved.
- A storage migration must move `objects/` and `metadata/` together. Use the
  staged encrypted transfer procedure in the OVHcloud runbook and do not
  expose plaintext storage during transfer.
- After a Coolify deployment, verify all six services are healthy, `GET
  https://yuralume.tototoproject.com/health` returns `status=ok`, representative
  media can be read, admin login works, and only the live connector owns
  Telegram polling. Only after those checks should a release be accepted.
- Keep `CONFIG_ENCRYPTION_KEY` stable across deployments so encrypted Admin
  provider configuration remains readable. Store all secrets only in Coolify
  variables or local ignored environment files; never commit, log, paste, or
  print them.
- Production uploads, deletes, rollback changes, public-port changes, and
  actions that may incur OVHcloud charges require explicit confirmation at the
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
## Diagnostic export debugging

- The diagnostic download UI should support time ranges (default: recent 1 hour), incident-type presets, and advanced checkboxes for detailed data. Keep full prompts, chat bodies, and credentials opt-in; show estimated size and sensitivity.
- A debug integration may let Codex sign in to and authorize the Yuralume diagnostic page, then fetch a bounded bundle through a protected, read-only diagnostic export API. Scope authorization to admin, short-lived tokens, and explicit export scopes. Fall back to manual download or shared workspace when the connector/session is unavailable.
