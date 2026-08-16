# Local Customization Workflow

This repository is a personal self-host fork of Yuralume. Its purpose is to
keep local behavior changes maintainable while allowing the upstream project to
be updated safely.

`UPDATE_PROGRESS_LOG.md` is the permanent, non-sensitive record of completed
updates, deployments, and outstanding follow-ups. Do not duplicate that
history in this document or in chat.

## Repository Policy

- `main` is an upstream mirror. Do not make local commits directly on it.
- `local/customizations` contains every local code or prompt change.
- `origin` points to the personal fork:
  `https://github.com/highpepsi826/yuralume-core.git`
- `upstream` points to the original project:
  `https://github.com/Yuralume/yuralume-core.git`
- Keep local changes small, scoped, and committed with a `local:` prefix.
- Never commit `.env.container`, API keys, database dumps, uploads, or Docker
  volumes.

## Deployment Layout

```text
C:\Entertainment\yuralume\      Runtime Compose files, .env.container, uploads, backups
C:\Entertainment\yuralume-src\  This Git checkout and local source changes
```

The runtime stack uses the published images for PostgreSQL, storage, and the
WhatsApp sidecar. The local Compose override builds only the application image
from this checkout; `migrate` uses that exact same image.

The current storage host port is `127.0.0.1:19012`. Keep it unchanged unless
the Docker Desktop port mapping is deliberately changed and verified.

`C:\Entertainment\yuralume\docker-compose.yml` is an installer-managed
deployment base, not a copy of this repository's root `docker-compose.yml` or
`docker-compose.container.yml`. Those source files use different service and
volume names. Do not replace the runtime base with either source file: Docker
could create a new empty PostgreSQL volume, making the existing data appear to
have disappeared.

## Making a Local Change

1. Work only on `local/customizations`.
2. Make the smallest practical change.
3. Run focused tests or a source build before deployment.
4. Commit the change with a clear message, for example:

   ```text
   local: reduce duplicate deferred intent resurfacing
   ```

5. Push the branch to the personal fork.

Do not edit files inside a running Docker container. Those edits disappear
when the container is recreated.

## Standard Upstream Update Runbook

Use this sequence for a normal upstream release. Start only when
`git status --short` is empty; commit any intentional local work first.

### 1. Back up and review

1. Create and verify a new PostgreSQL custom-format dump under
   `C:\Entertainment\yuralume\backups`. Record only its file name in
   `UPDATE_PROGRESS_LOG.md`.
2. On GitHub, open the personal fork and choose **Sync fork** then
   **Update branch**. This updates `main` only; never use the control on
   `local/customizations`.
3. Read the upstream release notes. If they explicitly change the self-host
   installer, deployment Compose file, or required environment values, stop
   for a separate review. Never overwrite
   `C:\Entertainment\yuralume\docker-compose.yml` with a source Compose
   file.

### 2. Merge the upstream base

Run these commands from the source checkout:

```powershell
Set-Location C:\Entertainment\yuralume-src
git status --short
git fetch origin upstream --tags
git switch main
git pull --ff-only origin main
git switch local/customizations
git merge --no-edit main
```

Use `merge` for this personal fork. It preserves a visible update boundary and
does not require force-pushing the custom branch. If a merge conflict occurs,
stop and resolve it deliberately; do not discard local commits or choose
`ours`/`theirs` blindly.

### 3. Refresh support images, build, and deploy

Run these commands from the runtime directory:

```powershell
Set-Location C:\Entertainment\yuralume

docker compose --env-file .env.container `
  -f docker-compose.yml pull postgres storage-local whatsapp-sidecar

docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml build app

docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml up -d
```

Do not run a blanket `docker compose pull` with the local override enabled:
`yuralume-local/app:custom` exists only on this machine and must be built, not
pulled.

### 4. Verify, push, and record

```powershell
docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml ps
Invoke-RestMethod http://127.0.0.1:8012/health

Set-Location C:\Entertainment\yuralume-src
git push origin local/customizations
```

Confirm the application health endpoint succeeds and the expected services are
healthy in Docker Desktop. Then append an entry to `UPDATE_PROGRESS_LOG.md`
with the upstream version/commit, backup file name, deployment result, health
result, and any unresolved follow-up.

## Building and Deploying Local Source Manually

Run these commands from the runtime folder, not the source folder:

```powershell
Set-Location C:\Entertainment\yuralume
docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml build app
docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml up -d
```

The local override tags the application image as `yuralume-local/app:custom`.
Do not run a blanket `docker compose pull` with the local override enabled,
because Docker would try to pull that local-only image. To refresh the
unchanged supporting services, pull them explicitly:

```powershell
docker compose --env-file .env.container `
  -f docker-compose.yml pull postgres storage-local whatsapp-sidecar
```

After deployment, verify:

```powershell
docker compose --env-file .env.container `
  -f docker-compose.yml -f docker-compose.local.yml ps
Invoke-RestMethod http://127.0.0.1:8012/health
```

## Backup and Rollback

Before an upstream merge or database migration, create a PostgreSQL custom
format dump under `C:\Entertainment\yuralume\backups`.

Keep the previous Git commit available. If a local source build fails, switch
back to the prior known-good `local/customizations` commit, rebuild `app`, and
run Compose again. Restore the database dump only when a migration itself
caused an incompatible schema or data regression.

## Recording Work

Use `UPDATE_PROGRESS_LOG.md` for every completed update, deployment, rollback,
or meaningful local behavior change. Keep the entry factual and non-sensitive.
