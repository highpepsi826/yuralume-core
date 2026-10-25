# Zeabur `local` Image Workflow

## Problem

The hosted `storage` service currently uses an immutable image tag. That is
safe for rollback but requires a manual Zeabur tag edit whenever local storage
code changes. The upstream `latest` tag remains reserved for images built from
`main`/`master`, so the personal deployment uses a separate moving tag.

## Agreed scope

- Publish `local` from `local/customizations` as the moving personal deployment tag.
- Continue publishing `sha-<short-commit>` for immutable audit and rollback.
- Leave `latest` owned exclusively by `main`/`master` and explicit manual releases.
- Point the existing Zeabur `storage` service at `storage-local:local` after its first successful publication.
- Automate the Zeabur storage restart only when a CI token is explicitly authorized and stored as a GitHub Actions secret.

## Explicit non-goals

- Do not create a Git branch named `sha` or `local`; these are OCI image tags only.
- Do not overwrite upstream `latest` from `local/customizations`.
- Do not recreate the Zeabur `storage` service or its volume.
- Do not change `/data`, `STORAGE_KEY`, database state, Telegram ownership, public networking, or backup formats.
- Do not create or expose a Zeabur API token without action-time confirmation.

## Immutable data and rollback rules

- Keep the existing `storage-data` volume mounted at `/data` for every image update.
- A moving `local` tag is not sufficient evidence for rollback; every publication also retains `sha-<short-commit>`.
- Rollback changes only the container image reference, not the volume, environment variables, or database.

## Compatibility and deployment plan

1. Trigger the image workflow from `local/customizations`.
2. Resolve `local` for `local/customizations`, `latest` for `main`/`master`, and the explicit input for manual runs.
3. Publish the moving tag and `sha-<short-commit>` together from the same build.
4. Verify workflow syntax and the first GHCR publication before changing Zeabur.
5. Change the existing Zeabur service to `local`, preserving variables and volume.
6. Verify the pulled tag, `Running 1/1`, `/data` contents, public app health, PostgreSQL health, and representative media.

## Test cases

- Push to `local/customizations` resolves to `local`.
- Push to `main` or `master` resolves to `latest`.
- Manual runs use the requested tag.
- Every run also publishes `sha-<short-commit>`.
- Workflow YAML parses and `git diff --check` passes.
- Zeabur retains `storage-data` at `/data` after the tag switch.
- Without `ZEABUR_TOKEN`, publication succeeds and restart is explicitly skipped.

## Deployment status

Workflow and documentation changes are implemented locally. No GitHub secret,
Zeabur service, environment variable, volume, or production data is changed by
this reference alone.

## Ordered checklist

1. Record agreed design and safety boundaries. **Complete**
2. Modify and validate workflow. **Complete**
3. Update hosted deployment documentation. **Complete**
4. Commit and push `local/customizations`. **Pending**
5. Verify `local` and immutable SHA tags in GHCR. **Pending**
6. Switch the existing Zeabur storage service to `local`. **Pending**
7. Add and verify automated restart only after token authorization. **Pending**
