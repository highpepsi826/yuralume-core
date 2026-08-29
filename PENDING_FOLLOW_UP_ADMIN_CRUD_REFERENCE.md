# 手動待回覆管理 CRUD Reference

## Status

Approved and deployed from `local/customizations`.
This is a small operational tool, not a replacement for automatic
cross-surface commitment reconciliation. The approved deployment reuses the
existing pending-follow-up schema and does not edit live queue rows.

## Problem

The admin "待回覆訊息" page can currently only reload open rows or invoke one
dispatcher tick.  Reloading is read-only and the tick only releases rows whose
`scheduled_for` is already due; neither operation lets an operator correct a
queued scheduled promise after a meeting or reminder changes in chat.

The operator needs a narrow manual escape hatch for the queue itself:

- delete a queued scheduled promise that should no longer be sent;
- edit its future send time and/or the natural-language promise intent; and
- add a new scheduled promise deliberately when the character should send a
  callback that is not currently queued.

## Approved Scope

### Included

1. Admin-only list details and CRUD for `kind=scheduled_promise` rows.
2. Existing rows are editable only while `status=queued`.  The edit accepts a
   future `scheduled_for` and/or a non-empty `promise_intent`.
3. Existing rows are deletable while they are still `queued`.
4. New rows are created as scheduled promises with a future `scheduled_for` and
   non-empty `promise_intent`.  The service uses an explicitly supplied valid
   conversation when given; otherwise it resolves the character's latest
   existing conversation.  No empty conversation is created implicitly.
5. Existing derived values are maintained:
   `dedupe_key`, `delivery_slot_key`, and the composer-facing
   `obligations` are rebuilt when an edit changes the time or intent.
   Repository writes use conditional admin-only operations so a stale browser
   snapshot cannot overwrite a worker's `resolving` transition or delete an
   in-flight row.
   The UI receives an early delivery-slot conflict where possible, while the
   repository write remains the race-safe authority.
6. When a distributed release queue is wired, edits withdraw release jobs
   derived from the old timestamp and enqueue the new row; deletes withdraw
   the row's queued release jobs.  In embedded self-host mode these hooks are
   no-ops and the normal scheduler reads the saved row.
7. The admin response exposes `kind`, `promise_intent`, and
   `commitment_key` for diagnosis without changing the player-facing response
   contract.  Internal dedupe hashes remain hidden.

### Explicit Non-goals

- No automatic comparison of pending promises with schedules, story beats,
  goals, memories, or Telegram prose.
- No memory schema, memory contents, embedding, or consolidation changes.
- No schedule, beat, goal, character, conversation-history, or cooldown
  mutation as a side effect of queue CRUD.
- No new `manual_override` column or migration in this version.
- No editing of `kind`, row id, `conversation_id`, `turn_record_id`,
  `commitment_key`, status, original queued messages, or resolved output.
- No CRUD controls for `busy_defer`, `resolving`, `resolved`, or `cancelled`
  rows.
- No new "force send now" behavior.  The existing tick still only releases
  rows that are due.

## Behavioral Rules

### Edit

- Resolve the row by exact id and verify `scheduled_promise` + `queued`.
- Reject a new time that is missing, invalid, or not strictly in the future.
- Preserve the original queued message and turn anchor for audit/undo.
- If `promise_intent` changes, replace the composer-facing obligation with one
  obligation carrying the edited intent while retaining the original source
  provenance where possible.  This prevents the composer from silently using
  an old merged obligation.
- Recompute both delivery-derived hashes from the resulting time/intent.
- Preserve an existing `commitment_key` as read-only.  A later chat turn that
  explicitly emits that same key may still reconcile the row; this is a known
  limitation of the no-migration version and must be stated in the UI.

### Delete

- Delete only an open queued scheduled promise.  A row already `resolving` is
  considered in flight and is not editable or deletable through this surface.
- Withdraw queued release jobs after the row is removed.  If a worker already
  claimed a job, the existing handler re-reads the row and safely skips a
  missing row; the UI must not claim cancellation of work already in flight.
- The user-facing action may be labelled "刪除".  This version uses the
  repository's hard delete and therefore removes the queue row's own audit
  record; broader historical records remain untouched.

### Add

- Create only a `scheduled_promise` row with `turn_record_id=None` and no
  commitment key by default.  It is an operator-authored queue item, not a
  claim that a chat turn promised it.
