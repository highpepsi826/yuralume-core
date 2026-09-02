# Zeabur Deployment Implementation Reference

## Problem

The current Yuralume runtime is hosted on a Windows machine that cannot stay
online continuously. The deployment needs one always-on production owner while
preserving a safe local and secondary-notebook development workflow.

## Agreed Scope

- Prepare a Zeabur deployment definition for the existing Yuralume fork.
- Run production on Zeabur as one active application runtime with PostgreSQL,
  HTTP object storage, and the optional WhatsApp sidecar.
- Move the current production database and object-storage data only after an
  explicit user confirmation at the data-transfer step.
- Keep this repository's `local/customizations` branch as the source of code
  deployments.
- Define a repeatable production-snapshot-to-isolated-development workflow.

## Explicit Non-Goals

- Do not place secrets, database dumps, uploads, Docker volumes, or provider
  credentials in Git.
- Do not expose PostgreSQL or the storage service publicly for routine local
  development.
- Do not run two default `all` application instances against the same live
  database.
- Do not alter character records, conversations, schedules, memories, or any
  other live user data during deployment preparation.
- Do not replace the installer-managed local Compose files.

## Runtime Topology

The Zeabur project has independent services connected only on its private
network:

1. `app`: the public Yuralume service, one replica, port 8002.
2. `postgres`: PostgreSQL 16 with the `vector` extension and a dedicated
   persistent volume.
3. `storage`: the bundled HTTP object-storage service, port 9000, with its
   own persistent `/data` volume.
4. `whatsapp-sidecar`: optional service with separate auth/media volumes,
   deployed only when WhatsApp is enabled.

The public app origin proxies `/v1/public/*`; object storage itself remains
private. The existing application Dockerfiles are under `docker/`, so a
Zeabur build must select the precise Dockerfile or use prebuilt images.

## Data and Secret Rules

- The migration unit is a PostgreSQL custom-format dump plus the complete
  object-storage `/data` tree, including `objects` and `metadata`.
- A fresh verified dump is required immediately before migration or any
  schema-affecting deployment.
- `CONFIG_ENCRYPTION_KEY` must be retained securely for production if the
  existing encrypted Admin provider configuration is to remain usable.
- Database credentials, storage credentials, JWT secret, API keys, and
  provider keys are set only in Zeabur service environment variables.
- A migration manifest records timestamp, Git SHA, Alembic revision, file
  hashes, and object counts, but never secrets or user content.

## Compatibility and Migration Plan

1. Deploy an empty cloud topology and verify `CREATE EXTENSION vector`, storage
   read/write, the migration command, and `/health` before transferring data.
2. Configure a stable HTTPS app domain, production `APP_BASE_URL`, and
   authenticated access before making the app public.
3. Take a final consistent source snapshot while the local app is stopped or
   otherwise prevented from writing.
4. Restore PostgreSQL, restore storage data, then run Alembic exactly once
   against the target database.
5. Verify the expected schema revision, health endpoint, media reads, and the
   minimum end-to-end chat flow before switching webhooks or normal traffic.
6. Retain the local source runtime unchanged until the cloud cutover is
   accepted. Rollback means stop the cloud app and restore the verified source
   runtime or a known-good cloud backup; never run both as writers.

## Development Data Workflow

- Normal development uses an isolated local database and storage volume.
- For a production bug, produce or retrieve a labelled production snapshot and
  restore it locally. Disable external connectors and use non-production
  provider credentials in the clone.
- Deploy code and reviewed migrations through Git; do not copy a development
  database back onto production.

## Validation

- Validate the Zeabur Template or service definitions without secrets.
- Build each selected Dockerfile remotely or through the existing CI images.
- On the empty stack: verify pgvector, `alembic upgrade head`, storage API,
  app `/health`, and authenticated browser access.
- After data migration: compare dump restore status, object count, app health,
  one representative media URL, and current Alembic revision.
- Record non-sensitive deployment status in `UPDATE_PROGRESS_LOG.md` only
  after a verified cutover.

## Deployment Status

Preparation started on 2026-09-02. The non-secret runbook and application
environment template now live under `deploy/zeabur/`; a filled environment
file is ignored by Git. The Zeabur account is now signed in and has one
dedicated Tokyo server (`2C / 4 GB`) with an existing SillyTavern project, plus
one suspended legacy shared-cluster project that is not suitable for new
services. No Yuralume project, service, secret, database dump, upload, or
production data transfer has been created by this work item yet.

## Ordered Checklist

1. Complete: add the version-controlled Zeabur deployment assets and
   validation notes.
2. Complete: sign in to the user's Zeabur account and inspect available project
   and billing context without creating resources.
3. Obtain confirmation immediately before creating billable services on the
   Tokyo dedicated server.
4. Create the empty services and persistent volumes; configure non-secret
   topology settings.
5. Obtain confirmation immediately before entering secrets or uploading the
   production database and object-storage data.
6. Execute the migration, validate the cloud runtime, and record the verified
   cutover.
7. Implement the snapshot pull workflow for local and secondary-notebook bug
   reproduction.
