# Update and Progress Log

This is the durable, non-sensitive operating record for this personal
Yuralume self-host. Add new entries at the top after the work is verified.
Do not record API keys, connection strings, chat content, character data, or
database rows.

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
