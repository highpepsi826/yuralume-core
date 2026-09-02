# Yuralume on Zeabur

This directory describes the production topology for the personal
`local/customizations` fork. It intentionally contains no credential, dump,
upload, or user data.

## Service Layout

Create one Zeabur project with these services:

| Service | Deployment source | Private port | Persistent paths |
| --- | --- | --- | --- |
| `postgres` | `ghcr.io/yuralume/yuralume-core/postgres:<pinned-tag>` | `5432/TCP` | `/var/lib/postgresql/data` |
| `storage` | `ghcr.io/yuralume/yuralume-core/storage-local:<pinned-tag>` | `9000/TCP` | `/data` |
| `app` | GitHub fork, branch `local/customizations` | `8002/HTTP` | none |
| `whatsapp-sidecar` | optional `ghcr.io/yuralume/yuralume-core/whatsapp-sidecar:<pinned-tag>` | `32190/TCP` | `/data/auth`, `/data/media` |

Use the same pinned image tag for `postgres`, `storage`, and the optional
sidecar. Do not use `latest` after the initial empty-stack validation.

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

The Yuralume schema requires PostgreSQL 16 with `pgvector`. The listed image
includes the `vector` extension initializer. Before moving any real data, run
this command in the database service and require one row:

```sql
SELECT extname FROM pg_extension WHERE extname = 'vector';
```

Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` only in the
database service. The app receives the resulting asyncpg URL through
`DATABASE_URL`.

## Storage Service

Set `YURALUME_STORAGE_ROOT=/data`, `STORAGE_KEY`, and
`STORAGE_PUBLIC_URL` in the storage service. `STORAGE_PUBLIC_URL` must be the
public app URL, not a public storage URL: the app proxies `/v1/public/*` while
the storage service stays private.

The `/data` volume holds both object bytes and metadata. Restoring only the
database will leave existing image, attachment, feed, and TTS references
broken.

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
