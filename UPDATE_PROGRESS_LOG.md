# Update and Progress Log

This is the durable, non-sensitive operating record for this personal
Yuralume self-host. Add new entries at the top after the work is verified.
Do not record API keys, connection strings, chat content, character data, or
database rows.

### 2026-09-04 - Stream large backup transfers within bounded memory

- Status: source implementation complete; Zeabur deployment pending.
- Type: local source stability repair for hosted backup export/import.
- Git result: committed as `b1e910f` on `local/customizations`.
- Fix: added an optional raw `put_stream` object-storage capability, a shared
  bounded file uploader, HTTP chunked request transport, and storage-service
  atomic temp-file ingestion with incremental size/SHA-256 accounting. CB2
  encrypted artifact uploads and CB3 staged uploads now use the capability and
  retain `put_bytes` compatibility for legacy adapters.
- Compatibility: `.lumebackup` bytes, encryption, restore semantics, and
  existing multipart/small-object uploads are unchanged. Storage's default
  object cap is aligned to the 2 GiB backup import cap; Zeabur should set
  `YURALUME_STORAGE_MAX_OBJECT_BYTES=2147483648` on the storage service.
- Data safety: no database schema, storage volume, user data, Telegram state,
  or migration was changed.
- Verification: 97 storage/variant/uploader tests, 100 storage-service/backup
  export/import tests, Python compilation, and `git diff --check` passed.
- Deployment: not performed. Docker CLI/daemon is unavailable on this
  workstation; publish both the app and `storage-local` images from the same
  reviewed revision before changing Zeabur services. Pod resource values for
  the upgraded 4 vCPU / 8 GB / 70 GB host remain pending dashboard review.
- Follow-up: commit/push source, publish pinned images, apply measured Pod
  requests/limits, deploy, and verify health, media, admin login, one replica,
  and one Telegram polling owner.

### 2026-08-30 - Fix proactive intention-judge prompt crash

- Status: completed
- Type: approved local source fix and app-only deployment
- Git result: source fix committed as `c574ddb` on `local/customizations`.
- Fix: corrected the undefined `parts` reference in deferred-intent prompt
  rendering and restored the future revisit-time display. This removes the
  `intention judge raised` crash while preserving existing judgement semantics
  and the real-message 30-minute cooldown.
- Data: no deferred intents, audit history, conversations, schedules, goals,
  memories, or schema rows were changed.
- Backup: `pre-proactive-intention-judge-fix-20260830-163419.dump`, verified as
  PostgreSQL custom format; SHA-256 is recorded in the scoped reference.
- Deployment: built the local app image, ran the existing migrate service
  successfully, and recreated only `app`; support services and volumes were
  retained.
- Verification: 33 intention-judge tests and 77 dispatcher/deferred-intent/
  scheduler tests passed; compile and diff checks passed; all Compose services
  healthy; `/health` returned `status: ok`; Alembic remained at
  `u2c6m8p10046 (head)`; no new post-deployment `NameError` or errored attempt
  appeared in the runtime check.
- Follow-up: monitor the next due deferred-intent evaluation at 17:30 HK.

### 2026-08-30 - Prevent premature first-meeting story completion

- Status: completed
- Type: approved local behavior repair and exact live-data correction
- Git result: guard committed as `81312f3`; repair transaction/script and
  deployment records committed through `173b66c` on `local/customizations`.
- Fix: first-meeting beats now require player presence and the exact live
  schedule start; unattended simulation, raw status shortcuts, and memorialized
  schedule rows cannot complete the meeting. The real-message 30-minute
  proactive cooldown is unchanged.
- Data repair: removed only the known false autonomous realization artifacts,
  restored the affected arc/beat to active/pending, and preserved the separate
  pre-meeting and festival activities plus unrelated projections.
- Backup: `pre-first-meeting-premature-completion-20260830-1517.dump` (verified
  PostgreSQL custom format; SHA-256 is recorded in the scoped reference).
- Deployment: built the local app image, ran the existing migrate service
  successfully, and recreated only `app`; PostgreSQL, storage, WhatsApp
  sidecar, and volumes were retained.
- Verification: all Compose services healthy; `/health` returned `status: ok`;
  Alembic remained at `u2c6m8p10046 (head)`; active-story API shows the pending
  first-meeting beat; the first natural post-restart tick completed without
  simulating that meeting.
- Follow-up: an unrelated proactive intention-judge crash was contained by the
  scheduler during the verification tick and remains outside this repair.

### 2026-08-30 - Restore proactive audit recording after image-guard merge

- Status: completed
- Type: approved local source hotfix and deployment
- Git result: committed `5dc8672` on `local/customizations`.
- Fix: restored the `image_intent` imports used by proactive dispatch and the
  existing truthful fallback when an image commitment has no deliverable
  attachment. The 30-minute real-message cooldown and all data were preserved.
- Backup: `pre-proactive-audit-hotfix-20260830-140137.dump`, verified as a
  PostgreSQL custom-format archive; SHA-256 recorded locally as
  `9C7FE88EB531C83A5521B7EAA43C0C3F8DD773338F5D3580BED6FC6835940C38`.
