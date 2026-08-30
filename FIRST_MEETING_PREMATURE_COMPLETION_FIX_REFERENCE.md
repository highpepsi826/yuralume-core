# First-Meeting Premature Completion Fix Reference

## Problem

The canonical first-meeting beat for character
`8b491064-97af-43b1-9124-c89977406120` was scheduled for the 17:30 HK
card handover on 2026-08-30, but an unattended `scene_simulation` realized it
at 00:02. The beat had `is_first_meeting=true` while
`operator_position` was NULL. Autonomous routing only treated
`operator_position=central` as player-required, so it generated a false
meeting event and memory before the player arrived. Later same-day beats became
terminal and the arc was marked `completed`, making the active-story endpoint
empty.

## Approved Scope

- Treat `is_first_meeting=true` as player-required in every unattended story
  path, even when `operator_position` is NULL.
- Keep a first-meeting beat pending until its linked live schedule start (the
  approved 17:30 HK handover) has passed; do not infer a time from prose.
- Apply the same guard to autonomous story-event realization and post-turn
  realization so a same-day pre-event conversation cannot silently canonize the
  meeting.
- Keep low-level arc mutation helpers from marking a first meeting realized
  without a persisted `StoryEvent` link; normal attended realization still
  goes through `StoryEventService`.
- Add focused regression tests for unattended routing, same-day time gating,
  and arc completion protection.
- Repair only the known erroneous live data in one transaction after a fresh,
  verified PostgreSQL backup.
- Redeploy the local app image and verify normal scheduler behaviour.
- Preserve the real-message 30-minute proactive cooldown and all unrelated
  schedules, goals, promises, conversations, and memories.

## Exact Data Repair

Target character: `8b491064-97af-43b1-9124-c89977406120`

Target arc: `6f727ca8102c493faf8af57344b6a7ae`

Canonical first-meeting beat: `3364666069e5424fbf0e5d9a5faffb37`

False story event: `bca2f515-efa8-48ef-928a-8574f26a3fa4`

False beat memory: `8adddf35-75ac-42e6-8ba6-45250eba7099`
False completion milestone memory: `7abf826c-546f-44da-8d55-a34d161db505`

The repair transaction must verify every target's current value before writing:

1. Delete only the two false memory rows above and the false story-event row.
2. Set the canonical beat back to `pending`, clear its
   `realized_event_id`, reset only the false play-attempt bookkeeping, and
   retain its approved date, commitment key, and `is_first_meeting=true`.
3. Set the target arc to `active` without rewriting any beat text or any other
   beat status.
4. Leave the valid 14:13 and 14:21 same-day stage events/beats and all other
   memories untouched.

If any precondition differs, abort the transaction and report the mismatch;
never broaden the target set or fuzzy-match rows.

## Invariants

- A first meeting cannot be autonomously simulated or marked realized before
  the exact linked live schedule start.
- The player-facing chat path may realize it only after that start and only as
  part of an actual player-present interaction.
- The first-meeting schedule remains the separate 17:30-18:00 activity; the
  18:00-21:30 festival activity remains independent.
- Historical records unrelated to the erroneous generated event remain
  immutable.
- Arc completion requires all beats terminal *and* must never be reached by an
  unattended first-meeting simulation.
- No migration is needed; this is source logic plus a one-shot data repair.
- The 30-minute post-send proactive cooldown is unchanged.

## Affected Components

- `StoryArcService.next_beat_due` and its player-required predicate.
- `StoryEventService.ensure_today` and
  `record_arc_beat_realization`.
- `ProactiveDispatcher`'s awaiting-player projection.
- Schedule lookup needed to resolve the exact first-meeting start instant.
- Unit tests for arc routing, story-event integration, and proactive
  scheduling.

## Ordered Checklist

1. Re-read this reference and perform a read-only preflight of the exact rows.
2. Implement a shared player-required predicate and exact schedule-time guard.
3. Add and run focused regression tests; run `git diff --check` and compile.
4. Commit the source/reference changes with a narrow `local:` commit.
5. Create and verify a fresh PostgreSQL custom-format backup.
6. Run the exact repair transaction with preconditions and capture a
   non-sensitive audit result.
7. Build the local app image, run the existing migration service (no schema
   change), and recreate only `app`.
8. Verify Compose health, `/health`, Alembic, active arc/beat state, and the
   next normal scheduler tick.
9. Update `UPDATE_PROGRESS_LOG.md` and this reference with final results, then
   commit the deployment record.

## Status

Source guard and focused regression coverage are complete and verified; source
commit, live backup, exact data repair, and deployment verification remain.

## Verification So Far

- Focused first-meeting/story/proactive suite: 78 passed.
- Background proactive/scheduler/tick/story suite: 148 passed.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Live Preflight (2026-08-30)

- Runtime Compose was read successfully; PostgreSQL and all support services
  are healthy, and the current app health endpoint returns `status: ok`.
- The target arc is currently `completed` with 14/14 beats realized.
- The target first-meeting beat still has the approved date/key/flag but is
  incorrectly `realized`, points at the approved false event ID, and has one
  `scene_simulation` attempt. Its other attempt/failure fields remain at the
  values covered by the repair precondition.
- The false event and both exact false memory IDs are present. The valid
  same-day stage records remain separate and are outside the repair set.
- The live 17:30 HK activity is an unmemorialized first-meeting activity at
  `09:30 UTC`; the separate festival activity starts at `10:00 UTC` and is not
  a first meeting.
- No live row has been changed yet. App stop and backup are the next actions.
