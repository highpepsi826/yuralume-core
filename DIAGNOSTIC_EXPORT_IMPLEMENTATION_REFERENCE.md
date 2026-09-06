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
- Extend the existing inbound receipt retention to 14 days and use the
  existing Turn, receipt, delivery, and account records for incident diagnosis
  across app image replacement and Zeabur Pod recreation. Do not add a new
  application_logs table in this phase.
- Cover Telegram receive/dispatch/delivery, image sends, chat generation,
  schedule CRUD, and startup/runtime failures with correlation identifiers.

## Non-goals

- No production database edits, message repair, replay, resend, or deletion.
- No automatic Zeabur API access or direct Pod mutation.
- No change to Telegram polling or delivery semantics.
- Pod restart, OOM, startup probe, and other Zeabur platform events remain
  external platform input and are intentionally read from the Zeabur console.
- Do not persist every third-party or access log line, full prompts, or chat
  bodies as application logs.

## Data safety and compatibility

The endpoint is admin-only, read-only, bounded by a maximum time window and
row count, and returns a downloaded ZIP. Inbound receipt retention is extended
from 7 to 14 days; no new log table is added. Existing tables and APIs remain
compatible apart from the retention configuration. Secrets are never included
in the export.

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

## Approved execution changes

- Change ``DEFAULT_RECEIPT_RETENTION_DAYS`` from 7 to 14.
- Add bounded processing outcome fields to the existing inbound receipt row:
  state, failure code/message, and completion timestamp. These fields remain
  metadata only and never store message text or credentials.
- Mark accepted, rejected, generation-failed, queued, and delivered outcomes
  from the dispatcher so a Telegram delivery can be followed after restart.
- Preserve the existing generation-failure fallback, and add deterministic
  notices only to terminal pre-dispatch failures where retrying would otherwise
  silently lose the update. Busy/draining paths continue to hand the update
  back to Telegram.
- Keep Zeabur platform events outside the application database.

The diagnostic bundle also reports an inferred application health summary from
the export request itself and the selected character's durable records. It
must distinguish functional health from unknown platform lifecycle state:
``healthy`` means recent polling and no pending/failed evidence in the window,
``degraded`` means a stale polling account or failed/unresolved delivery, and
``unknown`` means there is not enough durable activity to infer a state.

The receipt outcome fields and 14-day default are now implemented in the
working tree, with migration ``v6r4t2y10055``. Telegram fallback behavior is
unchanged pending a production log sample that identifies a terminal path.

## Diagnostic event contract

The implementation relies on existing durable rows and focused structured
fields. It must not persist Zeabur platform events or credentials. Error and
delivery metadata remain bounded and exclude authorization headers, bot tokens,
full prompts, and chat text unless an existing record explicitly requires it.

## Retention and Telegram fallback decision

Inbound receipt retention is planned to change from 7 to 14 days; no separate
application log table is planned. Zeabur Pod lifecycle events remain in the
Zeabur console.

The existing localized generation-failure notice is only sent when
``MessagingDispatcher.handle_inbound`` reaches its generic chat-service error
branch. Busy conversation hand-back, polling/API failures before dispatch,
sender or binding rejection, and outbound transport failures follow different
paths. Investigate these paths before changing the fallback behavior so a
retryable Telegram update is not acknowledged or duplicated incorrectly.

## Current status

Backend export endpoint and frontend download control are implemented in the
working tree. The bundle contains Turn-record summaries, selected-character
messaging account status, inbound receipts, and outbound delivery/retry rows.
Full prompts remain opt-in; Zeabur platform logs are still supplied separately.
The export also includes an ``inferred_health`` summary with current endpoint
availability, stale Telegram polling accounts, unresolved receipts, failed or
pending deliveries, and Turn errors. It is functional evidence, not a
reconstruction of Zeabur Pod lifecycle history.

Receipts created before outcome tracking was deployed are classified as
``legacy`` during migration and are reported as historical/unknown rather than
as currently unresolved work. Only new ``claimed`` or ``queued`` rows affect
the degraded health verdict.

If an optional durable source cannot be queried during a rolling deployment,
the endpoint returns a partial ZIP with ``source_errors`` and a migration hint
instead of a generic HTTP 500. The Zeabur app service still needs
``alembic upgrade head`` before the receipt outcome columns are available.
Receipt outcome migration and dispatcher outcome marks are implemented in
commit ``e90f15c``. Production deployment remains pending a PostgreSQL backup
and migration verification. No fallback text behavior was changed yet; the
current evidence shows that only the generic ChatService failure branch sends
the existing notice, so polling/pre-dispatch and delivery failures still need
an observed failure sample before changing retry semantics.
