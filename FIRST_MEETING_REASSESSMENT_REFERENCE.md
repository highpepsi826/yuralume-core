# First-Meeting Reassessment Reference

## Status

Approved for implementation on `local/customizations`; source and runtime data
are unchanged at the start of this work.

This document is the durable implementation reference for the first-meeting
reassessment control and the associated exact-schedule-anchor repair. Read it
before changing this behaviour. It supplements, and does not replace,
`FIRST_MEETING_PREMATURE_COMPLETION_FIX_REFERENCE.md`.

## Problem

The active first-meeting beat for the local character remains `pending` after
the scheduled meeting window and attended chat turns. The linked activity has
the expected commitment key and first-meeting flag, but it is already
`memorialized=true` while `has_memory=false`. The existing realization guard
only accepts an unmemorialized activity, so it finds zero valid anchors and
rejects any later first-meeting realization.

The schedule flags have distinct meanings:

- `memorialized` is an idempotency/processing latch, not evidence that a
  memory was written or that a shared meeting happened.
- `has_memory` means the schedule memorializer actually wrote or matched a
  schedule memory.

No existing StoryEvent is linked to the pending beat. A normal chat
post-turn may also miss the `mark_realized` signal for an otherwise completed
event. The operator needs a controlled way to request a fresh evidence-based
decision without turning calendar time alone into fictional history.

## Agreed Scope

1. Preserve the first-meeting safety rules: a calendar slot alone never
   completes the beat; the schedule start must have passed; a player-present
   event is required; and completion must use the normal StoryEvent path.
2. Repair the exact-anchor check so a unique linked activity with
   `has_memory=false` remains a usable first-meeting anchor even when its
   `memorialized` latch is set. An activity that has an actual schedule memory
   remains ineligible for this fallback.
3. Add a per-pending-beat admin control labelled "重新判定" in the existing
   Story Arc panel.
4. The control first runs a read-only, focused reassessment over the beat,
   linked activity, and bounded relevant interaction evidence. It returns
   `completed`, `pending`, or `anchor_error`, with a short reason and, for a
   completion proposal, a factual event summary.
5. A proposed completion requires explicit operator confirmation before any
   write. Confirmation persists a StoryEvent through
   `StoryEventService.record_arc_beat_realization`, then lets the normal arc
   lifecycle mark the beat/arc terminal. It never directly flips a beat row.
6. A non-completion result changes no data. A failed model call or malformed
   response also changes no data and surfaces an actionable error.

## Non-Goals

- Do not auto-complete a first meeting at the scheduled end time.
- Do not write a schedule memory merely to unblock a story beat.
- Do not alter conversation history, existing memories, schedules, goals,
  promises, or proactive cooldown data as part of source implementation.
- Do not use the existing autonomous `simulate` route: it intentionally
  rejects first meetings because it has no player-present evidence.
- Do not fuzzy-match other beats or legacy schedules by prose/date/title.

## Data and Safety Rules

- Existing historical StoryEvents and memories are immutable.
- The manually invoked reassessment may inspect the bounded relevant dialogue
  server-side, but must not expose raw message content through the admin API.
- If the cross-channel evidence window cannot be built, or it yields no
  usable interaction summary, reassessment must fail closed: it may report
  unavailable or keep the beat pending, but it must not ask the LLM to infer
  completion from schedule time or beat prose alone.
- Confirmation must be idempotent: if another writer realized the beat after
  the preview, the confirmation returns the already-linked event rather than
  creating a duplicate.
- The 30-minute cooldown after a genuinely delivered proactive message is
  outside this change and must remain unchanged.

## Affected Components

- `StoryEventService`: exact first-meeting schedule anchor and confirmed
  realization path.
- `StoryArcService`'s existing `StoryBeatRecheckerPort`: reuse its restricted
  JSON parser and `FEATURE_ARC_BEAT_RECHECK` routing for a manual review mode,
  rather than adding a second LLM protocol.
- A small reassessment orchestration service that turns the rechecker result
  into a preview and delegates confirmed writes to `StoryEventService`.
- Story-arc API routes and DTOs for preview and confirm actions.
- `frontend/src/components/StoryArcPanel.vue`, the story-arc API client,
  types, and localized labels.
- Focused backend route/service tests and frontend API/component tests.

## Compatibility and Migration

No database migration is planned. The preview is ephemeral. Confirmed
completion writes the existing StoryEvent and beat fields through established
services. Existing `memorialized=true, has_memory=false` rows remain readable
and become eligible only when they are the unique linked first-meeting anchor.

## Post-Deployment Mapping Repair

The first live reassessment returned `anchor_error` with `matches=0`.
Read-only database inspection confirmed that the pending beat and its
2026-08-30 17:30 Hong Kong activity share `REVIEW-MEET-20260830`, that the
activity is `is_first_meeting=true`, `memorialized=true`, and
`has_memory=false`, and that its exact start time has passed. The data is
valid.

The defect is in `sa_schedule_mapping.py`: `_row_to_activity()` omits both
`commitment_key` and `is_first_meeting` when it reconstructs a domain activity,
so the exact-anchor filter receives `None` / `False`. The symmetric writer
`_activity_to_row()` also omits these values, so later schedule saves could
erase them from otherwise valid rows.

The repair must restore both fields in both directions, use tolerant reads for
legacy rows, and add a persistence round-trip regression test. It must not
change any live schedule row, beat, memory, promise, goal, or cooldown. No
migration is required. After verification, rebuild only `app`, run the normal
`migrate` gate, recreate only `app`, and repeat the read-only anchor inspection
plus health checks.

