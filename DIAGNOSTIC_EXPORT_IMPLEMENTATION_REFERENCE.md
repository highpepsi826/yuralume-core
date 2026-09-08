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

## Web chat no-response diagnosis (2026-09-06)

The latest diagnostic export shows the final web ``chat`` turn at
``2026-09-06T07:23:19Z`` completed with no error, while no subsequent ``chat``
Turn record exists in the export window. This rules out a global LLM failure
for the reported follow-up and points to the browser send path being blocked
before a request was created. ``ChatPanel.runChatTurn`` rendered the assistant
reply and, for multi-paragraph DM replies, awaited a ``reveal-complete`` event
before its ``finally`` released ``sending``. If the bubble missed that event,
the composer could silently reject later sends forever. The reveal wait now
has a bounded 10-second fallback; activity, credits, and preference refreshes
remain best-effort and never gate chat-turn settlement.

The follow-up export contains a successful ``chat`` Turn at
``2026-09-06T07:50:16Z`` with 67.9s latency. A send attempted while that turn
held the conversation lease correctly received ``conversation_busy``. The
frontend had already rendered its optimistic user bubble before the 409, so a
rejected retry appeared as a duplicate user message. Busy, price, credit, and
session-cap refusals now remove only that unaccepted optimistic bubble while
preserving messages that were persisted before a later stream failure.

## Same-space pacing and message timestamps (2026-09-06)

Same-space replies previously kept action narration in one rendered bubble and
did not use the DM reveal cadence, so multi-paragraph roleplay appeared all at
once. The stage surface now reveals paragraph boundaries sequentially with a
longer bounded pause while preserving ``*action*`` text. ``created_at`` is
returned on chat message responses and rendered above each bubble in the
operator's configured timezone; optimistic user bubbles stamp the send time
until the persisted response is available.

## Upstream slow-stream resilience (2026-09-06)

The upstream usage export confirms that some ``gpt-6-astra`` requests receive
their first token quickly but keep the SSE stream open for tens or hundreds of
seconds. Add a periodic SSE comment heartbeat so Zeabur / browser intermediates
do not close an otherwise live response during token silence. Capture stream
timing and transport outcome on the existing chat Turn record metadata
(``first_token_at``, ``stream_completed_at``, ``transport_detached`` and
``client_cancelled``) so the diagnostic ZIP can explain slow or disconnected
turns without requiring Zeabur's paid log search. Do not add a new log table.

The diagnostic payload also carries a non-sensitive ``deployment`` block with
the process/pod label, process start time, and build image/commit metadata.
This identifies restarts and confirms which image produced a bundle without
pretending to reconstruct Zeabur lifecycle events.

## Interrupted web-stream recovery (2026-09-06)

The 20:36 same-space turn completed server-side after a 182-second wait for
the first token, but the browser reported that the SSE stream ended without
the final ``done`` event. Keep SSE as the low-latency display path while making
the persisted conversation authoritative when the transport disappears:

- On the client, poll the latest conversation briefly after a missing ``done``
  event or a transport/network failure after the conversation id is known, and
  silently reconcile the saved assistant message when it appears.
- If the bounded recovery window expires, request the ordinary conversation
  reload before showing the existing saved-message notice.
- On the server, encode non-credit stream failures as a terminal structured
  ``stream_failed`` frame. Do not expose provider exception text to the client.

The recovery is additive and does not change billing, conversation ownership,
same-space semantics, or the durable turn record contract. A future async-turn
API remains the long-term option if the hosting edge enforces a hard request
duration regardless of heartbeats.

## Planned: tiered diagnostic download UI (2026-09-08)

- Offer time ranges: recent 1 hour by default, recent 2 hours, and custom;
  deployment/migration incidents may use 30 minutes before deployment through
  2 hours after it.
- Provide incident-type presets for Telegram delivery, Web Chat/SSE,
  proactive scheduler, deployment/migration, and storage/images.
- Presets only select fields; advanced checkboxes control detailed exports such
  as full messages, prompts, application logs, storage object metadata, and
  provider raw errors. Full prompts, chat bodies, and credentials remain
  opt-in. Show estimated size and sensitivity before download.
- Provide quick, standard, and full-diagnostic shortcuts. If the first bundle
  is insufficient, use ``incident_summary.json`` to request only the missing
  detail at the same time range.
- Debug integration may allow Codex to sign in to and authorize the Yuralume
  diagnostic page, then fetch a bounded bundle through a protected,
  read-only API. Restrict authorization to admin, short-lived tokens, and
  explicit export scopes; fall back to manual download or shared workspace
  when the connector/session is unavailable.

## Planned: storage and application diagnostics (2026-09-08)

### Completion design and acceptance

- Use the existing storage `stat` port against character portraits plus message
  attachments and album references in the incident window. Do not assume an
  invented `characters/{id}/` key prefix or scan every tenant's objects. Report
  this as current metadata for referenced objects, not historical storage state.
  Cap 100 objects, use bounded concurrency/timeouts; missing objects and source
  failures remain visible. No storage service rollout or database migration.
- Install the bounded WARN/ERROR application buffer during app creation. Export
  redacted JSONL with process-local coverage and eviction metadata. This source
  is application-wide (admin-only), not character-specific; it cannot recover
  logs before restart. No changes to data, polling, schedulers or credentials.
- Keep credentials always redacted, even for full exports. Retain bounded text
  with explicit truncation flags and byte budgets; full messages are opt-in.
- Separate `diagnostic_completeness` from `inferred_health`; remove automatic
  migration advice for missing sources. Add a small `incident_summary.json`.
- Tests must download and parse real ZIPs: messages with bodies, storage stat
  success/missing/timeout, captured warning, opt-out, date and character scope,
  authentication, row truncation, and the previous full-export 500 regression.
- UI must describe real coverage and show post-download completeness. Run actual
  frontend build (there is no `typecheck` npm script), backend tests, and i18n.
- Deployment: app-only source push after verification. Live operator acceptance
  follows only after the new static assets are verified; no migration commands.

- Extend the storage diagnostic surface with a bounded metadata listing scoped
  to a character's referenced objects where possible; export key, content type,
  size, SHA-256, and metadata only, never object bytes. If the adapter cannot
  list objects, record an explicit source error.
- Export application diagnostics from an in-process bounded ring buffer when
  available, filtered to the requested time window and redacted before ZIP
  creation. Do not persist arbitrary third-party or access logs, and keep
  Zeabur Pod lifecycle events as external input.
- Preserve hard caps on rows, bytes, and time window; expose truncation and
  unavailable-source reasons in ``summary.json``.

Implementation status: bounded in-process application diagnostics and
reference-based storage metadata are now wired into the export. The storage
scope is intentionally not a full historical inventory, and Zeabur Pod events
remain external platform input.
