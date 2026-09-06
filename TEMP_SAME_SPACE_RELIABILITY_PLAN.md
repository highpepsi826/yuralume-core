# Same-Space Reliability Improvement Plan

## Purpose

Investigate and repair the hosted same-space chat path when a long-running
turn becomes unclear to the player, the Zeabur readiness probe times out, or a
Pod restarts while chat/background tasks are still running.

This is a temporary implementation reference. It must be replaced or folded
into a permanent scoped reference before the final production rollout.

## Current Evidence

- A same-space turn can wait roughly 2 minutes for its first token while the
  upstream LLM request remains active.
- The browser may lose the SSE transport at a fixed proxy/request boundary,
  even though the server later finishes the turn and persists the reply.
- The player-facing client currently receives `conversation_id`, but not a
  durable foreground `turn_id` or a queryable turn state.
- `GET /health` is synchronous and intentionally cheap, but Zeabur recorded a
  readiness failure while waiting for response headers. This indicates the
  process could not schedule the health handler in time, or the Pod was already
  entering restart/termination.
- The current production app uses one `all` process for API/SSE and background
  ownership. A long or CPU-heavy path can therefore affect probe response time.
- `Task was destroyed but it is pending!` is emitted by asyncio when the event
  loop is closing and a task still has pending work. Candidate tasks include a
  detached chat relay/watchdog, an upstream stream reader, a finalizer, or a
  fire-and-forget post-turn task. It is a shutdown/lifecycle warning, not an
  LLM response payload.
- The app lifespan waits for pending detached turns and other background work,
  but both drains are bounded at 10 seconds. A Pod termination shorter than
  the remaining work, or a task created outside the tracked sets, can still
  produce this warning.

## Problem Statement

The system currently conflates four states at the UI boundary:

1. The browser/SSE transport disconnected.
2. The LLM request is still processing.
3. The Pod was restarted and in-memory work was lost.
4. The turn completed and was persisted after the browser disconnected.

Without a durable turn identity and lifecycle state, the frontend cannot tell
these cases apart. Conversation history is therefore used as an indirect
signal, which is insufficient during a restart or concurrent send.

## Approved Scope

### Phase 1: Durable turn lifecycle

- Create a durable foreground turn row or extend the existing turn record so a
  turn is created before the upstream call.
- Persist a stable `turn_id`, `conversation_id`, character id, lifecycle state,
  timestamps, last heartbeat, and bounded failure/restart reason metadata.
- Expose a player-authorized status endpoint keyed by `turn_id`.
- Return `turn_id` in the first chat response/SSE frame.
- On graceful shutdown, mark owned processing turns as restart-interrupted or
  leave them explicitly recoverable according to the final state contract.

### Phase 1 implementation decisions (2026-09-06)

- Reuse the existing `turn_records` table and add nullable-compatible lifecycle
  columns (`status`, `started_at`, `updated_at`, `last_heartbeat_at`,
  `failure_code`). Existing historical rows are backfilled as `completed`.
- The foreground streaming path allocates the stable record id and inserts a
  `processing` row before the LLM call. The same finalizer updates that row to
  `completed` or `failed`; the existing response/prompt telemetry remains on
  the row.
- The first SSE frame carries both `conversation_id` and `turn_id`. A new
  owner-scoped `GET /api/v1/chat/turns/{turn_id}` endpoint returns lifecycle
  state and the completed assistant message when available.
- The initial implementation keeps non-streaming/proactive recording behavior
  unchanged. Only foreground web chat turns use the lifecycle fields first;
  later phases may extend the same status contract to external channels.
- A migration is required. It is source-only for this step; production backup,
  Alembic execution, and deployment remain gated until local tests and rollback
  review pass.

### Phase 2: Frontend state recovery

- Treat SSE as a live display channel, not the source of truth.
- On transport loss, keep the turn in `processing` and poll its status without a
  short fixed error deadline.
- Automatically load the completed assistant reply when status becomes
  `completed`.
- Show a distinct state for `failed`, `aborted_by_restart`, and unknown status.
- Do not allow a second send for the same conversation while the tracked turn
  is still processing, unless the user explicitly cancels/retries.
- Stop polling when the user changes character or intentionally leaves the
  conversation view.

### Phase 3: Runtime and deployment isolation

- Add event-loop lag, request latency, readiness latency, process start/stop,
  Pod restart, and memory/CPU correlation fields to diagnostics.
- Review every `asyncio.create_task` path and ensure tasks are tracked,
  cancelled, and awaited during shutdown.
- Separate API/SSE from scheduler/Telegram/background ownership using the
  existing process-role boundaries, preserving exactly one polling owner.
- Use a minimal liveness probe and a separate readiness probe with measured
  startup/termination settings.
- Add graceful deploy draining: stop accepting new turns, wait for durable turn
  state transitions, then terminate the process.

## Explicit Non-Goals

- No deletion, repair, replay, or rewriting of existing conversations.
- No change to same-space narrative semantics or billing semantics.
- No increase of a proxy timeout as the only fix.
- No addition of multiple API replicas while the `all` role still owns a unique
  scheduler or Telegram polling loop.
- No production migration or deployment until schema impact, backup needs, and
  rollback are reviewed.

## `Task was destroyed but it is pending!` Handling

The warning should be treated as evidence that process shutdown did not finish
all asynchronous work cleanly. The first implementation step is observability,
not broad cancellation: identify the task name/type and owner, then make that
owner participate in the lifespan drain. Cancelling a database finalizer in the
middle of a SQLAlchemy operation can lose the assistant reply or leave a
charge/lease inconsistent, so finalizers need explicit shielded completion or
durable recovery semantics before their timeout is changed.

The readiness timeout and pending-task warning may share a Pod restart, but
they are not identical errors:

- readiness timeout: the process did not answer `/health` within the probe
  deadline;
- pending-task warning: the event loop closed while work was still pending.

Zeabur platform restart reason, OOM status, and exact probe timeout remain
external evidence and must be captured from the dashboard alongside the
application diagnostic export.

## Test Plan

- Unit-test durable turn creation before the LLM call.
- Unit-test status transitions for completion, provider failure, client
  disconnect, and process restart.
- Exercise SSE disconnect followed by status polling and automatic recovery.
- Verify concurrent sends return a clear processing/busy state tied to the
  tracked turn.
- Test shutdown with detached relay, upstream reader, finalizer, and post-turn
  tasks; assert no pending-task warning and no double release.
- Measure `/health` latency while a long same-space turn is active.
- Run frontend focused tests, Python focused tests, build, and `git diff --check`.
- Before production migration/deployment, create and verify the required
  PostgreSQL backup and perform an app-only rollout where possible.

## Ordered Checklist

1. Record this plan before source edits. **Complete**
2. Inventory current turn persistence, status surfaces, and every relevant
   background task owner. **Complete**
3. Implement durable turn lifecycle and status API. **Complete**
4. Implement frontend status recovery and waiting states. **Complete**
5. Harden task tracking/shutdown and add probe/event-loop diagnostics. **Partial**
   (chat relay drain, stale-turn reconciliation, recorder flush)
6. Run focused tests and local deployment verification. **Complete**
   Focused checks pass; full frontend suite has one unrelated timeout in
   `uiImage.test.ts` under the local Windows sandbox.
7. Review schema/backup requirements and deploy app-only or split roles. **Blocked pending backup and controlled migration**
8. Verify health, restart behavior, turn recovery, and one polling owner.