- Deployment: built `yuralume-local/app:custom` from `5dc8672`, ran the
  existing `migrate` service successfully, and recreated only `app`.
  PostgreSQL, storage, WhatsApp sidecar, and their volumes were retained.
- Verification: all four Compose services healthy; `/health` returned
  `status: ok`; Alembic remained `u2c6m8p10046 (head)`; the next normal
  scheduler tick completed successfully and wrote a new proactive audit row
  at `2026-08-30 14:09:47` HK with no image-guard exception.
- Tests: image-tool suite 15 passed; proactive dispatcher/scheduler/tick suite
  321 passed; source compilation and `git diff --check` passed.
- Follow-up: monitor normal proactive evaluations; no data repair or policy
  change was part of this deployment.

### 2026-08-30 - Deploy queued scheduled-promise admin controls

- Status: completed
- Type: approved local source deployment
- Git result: deployed source commit `6340238` on `local/customizations`.
- Backup: `pre-pending-follow-up-admin-crud-20260830-033122.dump`, verified
  as a PostgreSQL custom-format archive before deployment.
- Deployment: built `yuralume-local/app:custom`, ran the existing `migrate`
  service successfully, then recreated only `app`. PostgreSQL, storage, and
  WhatsApp sidecar containers and volumes were retained.
- Verification: all services healthy; `http://127.0.0.1:8012/health` returned
  `status: ok`; Alembic is `u2c6m8p10046 (head)`; runtime version reports
  `local-customizations` and commit `6340238`; OpenAPI exposes the queued
  scheduled-promise admin CRUD endpoints.
- Follow-up: monitor normal queue operations; no data repair or cooldown
  policy change was part of this deployment.

### 2026-08-29 - Repair legacy meeting and festival projections

- Status: completed
- Type: approved live-data repair and deployment verification
- Git result: committed `f7bf8b7` on `local/customizations`.
- Backup: `legacy-commitment-repair-pre-live-20260829-015633.dump` (verified
  before the live transaction).
- Data repair: applied the approved 17:30 card-handover / 18:00 festival
  identity split, removed the approved obsolete goal and duplicate queued
  promises, and preserved the manually adjusted schedule, historical records,
  and proactive cooldown.
- Deployment: recreated only `migrate` and `app` with the runtime Compose base
  plus local source overlay; existing PostgreSQL, storage, and sidecar volumes
  were retained.
- Verification: isolated rollback/commit rehearsals passed; `migrate` exited 0,
  Alembic reached `u2c6m8p10046`, all services were healthy, and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: monitor the repaired schedule, story, goal, and pending-promise
  views; do not rerun the one-shot repair SQL.

### 2026-08-27 - Prevent early future-event venue visits

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.6.0` (`ce5bc09`)
- Git result: committed locally on `local/customizations`.
- Backup: covered by the verified `pre-schedule-date-fix-20260827-021235.dump`
  backup created before this schedule-fix deployment.
- Deployment: rebuilt and redeployed the local app. A future physical event
  may still inform earlier preparation, but unconfirmed plans and
  carried-forward wishes can no longer schedule travel to, waiting at, or
  attendance at that event venue before its scheduled date. Confirmed shared
  slots remain authoritative.
- Verification: 68 focused schedule tests and source compilation passed; the
  app health endpoint returned `status: ok`. Regenerated the affected gap day
  and the actual event day; the gap day contains no early venue activity and
  the actual day retained its confirmed shared activity.
- Follow-up: none

### 2026-08-27 - Future shared-event date guard

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.6.0` (`ce5bc09`)
- Git result: committed `211a9cb` on `local/customizations`.
- Backup: `pre-schedule-date-fix-20260827-021235.dump`, verified with
  `pg_restore --list` before deployment.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  app/migrate services using the runtime Compose base plus local override.
  Future story events may now inform preparation, but cannot be rendered as
  an early shared activity; manual regeneration preserves confirmed future
  commitments and their structured participant references.
- Verification: 68 focused schedule-planning tests passed; source compilation
  and Docker image build passed; all Compose services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`. Regenerated future
  schedule checks confirmed no early shared activity and retention of the
  confirmed commitment on its actual date.
- Follow-up: `none`

### 2026-08-25 - Durable Telegram outbound retry

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.6.0` (`ce5bc09`)
- Git result: added the outbound delivery ledger and retry worker on
  `local/customizations`; commit pending.
- Backup: `outbound-delivery-fix-20260825.dump`, verified with
  `pg_restore --list` before migration.
- Deployment: created the durable outbound message table, rebuilt
  `yuralume-local/app:custom`, and recreated the existing app/migrate services
  with the runtime Compose base plus local override. Failed channel sends now
  retain a credential-free payload for bounded retry without rerunning the
  LLM turn; segmented replies remain ordered across retries.
