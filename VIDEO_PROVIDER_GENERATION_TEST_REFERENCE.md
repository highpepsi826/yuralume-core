# Video provider generation test

## Problem and scope
The provider connection test only checks reachability. Add an explicit admin
action on the video capability card that generates one short clip using the
current draft and, when editing, the stored secret. Show a cost confirmation,
editable prompt, busy state, playback, download, and a readable error.

## Boundaries
Do not publish feed posts, change characters/history, persist test media, change
provider settings, or call paid APIs during implementation verification. Use a
temporary synthetic character and the same video adapter builder as runtime.
Keep shallow tests unchanged. No schema migration or deployment in this task.

## Components and compatibility
Provider connection service validates draft config and resolves matching stored
credentials; admin-only/cloud-disabled API returns an MP4; frontend uses a blob
URL and revokes it on replacement, draft changes, and unmount. A bounded 30 minute
generation timeout and slightly longer client timeout accommodate slow providers.
Existing providers and saved configuration remain compatible. Reverse-proxy long
request limits are deployment dependent and require live validation.

## Verification
Mock adapters to verify generation arguments, saved-secret reuse, draft override,
provider mismatch, unsupported capability, empty output, redaction, and errors.
Check admin/cloud access and MP4 response. Run focused Python tests, frontend
type/build checks and locale checks. No real generation or production deployment.

## Status and ordered checklist
- [x] Inspect existing provider tests and runtime adapters.
- [x] Implement validated no-write generation service and API.
- [x] Add localized prompt, confirmation, playback and download UI.
- [x] Run focused verification and inspect diff.
- [x] Record outcome; deployment remains pending.

## Verification outcome (2026-10-16)
- 95 Python tests passed across provider settings, native media adapters, and
  the new generation-preview suite (11 new cases).
- 22 frontend API/field tests passed, including blob errors and cancellation.
- Vue TypeScript checks, locale checks, and production/PWA build passed.
  Build used workspace TEMP/TMP to avoid the sandbox's user-profile temp access
  restriction. Existing Node version/chunk-size warnings remain.
- No paid provider request, live browser playback, commit, push, or deployment
  was performed. Hosted proxy timeout behavior remains unverified.