## Implementation Decision

The manual path must use a cross-channel recent-message window. The existing
arc-planning summary intentionally reads the latest web conversation only;
that is unsuitable for this operator's Telegram-first workflow. Add a
reassessment-only summary helper that calls
`ConversationRepositoryPort.recent_messages_for_character(...)`, sanitizes
the bounded message list with the existing tolerance helper, then calls the
existing dialogue summarizer. It must not change the legacy web-only planner
summary behaviour.

`StoryBeatRecheckContext` gains a `manual_reassessment` flag so its prompt
can distinguish an operator-requested evidence review from retry exhaustion.
In this mode, `mark_realized` becomes a preview proposal only; `delay_beat`
and `skip_beat` are reported as pending and never mutate the arc.

## Verification Plan

1. Unit test first-meeting realization before the exact start, with no player
   presence, with no matching activity, with an actual-memory activity, and
   with a latch-only (`memorialized=true, has_memory=false`) activity.
2. Unit test reassessment outcomes, malformed/provider failures, and confirm
   idempotency.
3. Route tests for ownership, preview, confirmation, and stale/terminal beat
   behaviour.
4. Frontend type check and focused tests for the API client/control states.
5. Run focused story/chat/schedule suites, `git diff --check`, and source
   compilation before committing.
6. Before deployment, create and verify a fresh PostgreSQL custom-format
   backup; build only `app`; run `migrate`; verify Compose health and
   `http://127.0.0.1:8012/health`.

## Ordered Checklist

1. [x] Record observed state and approved design in this reference.
2. [x] Map existing post-turn/StoryEvent contracts and choose the smallest
       reassessment service boundary.
3. [x] Implement the anchor repair with regression coverage.
4. [x] Implement preview/confirm API and focused reassessment logic.
5. [x] Add the Story Arc panel control and localized states.
6. [x] Run focused backend/frontend tests and record results.
7. [x] Commit the verified source change with a narrow `local:` commit.
8. [x] Create a backup, deploy, verify runtime health, and record deployment.
9. [x] Diagnose the post-deployment anchor error with read-only source, log,
       and database inspection.
10. [x] Restore schedule commitment identity in ORM mapping and add regression
        coverage.
11. [ ] Verify, commit, back up, deploy app-only, and retry the read-only
        anchor inspection.

## Current Facts

- The canonical beat remains pending and has no linked StoryEvent.
- Its commitment key is `REVIEW-MEET-20260830`; the linked schedule start is
  17:30 Hong Kong time.
- The activity is `memorialized=true`, `has_memory=false`; app logs report
  zero valid first-meeting anchors during reassessment because the deployed
  schedule ORM mapper drops its commitment identity on read.
- The source worktree was clean immediately before this reference was added.

## Checkpoint

- Current implementation step: deployed reassessment control is under a
  narrow schedule-ORM mapping repair; source fix and focused verification are
  complete, with no live-data correction required.
- Last verified source commit: `ae7259e local: add story beat reassessment controls`.
- Deployment backup: `pre-story-beat-reassessment-20260830-233223.dump`,
  PostgreSQL custom format verified by `pg_restore --list`, SHA-256
  `277BC513ED1CE12529BB34D8055E3B49DBD995C68CFE713B91BFF346C03FCCE8`.
- Last backend test: `.venv\\Scripts\\python.exe -m pytest -q
  tests\\unit\\test_story_event_arc_integration.py
  tests\\unit\\test_llm_beat_rechecker.py
  tests\\unit\\test_story_beat_reassessment_service.py
  tests\\unit\\test_story_arc_service.py
  tests\\unit\\test_story_arc_routes.py` — 75 passed.
- Last frontend verification: reassessment API Vitest test passed; `vue-tsc -b`,
  i18n checks, and the Vite/PWA production build passed. The sandbox build
  cannot inspect the Windows temp directory, so the PWA phase was verified
  successfully through the equivalent local-permission build command.
- Test stability note: the unrelated commitment reconciliation fixture now
  injects its declared 2026-08-28 clock instead of consulting the wall clock;
  its six focused tests pass and no product behavior changed.
- Mapping repair verification: 87 focused schedule-mapping, commitment,
  first-meeting, recheck, reassessment, service, and route tests passed;
  source compilation and `git diff --check` passed.
- Deployment: built only `yuralume-local/app:custom` from source commit
  `ae7259e`, ran the existing `migrate` service successfully, and recreated
  only `app`. Image ID is
  `sha256:79149119d8a04bf0d923e39ea31a2ec2fda7de5800fad3864f0ecd7870ba8187`.
  PostgreSQL, storage, WhatsApp sidecar, and all volumes were retained.
- Runtime verification: all four Compose services are healthy;
  `http://127.0.0.1:8012/health` returned `status=ok`; Alembic is
  `u2c6m8p10046`; runtime build SHA is `ae7259e`; both reassessment routes are
  registered in OpenAPI; and the post-start log contains no traceback,
  `ERROR`, or `CRITICAL` entry. Existing external RSS fetch warnings are
  unrelated and fail soft.
- Next action: use the deployed Story Arc panel's reassessment control when an
  eligible pending beat needs an operator-reviewed decision, after the mapping
  repair is committed and deployed through a fresh backup and app-only restart.
- Blocked reason: none.
