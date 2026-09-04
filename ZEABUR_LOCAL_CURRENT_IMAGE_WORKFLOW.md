# Zeabur `local-current` Image Workflow

## Problem

The hosted `storage` service currently uses an immutable image tag. That is
safe for rollback but requires a manual Zeabur tag edit whenever local storage
code changes. The upstream `latest` tag must remain reserved for images built
from `main`/`master`, so the personal deployment needs a separate moving tag.

## Agreed scope

- Publish `local-current` from `local/customizations` as the moving personal
  deployment tag.
- Continue publishing `sha-<short-commit>` for immutable audit and rollback.
- Leave `latest` owned exclusively by `main`/`master` and manual releases that
  explicitly request it.
- Point the existing Zeabur `storage` service at the personal-fork
  `storage-local:local-current` image once its first successful publication is
  verified.
- Automate the Zeabur storage restart after image publication when a CI token
  is explicitly authorized and stored as a GitHub Actions secret.
- Update deployment documentation and checkpoints to describe the moving-tag
  workflow and rollback path.

## Explicit non-goals

- Do not create a Git branch named `sha` or `local-current`; these are OCI
  image tags only.
- Do not overwrite the upstream `latest` tag from `local/customizations`.
- Do not recreate the Zeabur `storage` service or its volume.
- Do not change `/data`, `STORAGE_KEY`, database state, Telegram ownership,
  public networking, or backup formats.
- Do not run a production backup merely to test the deployment workflow.
- Do not create or expose a Zeabur API token without action-time confirmation.

## Immutable data and rollback rules

- The existing `storage-data` volume must remain mounted at `/data` throughout
  every image update.
- A moving `local-current` tag is never sufficient evidence for rollback.
  Every publication must also retain its immutable `sha-<short-commit>` tag.
- Rollback changes only the container image reference; it does not restore or
  rewrite the volume, environment variables, or database.
- Do not deploy a storage image unless the matching app/storage protocol is
  backward-compatible or the rollout order has been explicitly controlled.

## Affected components

- `.github/workflows/publish-images.yml`
- `AGENTS.md`
- `deploy/zeabur/README.md`
- `.codex-round.md`
- `UPDATE_PROGRESS_LOG.md`
- Zeabur `storage` image reference after the first `local-current` image is
  verified
- GitHub Actions secret for Zeabur CLI authentication, only after explicit
  confirmation

## Compatibility and deployment plan

1. Add `local/customizations` to the image workflow trigger.
2. Resolve the moving tag by source: `local-current` for
   `local/customizations`, `latest` for `main`/`master`, and the explicit input
   for manual runs.
3. Publish the moving tag and `sha-<short-commit>` together from the same build.
4. Keep all existing multi-architecture output and GHCR authentication.
5. Verify the workflow syntax and inspect the first successful GHCR package
   publication before changing Zeabur.
6. Change the existing Zeabur service from its immutable tag to
   `local-current`, preserving the service, variables, and volume.
7. Once a Zeabur CI token is explicitly authorized, store it only as a GitHub
   Actions secret and add a post-publication non-interactive storage restart.
8. Verify the pulled tag in runtime logs, `Running 1/1`, `/data` contents,
   public app health, PostgreSQL health, and representative media.

## Test cases

- A push to `local/customizations` resolves the moving tag to
  `local-current`.
- A push to `main` or `master` resolves the moving tag to `latest`.
- A manual run uses the requested tag.
- Every run also publishes `sha-<short-commit>`.
- Workflow YAML parses and `git diff --check` passes.
- Zeabur retains `storage-data` at `/data` after the one-time tag switch.
- Without a configured Zeabur token, image publication succeeds but automatic
  restart is explicitly skipped or remains a documented manual step.

## Deployment status

Workflow and documentation changes are implemented locally. The YAML parses,
both publish/restart jobs are present, and `git diff --check` passes. No GitHub
secret, Zeabur service, environment variable, volume, or production data has
been changed by this reference yet.

## Ordered checklist

1. Record the agreed design and safety boundaries. **Complete**
2. Modify and validate the image publishing workflow. **Complete**
3. Update the hosted deployment documentation. **Complete**
4. Commit and push `local/customizations`. **Pending**
5. Verify `local-current` and immutable SHA tags in GHCR. **Pending**
6. Switch the existing Zeabur storage service to `local-current`. **Pending**
7. Create/store the Zeabur CI token after action-time confirmation. **Pending**
8. Add and verify automated Zeabur restart and post-deploy health checks.
   **Pending**
