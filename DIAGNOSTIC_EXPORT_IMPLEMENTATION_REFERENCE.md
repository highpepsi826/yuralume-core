# Diagnostic Export Implementation Reference

## Problem

The hosted application writes useful runtime and database diagnostics, but the
current deployed UI does not provide a Turn-record JSON export or a bundled
incident export. Operators need a local artifact for investigating a Telegram
delivery failure by time window.

## Scope

- Add an admin-only diagnostic export API and UI entry point.
- Export a ZIP for a selected character and time window, using Hong Kong time
  in the UI and explicit timezone metadata in the artifact.
- Include available turn records, conversation messages, inbound receipts,
  outbound delivery rows, messaging account polling status, and a summary
  timeline. Include application log text only when an archived/imported log
  source is available; platform-level Zeabur events remain external input.
- Redact credentials, authorization values, and other secret-shaped fields.
- Keep raw chat text and full prompts opt-in.

## Non-goals

- No production database edits, message repair, replay, resend, or deletion.
- No automatic Zeabur API access or direct Pod mutation.
- No change to Telegram polling or delivery semantics.
- No promise that Zeabur platform events can be reconstructed by the app.

## Data safety and compatibility

The endpoint is admin-only, read-only, bounded by a maximum time window and
row count, and returns a downloaded ZIP. Existing tables and APIs remain
compatible; no migration is expected unless implementation discovers a missing
query surface. Secrets are never included in the export.

## Implementation checklist

1. Add backend export DTO/query helpers and ZIP generation with redaction. **Done**
2. Add the admin route with character/time-window validation and download
   headers.
   **Done**
3. Add the admin UI controls, progress/error state, and browser download.
   **Done**
4. Add focused tests for authorization, bounds, timezone conversion,
   redaction, and ZIP contents.
5. Run focused tests, compile/type checks, and diff checks.
6. Record the verified source result; deployment requires a separate review.

## Current status

Backend export endpoint and frontend download control are implemented in the
working tree. The bundle contains Turn-record summaries, selected-character
messaging account status, inbound receipts, and outbound delivery/retry rows.
Full prompts remain opt-in; Zeabur platform logs are still supplied separately.
Production deployment remains pending verification.
