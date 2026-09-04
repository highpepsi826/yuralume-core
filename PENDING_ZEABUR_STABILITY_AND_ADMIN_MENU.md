# Zeabur Stability and Pending Follow-ups Follow-up

## Status

Planning reference created 2026-09-04. The pending-follow-ups navigation fix is
complete. The streaming/resource work is approved for implementation after the
Zeabur host was upgraded to 4 vCPU / 8 GB RAM / 70 GB disk on 2026-09-04.
Production rollout remains a separate, explicit step after local verification.

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
4. Add end-to-end streaming upload for large backup artifacts and staged
   restore uploads: an additive object-storage capability, a shared app-side
   file/stream uploader, raw chunked HTTP transport, chunked storage-service
   ingestion with incremental size/hash accounting, and focused
   adapter/service/export/import tests.
5. Set measured Pod memory requests/limits for the upgraded Zeabur host in a
   separate deployment step and document the applied values in the runbook.

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
- Streaming pass: `contracts/object_storage.py`,
  `infrastructure/storage/http.py`, `infrastructure/storage/in_memory.py`,
  `storage_service/app.py`, shared application upload helper,
  `application/services/character_backup_export_service.py`,
  `application/services/character_backup_import_service.py`, and related
  tests/Docker image publishing.

## Test and verification plan

- Run the focused frontend navigation test(s), TypeScript check, and frontend
  build for the menu change.
- Run focused backup-export/import and storage adapter/service tests, including
  a large-file path that verifies bounded buffering, incremental SHA-256, and
  unchanged artifact bytes.
- Run `git diff --check` after each small step.
- Before any production rollout, verify the app-only deployment and separately
  verify the storage image if that image changed.

## Ordered checklist

1. Create this reference before source edits. **Complete**
2. Remove the accidental debug-only gate from the pending-follow-ups menu/home
   entry and route; preserve all admin authorization. **Complete**
3. Add and run focused frontend regression coverage. **Complete**
4. Commit the narrow menu fix and record it in `UPDATE_PROGRESS_LOG.md`.
   **Complete**
5. Design and implement end-to-end streaming upload. **Complete**
6. Publish and deploy the reviewed app plus pinned personal-fork
   `storage-local` image. **Complete**
7. Measure and set Pod resource requests/limits in Zeabur. **Deferred**

## Deployment status

The app revision containing the streaming client and admin navigation repair is
deployed. On 2026-09-04 the existing `storage` service was switched to
`ghcr.io/highpepsi826/yuralume-core/storage-local:sha-347c951`,
`YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648` was added, and the service was
restarted. The existing `storage-data` volume stayed mounted at `/data`; no
storage data, database row, schema, Telegram setting, or service identity was
recreated.

## Implementation decisions (2026-09-04)

- `SupportsObjectStreamUpload.put_stream` is optional and remains outside
  `ObjectStoragePort`; adapters and test doubles without it continue to use
  `put_bytes`.
- The HTTP adapter sends `PUT /v1/objects/stream/{object_key}` with a raw
  async byte stream. Content type and JSON metadata travel in dedicated
  headers, so multipart encoding cannot buffer the archive in the app.
- The storage service writes the request stream to a per-object temporary file,
  enforces `max_object_bytes` while receiving it, computes SHA-256
  incrementally, and publishes metadata only after an atomic object replace.
- Export and import staging share a file uploader that reads at most one
  `DEFAULT_STREAM_CHUNK_BYTES` chunk at a time. The compatibility fallback is
  intentionally retained for adapters that only implement `put_bytes`.
- The upgraded 8 GB host permits a separately measured resource policy, but no
  Zeabur resource setting is changed until the code pass and local tests are
  complete.

## Streaming implementation checkpoint (2026-09-04)

- Source implementation is complete in the optional `put_stream` capability,
  shared file uploader, HTTP adapter, in-memory adapter, storage service, and
  CB2/CB3 services.
- Storage's default object ceiling is now 2 GiB, matching the backup import
  contract; a Zeabur storage service should set
  `YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648` explicitly.
- Verification: 97 storage/variant/uploader tests and 100 storage-service/
  backup export/import tests passed; Python compilation and `git diff --check`
  passed.
- GitHub Actions published the personal-fork `storage-local` image from build
  revision `347c951`, which contains the streaming implementation from
  `af31c37`. Zeabur pulled that exact pinned tag and started it successfully.
- Production verification passed: storage is `Running 1/1`; repeated storage
  `/health` probes returned 200; `storage-data` remains mounted at `/data`;
  existing `objects/` and `metadata/` trees and a representative character
  image remained readable; app and PostgreSQL are `Running 1/1`; public
  `/health` returned `status=ok` with the database overlay active.
- Next action: measure and set explicit Pod resource requests/limits. A real
  multi-GB backup rehearsal remains optional and must run in a controlled
  window; it was intentionally not triggered as part of this image switch.

## Menu-fix verification checkpoint

- Focused Vitest: `adminLayoutDrawer.test.ts` and
  `adminFollowUpsNavigation.test.ts`, 14 tests passed.
- Type check: `frontend/node_modules/.bin/vue-tsc.cmd -b` passed.
- Frontend build: Vite production build passed. The local Node runtime emitted
  a version advisory only; it did not fail the build.
- Production deployment: complete in app build `347c951`; authenticated admin
  navigation remains protected by the existing backend authorization.