- Verification: focused outbound, dispatcher, segmentation, and SQLAlchemy
  tests passed (30 tests); source compilation and frontend syntax checks
  passed; all Compose services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`. Alembic reports
  `t9q4v7x10045 (head)`.
- Follow-up: observe the next real Telegram transport failure; Telegram has no
  universal idempotency key, so a timeout after remote acceptance can still
  produce a rare duplicate on retry.

### 2026-08-23 - Upstream v0.6.0 merge and local deployment

- Status: completed
- Type: upstream update and local-source deployment
- Upstream base: `v0.6.0` (`ce5bc09`)
- Git result: merged `main` into `local/customizations` as `48a1b44`; the
  branch remains local-only and was not pushed.
- Backup: `yuralume-pre-v0.6.0-deploy-20260823-235405.dump`, verified with
  `pg_restore --list` before migration.
- Deployment: rebuilt `yuralume-local/app:custom`, refreshed the published
  PostgreSQL, storage, and WhatsApp images, then ran the local image's
  Alembic migration before recreating the app.
- Data safety: an isolated restore-and-upgrade-and-rollback rehearsal passed
  first. The production migration reached `s9l2c5m10044`; core table counts
  matched the pre-migration baseline, and retired operator status values were
  preserved in the migration archive table before their obsolete columns were
  removed.
- Verification: all four Compose services are healthy, and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: none

### 2026-08-22 - Dual-mode structured Responses relay deployment

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `5bfa7c5` on `local/customizations`.
- Backup: `not required`; this changes outgoing provider request routing only
  and has no schema or user-data migration.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated only the
  existing `app` service. A connection may now use primary
  `chat_completions` with `structured_streaming`: foreground chat remains on
  Chat Completions, while complete background calls use the verified
  structured Responses SSE relay.
- Verification: 59 focused backend tests passed. Docker Compose reported the
  app, PostgreSQL, storage, and WhatsApp services healthy, and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: for the affected source, set protocol to `chat_completions`,
  Responses request profile to `structured_streaming`, leave Max tokens blank,
  and keep Disable upstream streaming off.

### 2026-08-22 - Structured streaming Responses relay compatibility

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `24e240d` on `local/customizations`.
- Backup: `not required`; this changes the outgoing provider request shape
  only and has no schema or user-data migration.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  `migrate` and `app` services using the runtime Compose base plus local
  override. Custom OpenAI-compatible Responses connections can now select
  `structured_streaming`, which always sends the verified structured user
  input with `stream=true`, while omitting instructions, token limits,
  reasoning, and extra request parameters. Background calls collect the same
  SSE stream into their normal text result.
- Verification: 133 focused backend tests, i18n checks, a frontend production
  build, and Docker app build passed. All Compose services are healthy;
  `http://127.0.0.1:8012/health` returned `status: ok` and `/docs` returned
  HTTP 200.
- Follow-up: on the affected provider, select `LLM API protocol: responses`
  and `Responses request profile: structured_streaming`, save, then use the
  ordinary connection test and an actual chat turn.

### 2026-08-22 - Verify streaming Responses payload text

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `93d3265` on `local/customizations`.
- Backup: `not required`; this adds a fixed-prompt diagnostic only and has no
  schema or user-data migration.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  `migrate` and `app` services using the runtime Compose base plus local
  override. The complete Responses payload test lab now verifies that the
  structured `input` plus `stream=true` variant yields readable SSE text,
  rather than treating HTTP 200 alone as success.
- Verification: 39 focused backend tests, Vue type-check, frontend production
  build, and Docker app build passed. All Compose services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: switch to the affected source, set its protocol to `responses`,
  and run the complete Payload test lab; capture the new SSE-text verification
  row before considering a runtime compatibility mode.

### 2026-08-22 - Structured Responses payload probes

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `a716ea5` on `local/customizations`.
- Backup: `not required`; this adds read-only, fixed-prompt diagnostics and
  has no schema or user-data migration.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  `migrate` and `app` services using the runtime Compose base plus local
  override. Complete Responses payload diagnostics now test native structured
  `input` and the same structure with `stream=true`.
- Verification: 38 focused backend tests, frontend i18n checks, and the
  production frontend build passed. All four Compose services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: run the complete Payload test lab against the affected source and
  compare the two structured-input variants with the existing minimal input.

### 2026-08-22 - Responses protocol for custom LLM providers

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed on `local/customizations`.
- Backup: `pre-responses-protocol-20260822-153940.dump`, verified with
  `pg_restore --list` before deployment.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  `migrate` and `app` services with the runtime Compose base plus local
  override. Custom OpenAI-Compatible LLM connections now have an advanced
  `LLM API protocol` setting. The default remains `chat_completions`; selecting
  `responses` sends native `/responses` payloads and parses both non-streaming
  and streaming Responses replies. Payload diagnostics use the selected
  endpoint and request shape. A failed request is never automatically retried
  against the other endpoint.
