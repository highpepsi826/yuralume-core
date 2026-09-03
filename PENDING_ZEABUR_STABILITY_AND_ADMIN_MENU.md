# Zeabur Stability and Pending Follow-ups Follow-up

## Status

Planning reference created 2026-09-04. The pending-follow-ups navigation fix is
approved for a narrow source change. The memory/resource and streaming work is
deferred until a separate implementation pass and production approval.

## Problems

### Hosted stability

The hosted Tokyo 4 GB server experienced repeated memory-pressure periods and
host reboots. The node has about 2.38 GiB allocatable to Kubernetes workloads,
while the application currently has no memory request or limit. A character
backup export involving about 1.18 GiB of media and 223 files reached its
`upload` stage immediately before the latest pressure period. The export path
currently reads the complete encrypted archive into application memory before
calling object storage, and the storage service currently reads the complete
multipart upload into memory as well.

The earlier application CrashLoopBackOff caused by a PostgreSQL password
authentication error is a separate configuration incident, not the streaming
design problem.

### Admin navigation

The pending-follow-ups backend routes, API client, and
`FollowUpsAdminPage` are present. The sidebar, admin home card, and router
route all mark the page as `debugOnly`. Since `KOKORO_DEBUG_UI_ENABLED` is
false by default, the page is hidden from the admin menu and direct navigation
is redirected. This page is an authenticated operational queue tool, so it
should be visible to authenticated admins while the remaining developer-only
panels stay behind the debug flag.

## Approved scope

1. Reclassify the pending-follow-ups admin page as an ordinary admin
   operational tool in the frontend navigation and router guard.
2. Keep backend `require_admin` protection and character ownership/scoping
   unchanged.
3. Add focused frontend regression coverage for visibility with the debug flag
   off, including the menu entry and direct route metadata.
4. In a later pass, add end-to-end streaming upload for large backup artifacts:
   an additive object-storage capability, an app-side file/stream uploader,
   chunked storage-service ingestion with incremental size/hash accounting,
   and focused adapter/service/export tests.
5. In a separate deployment step, set measured Pod memory requests/limits and
   document the values in the Zeabur runbook.

## Explicit non-goals

- No database schema migration, row repair, or data deletion.
- No change to the `.lumebackup` format, encryption parameters, or restore
  compatibility.
- No change to Telegram polling ownership, scheduler semantics, or channel
  configuration.
- No direct edits inside a live Zeabur container.
- No storage-volume move or data re-migration.
- No enabling of every developer-only admin panel merely to expose
  pending-follow-ups.
- No large backup/export execution during diagnosis or testing.

## Immutable-data and deployment rules

- Work on `local/customizations` in `C:\Entertainment\yuralume-src`.
- Use an isolated local Compose stack for source tests; never point local
  development at the hosted database or storage.
- Keep `put_bytes` as the compatibility path for small objects when adding the
  optional streaming capability.
- Commit and push reviewed source to GitHub. Zeabur rebuilds the app service
  from the branch; it does not deploy the local Compose files.
- A storage-service code change requires a separately published
  `storage-local` image and an explicit Zeabur storage-service update.
- No production migration is expected for these changes. Verify health,
  representative media, admin login, one app replica, and one Telegram polling
  owner after deployment.

## Affected components

- `frontend/src/layouts/AdminLayout.vue`
- `frontend/src/pages/admin/AdminHomePage.vue`
- `frontend/src/router/index.ts`
- `frontend/tests/` navigation regression coverage
- Later streaming pass: `contracts/object_storage.py`,
  `infrastructure/storage/http.py`, `storage_service/app.py`,
  `application/services/character_backup_export_service.py`, and related
  tests/Docker image publishing.

## Test and verification plan

- Run the focused frontend navigation test(s), TypeScript check, and frontend
  build for the menu change.
- Later run focused backup-export and storage adapter/service tests, including
  a large-file path that verifies bounded buffering and unchanged artifact
  bytes.
- Run `git diff --check` after each small step.
- Before any production rollout, verify the app-only deployment and separately
  verify the storage image if that image changed.

## Ordered checklist

1. Create this reference before source edits. **Complete**
2. Remove the accidental debug-only gate from the pending-follow-ups menu/home
   entry and route; preserve all admin authorization. **Complete**
3. Add and run focused frontend regression coverage. **Complete**
4. Commit the narrow menu fix and record it in `UPDATE_PROGRESS_LOG.md`.
   **In progress**
5. Design and implement end-to-end streaming upload in a separate pass.
   **Deferred**
6. Measure and set Pod resource requests/limits in Zeabur, then deploy through
   the reviewed branch/image workflow. **Deferred**

## Deployment status

No production setting, database, storage volume, or Zeabur service has been
modified by this reference.

## Menu-fix verification checkpoint

- Focused Vitest: `adminLayoutDrawer.test.ts` and
  `adminFollowUpsNavigation.test.ts`, 14 tests passed.
- Type check: `frontend/node_modules/.bin/vue-tsc.cmd -b` passed.
- Frontend build: Vite production build passed. The local Node runtime emitted
  a version advisory only; it did not fail the build.
- Production deployment: not performed.
