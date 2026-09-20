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

The production deployment uses explicit process roles. The public `app` service
uses `YURALUME_PROCESS_ROLE=api`, `YURALUME_BACKGROUND_BACKEND=postgres`,
`YURALUME_BACKGROUND_SHADOW=postgres`, and
`YURALUME_REALTIME_BACKEND=postgres`. Run these roles from the same image and
the same database:

| Service | `YURALUME_PROCESS_ROLE` | Background | Realtime | Durable chat worker |
| --- | --- | --- | --- | --- |
| `app` | `api` | `postgres` + shadow `postgres` | `postgres` | `false` |
| `coordinator` | `coordinator` | `postgres` + shadow `postgres` | `memory` | `false` |
| `worker` | `worker` | `postgres` + shadow `postgres` | `postgres` | `true` |
| `connector` | `connector` | `embedded` | `memory` | `false` |

Every service must set `DATABASE_URL`. The connector uses shared account leases,
inbound receipts, and delivery ledgers even though it does not consume the
background queue. A local debugger or secondary notebook must not start another
runtime against this database.

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

### Zeabur native backup format

Zeabur's PostgreSQL `createBackup` result is a platform archive, not a direct
`pg_dump -Fc` file. The presigned object name may end in `.sql.gz`, but the
download can be a ZIP containing `data/_manifest.json` and `data/data.sql`.
Treat the backup as unverified until all of these gates pass:

1. Poll the Zeabur backup job to `SUCCESS` and record its ID, reported size,
   timestamp, and SHA-256 of the downloaded archive.
2. Inspect the archive and manifest without placing plaintext SQL on the host
   filesystem. Restore `data/data.sql` into a new PostgreSQL 18/pgvector
   disposable cluster.
3. Run the schema/revision queries against that restored database.
4. Create a derived PostgreSQL custom-format dump from the restored database,
   run `pg_restore --list`, and restore that derived dump into a second
   disposable database. Preserve both hashes and the restore logs.

The native archive itself must not be passed directly to `pg_restore --list`.
A successful Zeabur backup job without a successful disposable restore is a
no-go for migration.

## Production Schema Revision Verification

The public `/health` endpoint does not prove the Alembic revision. Verify the
revision from a shell that uses the same `DATABASE_URL` as the app, or from a
temporary database client attached to the private PostgreSQL hostname. This is
a read-only check and must happen after the backup has been created, but before
any migration command:

```sql
SELECT version_num FROM alembic_version ORDER BY version_num;

SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('chat_turn_commands', 'chat_turn_effects')
ORDER BY tablename;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('chat_turn_commands', 'chat_turn_effects')
ORDER BY tablename, indexname;
```

The source head expected by this implementation is `u9e7b2a11059`, with
`t8d6f1a10058` immediately before it. The local source can show the expected
chain without touching a database:

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history | Select-Object -First 3
```

Run the same read-only queries against the restored disposable backup. The
following cases stop the rollout and require review: more than one unexpected
head, a production revision that is ahead of the image, a missing or divergent
migration branch, a backup restore whose revision differs from the source
snapshot, or an existing `chat_turn_commands` / `chat_turn_effects` table with
an incompatible definition. Do not use `alembic downgrade` to make Prod match
the source. Resolve the revision difference and prepare a separate controlled
migration plan first.

`alembic current` is an equivalent application-level check when run with the
production image and private `DATABASE_URL`; it must be executed in a one-off
read-only command context, never by starting a second scheduler or worker.

## Durable Same-Space Chat Rollout

The durable same-space chat implementation is currently source-only. The
production app, database schema, and feature flags must remain unchanged until
the following evidence exists in an isolated or maintenance window:

1. A fresh Zeabur native backup is created and restored into a disposable
   PostgreSQL 18/pgvector instance. Verify the archive manifest and real SQL
   restore, then create a derived custom-format dump and verify it with
   `pg_restore --list` plus a second restore. Do not pass the native Zeabur
   archive directly to `pg_restore`.
2. Alembic revisions `t8d6f1a10058` and `u9e7b2a11059` are applied once to the
   target database. Confirm the two tables, the owner/client idempotency
   constraint, the active-conversation partial index, and the effect indexes.
3. A compatible app image is deployed with the new schema while both
   `YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED` and
   `YURALUME_DURABLE_CHAT_WORKER_ENABLED` remain `false`. The legacy SSE route
   must still pass its health and chat regression checks.
4. A separate `worker` service is prepared from the same image with
   `YURALUME_PROCESS_ROLE=worker`, `YURALUME_BACKGROUND_BACKEND=postgres`, and
   `YURALUME_DURABLE_CHAT_WORKER_ENABLED=true`. It must have no public API
   domain, must report private health, and must be the only foreground worker
   owner during the rehearsal. Do not enable the flag on the existing `all`
   replica at the same time.
5. Run authorized test turns against a test character: submit, lose the ACK,
   restart the API, stop/restart the worker at each phase, reconnect from a
   second device, and verify one command, one user append, one assistant
   append, and one post-turn effect intent. Leave
   `VITE_DURABLE_CHAT_ENABLED=false` until these checks pass.
6. Enable the backend acceptance flag first, then the frontend build flag for
   a small authorized cohort. Keep the legacy route available for rollback,
   but never fall back to it after a durable submission has an unknown ACK.

Rollback closes the durable acceptance flag and frontend build flag, keeps the
worker available until all accepted commands are terminal or explicitly fenced
for reconciliation, and leaves the additive schema in place. It does not run a
destructive Alembic downgrade. Any production backup, migration, Zeabur
service creation, secret entry, or flag change requires a fresh operator
decision immediately before that operation.

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