- Verification: 125 focused backend tests and 11 frontend provider-field tests
  passed; the Docker production build passed. All four Compose services are
  healthy and `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: set the affected custom provider's `LLM API protocol` to
  `responses`, save it, then run `Payload test lab` against that source.

### 2026-08-22 - Exhaustive provider payload test lab deployed

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `ad4259a` on `local/customizations`.
- Backup: `not required`; this change adds read-only diagnostics and no schema
  or user-data migration.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the existing
  `migrate` and `app` services with the runtime Compose base plus local
  override. Provider Settings now exposes `Payload 測試區` for draft and saved
  OpenAI-compatible LLM connections. Complete mode sends the runtime-shaped
  request and controlled variants, progressively removing stream, token,
  reasoning, extra-parameter, and message fields while reporting only field
  names, status, and sanitized error details.
- Verification: focused backend tests (100), frontend provider API tests (8),
  i18n checks, Vue type-check, and production build passed. All four Compose
  services are healthy; `http://127.0.0.1:8012/health` returned
  `{"status":"ok"}` and OpenAPI lists both payload-diagnostic routes.
- Follow-up: run `Payload 測試區` against the failing provider source and use
  the first successful variant to identify the incompatible request field.

## Entry Template

### YYYY-MM-DD - Short update title

- Status: completed, partial, rolled back, or blocked
- Type: upstream update, local customization, deployment, or recovery
- Upstream base: release tag and/or commit
- Git result: branch and merge or commit result
- Backup: file name only, or `not required` with a reason
- Deployment: images or services changed
- Verification: build/test, Compose status, and health endpoint result
- Follow-up: `none` or a concise next action

## Current Baseline

### 2026-08-22 - Progressive OpenAI-compatible payload diagnostics

- Status: deployed
- Type: local customization
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: source changes remain in the working tree; no commit or push was
  requested.
- Backup: `not required`; the diagnostic is read-only and makes no schema or
  provider-row changes.
- Deployment: rebuilt `yuralume-local/app:custom` from the local source and
  recreated only the existing `yuralume-app` container. The admin Provider
  Settings page now has a `Payload diagnostic`
  action for draft and saved LLM connections. It checks `/models`, then sends
  bounded non-stream chat shapes, progressively removing max-token,
  reasoning, extra-parameter, and system-message fields. It stops at the
  first success; each chat probe is capped at 1 token, never returns payload
  contents or secrets, and reports the actual HTTP status (or `FAIL` for
  transport failures).
- Verification: 99 focused backend tests passed; provider-settings frontend
  API tests (6) passed, i18n checks passed, and the production frontend/PWA
  build passed. Runtime `/health` returned `status: ok`; all four Compose
  services were healthy and the OpenAPI document exposed both diagnostic
  routes.
- Follow-up: hard-refresh the browser if its PWA service worker still serves
  the previous bundle, open Provider Settings, run the diagnostic against the
  failing source, and use the first successful shape to adjust the provider
  configuration.

### 2026-08-22 - Optional non-streaming OpenAI-compatible requests

- Status: partial
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `678b487` on `local/customizations`.
- Backup: `not required`; no schema migration or user-data change
- Deployment: source checkout now exposes the advanced `停用上游串流` provider
  setting for OpenAI-compatible LLM connections. When enabled, the adapter
  omits `stream: true` upstream and still serves Yuralume's existing one-chunk
  streaming contract. Runtime deployment is pending because the current
  workstation session has no Docker CLI/Desktop executable available.
- Verification: 98 focused backend tests, all 1,149 frontend tests, i18n
  checks, Vue type-check, and production frontend/PWA build passed. Existing
  runtime `/health` remains `status: ok`; the running app has not yet been
  recreated with this commit.
- Follow-up: rerun the local Compose `app` build/up commands when Docker is
  available, then verify Compose health and the provider setting in the UI.

### 2026-08-21 - Structured schedule involvement and bounded deferrals

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: finalized on `local/customizations`; this entry ships with the
  implementation commit and personal-fork push.
- Backup: `not required`; no schema migration. The authorized settings change
  used the existing owned-character API and did not alter chats, schedules,
  deferred-intent rows, or other characters.
- Deployment: rebuilt `yuralume-local/app:custom` and recreated `migrate` and
  `app` with both runtime Compose files. The proactive intention judge now
  receives structured player schedule-involvement states, and repeated
  deferred motives have a bounded send-or-abandon lifecycle. The hard
  configured cooldown after an actual proactive send remains unchanged.
- Verification: 199 focused and adjacent backend tests passed with one
  integration skip, including the regression that a due deferred alarm cannot
  bypass a recent actual-send cooldown. Python compilation and the production
  Docker build passed. The repository-wide suite remains coupled to inherited
  storage environment values (representative collection failure: HTTP storage
  provider without a test base URL), while the affected suites pass in
  isolation. Browser verification confirmed the existing-character editor
  shows the selected schedule-involvement policy and cold-start permission,
  the normal proactive toggle remains enabled, and no console errors appeared.
  All four Compose services are healthy; storage remains on
  `127.0.0.1:19012`; `/health` returned `status: ok`.
- Follow-up: `none`

### 2026-08-21 - Editable starting relationships and proactive send hardening

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: finalized on `local/customizations`; this entry ships with the
  implementation commit and personal-fork push.