- Require a character and an existing conversation (explicit or latest).
- Reject a past time and reject a delivery slot already occupied by another
  open scheduled promise instead of silently merging two manual intentions.
- Enqueue its release job when the distributed queue is available.

### Delivery and cooldown

The existing scheduled-promise dispatcher remains the delivery authority.  It
will append a successful outbound reply to the normal web/channel history and
write the existing proactive attempt audit.  It chooses the currently eligible
proactive binding (for example the active Telegram binding), not an arbitrary
UI source selector.  Scheduled promises already bypass normal proactive
quiet-hours, daily-limit, and 30-minute cooldown gates; this CRUD feature does
not change that policy or the cooldown implementation.

## Affected Components

- `src/kokoro_link/domain/entities/pending_follow_up.py`: small validated admin
  edit helper for derived fields/obligations.
- `src/kokoro_link/contracts/pending_follow_up.py` and both repository
  adapters: strict manual insert, compare-and-set edit, open-row census, and
  queued scheduled-promise delete operations.
- `src/kokoro_link/application/services/pending_follow_up_admin_service.py`:
  new narrow service for validation, repository writes, conversation resolution,
  and optional release-job housekeeping.
- `src/kokoro_link/api/routes/pending_follow_ups.py`: admin list/create/update/
  delete endpoints and admin response DTOs; existing player endpoints stay
  backward-compatible.
- `src/kokoro_link/bootstrap/container.py`: wire the service while retaining
  the existing embedded/distributed shapes.
- `frontend/src/utils/api/pendingFollowUps.ts` and
  `frontend/src/components/PendingFollowUpsPanel.vue`: admin-only details,
  modal/form actions, optimistic reload, and clear status/error messages.
- Focused backend and frontend tests.

## Compatibility and Data Safety

- Reuse the already-deployed `pending_follow_ups` columns; no Alembic
  migration is expected.
- Player `PlayerFollowUpsCard` remains read-only and continues using its
  existing character-scoped endpoint.
- Historical/resolved rows and all other tables are not written by these
  endpoints.
- A same-key automatic post-turn reconciliation may later change a manually
  edited existing row; this is documented rather than hidden.
- Undo behavior remains unchanged.  A promise tied to a prior turn can still
  be affected by undo according to that turn's existing journal semantics.
- Turn-journal snapshots now round-trip the pending row's delivery identity,
  obligations, and commitment key; snapshots written before those optional
  fields remain readable with empty defaults.

## Regression Coverage

1. Admin list returns detailed scheduled-promise fields but player response
   shape remains compatible.
2. Queued future edit changes time and intent, rebuilds obligations and both
   derived keys, and preserves source message/anchor/key.
3. Edit rejects busy-defer, resolving, terminal, past-time, invalid-time, and
   occupied-slot cases without writing.
4. Delete removes a queued promise and withdraws every queued release-job key;
   resolving/terminal rows are not removed.
5. Add creates an unkeyed future promise against an existing conversation,
   rejects missing conversation/past time/slot conflict, and enqueues when a
   queue is wired.
6. A distributed old release job cannot send an edited future row at its old
   time; the new timestamp gets a new release job.
7. Normal chat, memory, schedule, story, goal, and proactive cooldown tests
   remain unchanged and pass.
8. Every new admin endpoint rejects a non-admin caller; the admin-auth test
   fixture is isolated from host storage configuration.

## Ordered Checklist

1. Add this reference before source edits. **Complete**
2. Add the domain edit helper and admin service with in-memory tests. **Complete**
3. Add admin DTOs/routes and container wiring; run backend route/service tests. **Complete**
4. Add API client and admin panel controls; run frontend tests/typecheck/build. **Complete**
5. Run focused regression suites and `git diff --check`. **Complete**
6. Update `.codex-round.md` and `UPDATE_PROGRESS_LOG.md`, create a narrow
   local commit, and deploy after separate approval. **Complete**

## Current State

- Repository: `C:\Entertainment\yuralume-src`
- Branch: `local/customizations`
- Source implementation, verification, local checkpoint commit, and deployment:
  complete (`6340238`)
- Migration: not needed/planned
- Live data/deployment: local app image built; `migrate` exited 0 and only the
  app container was recreated. No feature-specific data repair was run.
- Next action: monitor the admin queue controls in normal use; do not rerun
  deployment unless source changes.
- Blocked reason: none
