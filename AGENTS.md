# Local Self-Host Instructions

Read `LOCAL_CUSTOMIZATION_WORKFLOW.md` before modifying this repository or the
local Yuralume deployment.

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