- Backup: `not required`; no schema migration or user-data change
- Deployment: rebuilt `yuralume-local/app:custom` and recreated `migrate` and
  `app` with both runtime Compose files; PostgreSQL, storage, WhatsApp, and
  volumes were unchanged. Manual card uploads and marketplace installs now
  open the starting-relationship wizard before any character is created, and
  existing relationships remain editable from player and admin settings.
- Verification: 79 focused backend tests, the PostgreSQL repository
  integration test, all 1,149 frontend tests, Vue type-check, i18n checks,
  Python compilation, production frontend/PWA and Docker builds passed.
  Browser checks covered upload preview, marketplace install, player/admin
  relationship editing, layout, and console errors without importing or
  saving. All Compose services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: `none`

### 2026-08-18 - Enforce proactive image delivery claims

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `7564cdf` on `local/customizations`; the shared
  image-intent guard now forces `generate_image` for clear photo promises and
  prevents attachment-less delivery claims on chat and proactive surfaces.
- Backup: `not required`; no schema migration or data change
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the local
  `app` and dependency `migrate` services with the runtime Compose files;
  PostgreSQL, storage, WhatsApp sidecar, uploads, and volumes were preserved.
- Verification: focused image/chat/proactive tests passed; Docker build
  succeeded; all runtime services are healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: monitor the next proactive image promise and its tool audit row.

### 2026-08-17 - Reliable image requests from chat and Telegram

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: updated `local/customizations` so Telegram forwards `/pic`,
  explicit natural-language image requests force the image tool, and failed
  or unavailable image generation cannot produce a false delivery claim.
- Backup: `not required`; no schema migration or data change
- Deployment: rebuilt `yuralume-local/app:custom` and recreated only the local
  `app` and `migrate` services; PostgreSQL, storage, WhatsApp sidecar,
  uploads, and volumes were preserved.
- Verification: 56 image/chat/localization tests, 70 chat-service tests, and
  17 Telegram polling tests passed; Docker build succeeded; all Compose
  services were healthy and `http://127.0.0.1:8012/health` returned
  `status: ok`.
- Follow-up: `none`

### 2026-08-17 - Merge same-slot scheduled promises

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `33fcfce` on `local/customizations`; push to the
  personal fork follows this verified deployment record.
- Backup: `yuralume-pre-scheduled-promise-slots-20260817-131953.dump`
  (custom format, verified with `pg_restore -l` before migration)
- Deployment: rebuilt only `yuralume-local/app:custom`, ran migration
  `m5d2r8q10042`, and force-recreated `migrate` then `app`. PostgreSQL,
  storage, WhatsApp sidecar, and their volumes were unchanged.
- Data maintenance: in one verified transaction, consolidated one approved
  pre-existing duplicate scheduled-promise pair into one active delivery with
  both obligations retained; the redundant record is cancelled, not deleted.
- Verification: 80 direct focused tests and 43 adjacent promise-flow tests
  passed; all Compose services are healthy and `/health` returned `status: ok`.
- Follow-up: observe the next scheduled promise delivery; no normal chat path
  gains an additional LLM call from this change.

### 2026-08-17 - Harden Telegram replies and promised-media delivery

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed on `local/customizations` and pushed to the personal
  fork.
- Backup: `pre-messaging-reliability-20260817.dump` (custom format, verified
  with `pg_restore -l` before deployment)
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the local
  application stack. Telegram sends now require an explicit successful API
  acknowledgement before they are recorded as delivered. Malformed successful
  OpenAI-compatible chat responses are retried once, then report a visible
  localized failure instead of silently dropping a reply. Image promises cannot
  be marked completed when no attachment was delivered.
- Verification: 148 focused LLM, dispatcher, promise, and Telegram tests
  passed; Docker build passed; all Compose services were healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: observe normal Telegram conversations and the next image promise;
  no historical chat or character data was changed.

### 2026-08-17 - Deploy proactive messaging and intent lifecycle redesign

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: source commit `0b3c6a2` on `local/customizations`; deployment
  record committed locally and not pushed
- Backup: `pre-proactive-intent-20260817-075116.dump` (custom format,
  verified with `pg_restore -l` before migration)
- Deployment: built `yuralume-local/app:custom` from `0b3c6a2`, ran migrations
  `l4c8p9z10040` and `m5d2r8q10041`, and recreated only `migrate` and `app`.
  PostgreSQL, storage, WhatsApp sidecar, and their volumes were unchanged.
- Verification: all four Compose services are healthy; `/health` returned
  `status: ok`; `/api/v1/system/version` reports image tag
  `local-customizations` and commit `0b3c6a2`.
- Follow-up: observe proactive-attempt reasons and chat/tick latency for one
  day; keep `proactive_frequency` deferred until that observation is complete.

### 2026-08-17 - Proactive messaging and current-intent lifecycle redesign

- Status: completed in source; deployment pending explicit approval
- Type: local customization
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: verified on `local/customizations`; commit is local-only and
  will not be pushed automatically
- Backup: not required yet; a verified PostgreSQL dump is required before the
  additive migrations are deployed
