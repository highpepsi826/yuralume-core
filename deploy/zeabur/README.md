# Yuralume on Zeabur

This directory describes the production topology for the personal
`local/customizations` fork. It intentionally contains no credential, dump,
upload, or user data.

## Current Cutover Status (2026-09-04)

The initial Zeabur cutover is complete. The existing `yuralume-production`
project already contains the active `app`, `storage`, and `postgresql`
services. The obsolete suspended `postgres` service and its `postgres-data`
volume were explicitly deleted on 2026-09-04 after the active database and
off-platform backup were verified. Do not repeat the service-creation or
initial data-migration steps below for this project. Use the hosted workflow in
`AGENTS.md` for ordinary source changes and use the migration sections only for
a planned migration or a new environment.

- The app is running as one production replica at `yuralume-prod.zeabur.app`.
- PostgreSQL is private at `postgresql.zeabur.internal:5432`; public TCP
  forwarding is disabled.
- Storage is private at `http://storage.zeabur.internal:9000`; the complete
  `objects/` and `metadata/` data set has been restored. It runs the
  personal-fork deployment image
  `ghcr.io/highpepsi826/yuralume-core/storage-local:local` with
  `YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648`; the temporary migration
  domain has been removed.
- The first hosted admin account has been configured. Keep the existing
  encryption and rollback backups until an explicit retention decision.

## Service Layout

Create one Zeabur project with these services:

| Service | Deployment source | Private port | Persistent paths |
| --- | --- | --- | --- |
| `postgresql` | `docker.io/pgvector/pgvector:pg18` | `5432/TCP` | `/var/lib/postgresql/18/docker` |
| `storage` | `ghcr.io/highpepsi826/yuralume-core/storage-local:local` | `9000/HTTP` | `/data` (`storage-data`) |
| `app` | GitHub fork, branch `local/customizations` | `8002/HTTP` | none |
| `whatsapp-sidecar` | optional `ghcr.io/yuralume/yuralume-core/whatsapp-sidecar:<pinned-tag>` | `32190/TCP` | `/data/auth`, `/data/media` |

The personal storage deployment follows the moving `local` tag, while
every publication also retains an immutable `sha-<commit>` rollback tag.
`latest` is reserved for `main`/`master`; never use it for personal-fork
production. App and storage revisions must remain protocol-compatible, while
the PostgreSQL and optional sidecar images have independent version lines.

Volumes belong to one Zeabur service only. The app reaches the database and
storage through the private hostnames shown in each service's Networking page;
do not publish the database or storage port.

## App Service

Create `app` as a Git service from the personal fork. Select the
`local/customizations` branch and set this build variable:

```text
ZBPACK_DOCKERFILE_PATH=docker/app/Dockerfile
```

Expose port `8002` as HTTP and bind a generated Zeabur domain first. A custom
domain can be added after the empty stack succeeds. Copy
`production.env.example` into the Zeabur service environment editor, replacing
only the placeholders with service-private hostnames and secrets.

The app service must remain one production replica using the default `all`
process role. A local debugger or secondary notebook must not start another
default runtime against this database.

## Database Service

The current production database runs PostgreSQL 18 with `pgvector`. The listed
image includes the `vector` extension. Before moving any real data into a new
environment, run this command in the database service and require one row:

```sql
SELECT extname FROM pg_extension WHERE extname = 'vector';
```

Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` only in the
database service. The app receives the resulting asyncpg URL through
`DATABASE_URL`.

## Storage Service

Set `YURALUME_STORAGE_ROOT=/data`, `STORAGE_KEY`, and
`STORAGE_PUBLIC_URL` in the storage service. Set
`YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648` there as well: it matches the
application's 2 GiB `.lumebackup` import cap, while the streaming endpoint
keeps the transfer bounded in memory. `STORAGE_PUBLIC_URL` must be the
public app URL, not a public storage URL: the app proxies `/v1/public/*` while
the storage service stays private.

The `/data` volume holds both object bytes and metadata. Restoring only the
database will leave existing image, attachment, feed, and TTS references
broken.

For a storage-code rollout, GitHub Actions publishes `local` plus an
immutable SHA tag, then restarts the existing `storage` service when the
`ZEABUR_TOKEN` Actions secret is configured. Preserve `storage-data`, its
`/data` mount, and all existing variables. Afterward verify `Running 1/1`,
successful `/health` probes, both `/data/objects` and `/data/metadata`, and a
representative media URL through the public app proxy.

If the automated restart is not configured or fails, the published image is
safe but inactive until the existing service is restarted. Do not recreate the
service. For rollback, temporarily replace `local` with the last
known-good `sha-<commit>` tag; changing the image does not roll back volume or
database data.

## Migration Gate

Zeabur does not deploy the local Docker Compose file, so migrations are a
separate release operation:

1. Start the empty PostgreSQL and storage services.
2. Create the app service with its public domain but do not move user data.
3. Run `alembic upgrade head` once through the app service's command panel.
4. Verify `GET https://<app-domain>/health` and the `vector` extension.
5. Only after an explicit data-transfer confirmation: make a fresh local
   PostgreSQL custom-format dump, archive the complete storage data, import
   both, rerun `alembic upgrade head`, and validate the cloud app.

Never run a migration simultaneously from local and cloud environments.

## Required Confirmation Points

- Creating the four services and volumes can create Zeabur charges.
- Entering the values marked `CHANGE_ME` in the environment template sends
  secrets to Zeabur.
- Uploading the production dump and storage archive sends private application
  data to Zeabur.

Each action needs a fresh user confirmation immediately before it occurs.

## Post-Cutover Workflow

- Commit and push local code to `local/customizations`; Zeabur rebuilds the app
  from that branch.
- For a production bug, take or retrieve a labelled cloud snapshot and restore
  it into an isolated notebook/local stack. Disable external connectors there.
- Deploy reviewed code and migrations back to Zeabur. Never overwrite
  production from a development database.
- Keep an off-Zeabur encrypted database-plus-storage backup. Platform backups
  are useful but are not the sole retention mechanism.
