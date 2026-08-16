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