- Deployment: not performed. The source adds the proactive-message policy
  changes, lifecycle reconciliation and manual intent check, plus scheduled
  promise deduplication and a read-only legacy duplicate report.
- Verification: Alembic reports one head (`m5d2r8q10041`); 191 focused backend
  tests passed for the new behavior; 1,148 frontend tests, i18n checks, and a
  production build passed. The full backend run completed with 8,729 passes;
  its unrelated failures were caused by missing monorepo manifest files,
  inherited storage/deployment test settings, and one existing time-sensitive
  dispatcher case.
- Follow-up: after approval, create and verify a database backup, build the
  local `app` image, run migrations through the existing Compose stack, then
  check health and observe proactive-attempt reasons and latency for one day.

### 2026-08-16 - Native ElevenLabs Video provider

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: committed `ba402e4` on `local/customizations`; GitHub push is
  pending explicit confirmation for this repository egress.
- Backup: `not required`; no schema or data migration
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the local
  `app` and `migrate` services. Added the `ElevenLabs Video` provider for
  ElevenLabs-hosted Veo 3.1 models, with asynchronous job polling and signed
  artifact download.
- Verification: 82 focused backend tests passed; Docker build succeeded; all
  Compose services were healthy and `http://127.0.0.1:8012/health` returned
  `status: ok`.
- Follow-up: create an `ElevenLabs Video` connection in Settings, then select
  it as the active video profile before running a real generation.

### 2026-08-16 - Preserve unsent schedule invitations

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: updated `local/customizations` with the planner guard and its
  focused regression coverage.
- Backup: `pre-unsent-invitation-fix-20260816-211659.dump`
- Deployment: rebuilt the local `app` image and restarted the Compose stack.
  The planner now records an unspoken invitation as `operator_wish`; it cannot
  represent a daily-plan draft as an already-sent invitation.
- Verification: 51 focused schedule, aftermath, and memorializer tests passed;
  Docker build succeeded; all services were healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`. Corrected the affected
  existing schedule activity and episodic-memory record in one verified
  transaction.
- Follow-up: `none`

### 2026-08-16 - OpenAI-compatible video protocols

- Status: completed
- Type: local customization and deployment
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: added protocol-based video support on `local/customizations`
  for Custom OpenAI-Compatible.
- Backup: `not required`; no schema migration
- Deployment: rebuilt and force-recreated the local `app` image. Custom
  OpenAI-Compatible now supports `openai_videos` and `generations_polling`
  video protocols.
- Verification: 99 focused backend tests, 51 frontend tests, frontend
  production build, and Docker app build passed. Compose was healthy and
  `http://127.0.0.1:8012/health` returned `status: ok`.
- Follow-up: configure a provider-specific video model and documented
  protocol before running a real video generation.

### 2026-08-16 - Local source customization workflow

- Status: completed
- Type: deployment foundation
- Upstream base: `v0.5.2` (`69f5cf7`)
- Git result: configured `origin` as the personal fork, `upstream` as the
  original repository, created `local/customizations`, and committed the
  maintenance workflow.
- Backup: `yuralume-before-local-source-20260816-1719.dump`
- Deployment: built `yuralume-local/app:custom`; `app` and `migrate` use the
  local source image while PostgreSQL, storage, and the WhatsApp sidecar keep
  their published images.
- Verification: Docker services were healthy and
  `http://127.0.0.1:8012/health` succeeded.
- Follow-up: `none`

### 2026-08-27 - Preserve same-day story-arc scenes

- Status: completed
- Type: local behavior repair and targeted data correction
- Git result: committed `d46c98a` on `local/customizations`.
- Backup: `pre-schedule-date-fix-20260827-021235.dump` (verified with
  `pg_restore`).
- Deployment: rebuilt `yuralume-local/app:custom` and recreated the local
  `app` and `migrate` services.
- Data repair: restored one future player-central beat that had been falsely
  marked realized, then regenerated the two affected daily schedules.
- Verification: 89 focused backend tests passed; Docker build succeeded; all
  Compose services were healthy and `http://127.0.0.1:8012/health` returned
  `status: ok`. The corrected future beat is pending, the preceding day has
  no venue activity, and the event-day schedule contains venue activities.
- Follow-up: `none`

### 2026-08-28 - Reconcile revised commitments across live projections

- Status: source implementation complete; deployment not performed.
- Type: post-turn commitment reconciliation and concurrency safety.
- Git result: checkpoint commits `2e61b45`, `a73584d`, `e73f7dd`, `838cacf`,
  and `a339c4e` on `local/customizations`.
- Scope: exact-key synchronization for schedules, story beats, active goals,
  and queued promises; nullable persistence fields, snapshot/backup round-trip,
  and additive Alembic migration. Historical records stay immutable; the
  30-minute proactive cooldown and distinct 16:30/18:00 activities remain.
- Verification: focused post-turn/schedule/story/promise suite passed 122
  tests; story/service/routes concurrency suite passed 58 tests; compile and
  `git diff --check` passed.
- Deployment: none. Migration: present but not executed.
- Follow-up: separately approve backup, migration rehearsal, and deployment.

### 2026-08-30 - Add admin CRUD for queued scheduled promises

- Status: source implementation committed; deployment not performed.
- Type: local admin queue maintenance and compatibility repair.
- Git result: local source commit adds admin-only list/create/edit/delete for queued
  `scheduled_promise` rows, with delivery-slot validation, conditional SQL
  writes, and optional distributed release-job withdrawal/re-enqueue. Player
  follow-up responses remain read-only and backward-compatible.
- Data safety: no migration, live-row edit, schedule/story/goal/memory change,
  or proactive cooldown change. Manual rows require an existing conversation
  and carry no commitment key by default.
- Verification: 11 focused admin/service/route/SQL tests, 17 admin-auth
  integration tests, 179 pending/release/dispatcher/post-turn/snapshot tests,
  and 31 ChatService tests passed. One known separate out-of-order audit/undo
  test still fails: undoing turn N+1 also removes turn N's distinct repair
  row. Frontend typecheck, API tests, and i18n checks passed; a prior
  production-assets build completed, but PWA build completion remains blocked
  by the host's Windows temp-directory `EPERM`.
- Follow-up: review the source commit, then separately approve deployment if
  the new admin controls should be exposed in the running app.

### 2026-08-30 - First-meeting reassessment controls

- Status: completed and deployed.
- Type: local story-arc safety repair and admin workflow.
- Git result: committed `ae7259e` on `local/customizations`.
- Scope: a latch-only first-meeting activity (`memorialized=true`,
  `has_memory=false`) remains a valid exact schedule anchor; manual
  reassessment reads a bounded cross-channel dialogue window and remains
  read-only until explicit confirmation writes through the existing
  StoryEvent path. Empty or unavailable evidence fails closed.
- Data safety: no schema migration, live row edit, schedule/memory/history
  rewrite, or proactive cooldown change. The real-message 30-minute cooldown
  is unchanged.
- Backup: `pre-story-beat-reassessment-20260830-233223.dump`, verified as a
  PostgreSQL custom-format archive with `pg_restore --list`; SHA-256
  `277BC513ED1CE12529BB34D8055E3B49DBD995C68CFE713B91BFF346C03FCCE8`.
- Verification: 75 focused story-event/recheck/service/route tests and 6
  commitment reconciliation tests passed; frontend reassessment API test,
  `vue-tsc -b`, i18n checks, and the local-permission Vite/PWA production
  build passed; Python compilation and `git diff --check` passed.
- Deployment: built only `yuralume-local/app:custom`, ran the existing
  `migrate` service successfully, and recreated only `app`. PostgreSQL,
  storage, WhatsApp sidecar, and volumes were retained. Runtime image is
  `sha256:79149119d8a04bf0d923e39ea31a2ec2fda7de5800fad3864f0ecd7870ba8187`.
- Runtime verification: all Compose services are healthy; `/health` returned
  `status=ok`; Alembic is `u2c6m8p10046`; build SHA is `ae7259e`; both new
  routes are registered in OpenAPI; no traceback or error-level startup log
  appeared.
- Follow-up: normal use and monitor manual reassessment results.

### 2026-08-31 - Preserve schedule commitment identity in reassessment

- Status: completed and deployed.
- Type: local persistence mapping hotfix.
- Git result: committed `76a64cd` on `local/customizations`.
- Discovery: the first live reassessment found `matches=0` because the
  schedule ORM mapper dropped `commitment_key` and `is_first_meeting` while
  reading and writing activities. The database row itself was valid.
- Data safety: no migration, live-row edit, schedule/story/memory rewrite,
  promise/goal change, or proactive cooldown change.
- Backup: `pre-schedule-identity-hotfix-20260830-235206.dump`, verified as a
  PostgreSQL custom-format archive with `pg_restore --list`; SHA-256
  `56243118F06702584D434FDD8E08D7A6586B882A74AA88859C6B9A82FB6497BC`.
- Verification: 87 focused mapping/commitment/first-meeting/recheck/service/
  route tests passed; source compilation and `git diff --check` passed.
- Deployment: built only `yuralume-local/app:custom`, ran the existing
  `migrate` gate, and recreated only `app`. Runtime image is
  `sha256:1a8bacde128cccd95e6846e4a3211a442d2bdb3ca14ad28d35b087e71933f934`;
  PostgreSQL, storage, WhatsApp sidecar, and volumes were retained.
- Runtime verification: all Compose services are healthy; `/health` returned
  `status=ok`; Alembic is `u2c6m8p10046`; build SHA is `76a64cd`; the live
  SQLAlchemy mapping reconstructs the 17:30 activity with the expected key,
  first-meeting flag, and memory flags; no traceback or error-level startup
  log appeared.
- Follow-up: retry 「重新判定」 in the Story Arc panel; it should now proceed
  to the evidence review result.

### 2026-08-31 - Use cross-channel dialogue context for normal story arcs

- Status: completed and deployed.
- Type: local story-arc planning context repair.
- Git result: committed `300218c` on `local/customizations`.
- Scope: ordinary LLM-planned story-arc summaries now read the existing
  merged web, Telegram, LINE, and other channel timeline, ordered by message
  timestamp and excluding tool-only artifacts. New arcs, regeneration, season
  context, and normal beat recheck share this helper.
- Explicit non-goal: abandoned/completed arc history handling is unchanged.
- Data safety: no migration, live-row edit, conversation/schedule/story/goal/
  promise/memory change, or proactive cooldown change.
- Verification: focused StoryArcService/planner/context tests passed 63;
  cross-source conversation repository tests passed 26; broader story-arc /
  event / planner tests passed 276; final dialogue-summary/service tests
  passed 31. Source compilation and diff checks passed.
- Deployment: none.
- Follow-up: separately approve a local-source deployment when this behavior
  should be enabled in the running app.

### 2026-08-31 - Deploy cross-channel story-arc context repair

- Status: completed and deployed.
- Type: local story-arc planning context repair deployment.
- Git/build result: behavior commit `300218c` deployed from verified local
  build `4b78590` on `local/customizations`.
- Data safety: this is a read-path-only change. No conversation, arc, beat,
  schedule, memory, goal, promise, cooldown, or schema data was rewritten.
- Backup: `pre-cross-channel-arc-planner-20260831-114811.dump`, verified as a
  PostgreSQL custom-format archive with `pg_restore --list`; SHA-256
  `1575101598705076DD27FC7C8ABE720A930A8EB9A0B2CA0F26FA01272A479FEE`.
- Deployment: built only `yuralume-local/app:custom`, ran the existing migrate
  service successfully, and recreated only `app`. PostgreSQL, storage,
  WhatsApp sidecar, and volumes were retained.
- Runtime verification: all Compose services are healthy; `/health` returned
  `status=ok`; migration exited 0; Alembic is `u2c6m8p10046 (head)`; build SHA
  is `4b78590`; the app container includes the merged cross-channel planner
  call; and no startup error or traceback lines were found.
- Follow-up: create or regenerate a normal story arc when appropriate; its
  summary will then include the recent web, Telegram, and LINE timeline.

### 2026-08-31 - Enrich same-space reply guidance

- Status: source implementation committed and verified; deployment not
  performed.
- Type: local prompt-quality adjustment.
- Git result: committed `1386a00 local: enrich same-space reply guidance` on
  `local/customizations`.
- Scope: the normal web same-space response format now permits grounded,
  scene-dependent environment, sensory, spatial, pause, and continuous-action
  detail in the existing `*...*` action spans. It does not impose a fixed
  length, add a UI mode, change persistence, or alter phone, Telegram, or LINE
  text-message guidance.
- Safety: asterisk spans must remain single-line and moderate in size; the
  prompt explicitly retains the existing no-invented-player rule and prohibits
  creating durable facts, people, places, or commitments merely to add prose.
- Verification: stage/presence regression tests passed 19; prompt golden tests
  passed 85 after intentional snapshot refresh; prompt compilation and
  `git diff --check` passed. The `tools_and_outcomes` golden also caught up
  with a pre-existing explicit-image-trigger source wording without a source
  behavior change in that area.
- Backup: `pre-same-space-detail-guidance-20260831-231054.dump`, verified as a
  PostgreSQL custom-format archive with `pg_restore --list`; SHA-256
  `86DFF9650FB0CD089208FCB88AA231E72F8C4302AFCDB6C8F1CA839669D4D167`.
- Deployment: built only `yuralume-local/app:custom`
  (`sha256:cda6321024f9eb3927bc6ed38201f1488fba72d13f237b8acdca33234bcc7e3d`),
  ran the existing migration gate successfully, and recreated only `app`.
  PostgreSQL, storage, WhatsApp sidecar, and volumes were retained. No schema
  or live-data change was applied.
- Runtime verification: all Compose services are healthy; `/health` returned
  `status=ok`; Alembic is `u2c6m8p10046 (head)`; runtime build SHA is
  `caa41a8`; and the container contains the new same-space detail guidance.
- Follow-up: normal use; no further deployment action is pending.

### 2026-09-04 - Expose pending-follow-ups admin tool

- Status: source implementation committed and verified; Zeabur deployment not
  performed.
- Type: narrow frontend admin-navigation visibility fix.
- Scope: pending follow-ups remains protected by the existing admin routes and
  is now visible in the admin sidebar, admin home, and direct route even when
  `KOKORO_DEBUG_UI_ENABLED` is false. Other developer-only panels remain behind
  the debug flag.
- Data safety: no database, storage, Telegram, scheduler, or live user data
  was changed. No migration is needed.
- Verification: focused frontend navigation tests passed 14; `vue-tsc -b`
  passed; Vite production build passed; `git diff --check` passed.
- Follow-up: the Zeabur memory request/limit and end-to-end backup streaming
  work are recorded in `PENDING_ZEABUR_STABILITY_AND_ADMIN_MENU.md` and remain
  deferred to a separately approved implementation/deployment pass.
