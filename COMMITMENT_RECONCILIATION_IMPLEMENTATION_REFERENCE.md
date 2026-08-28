# Commitment Reconciliation Implementation Reference

## Status

Source implementation complete and committed on `local/customizations`.
The additive migration is present but has not been executed; runtime,
database, schedule, story, goal, pending-follow-up, and user data remain
untouched.

This document is the durable implementation reference for the post-turn
commitment reconciliation repair. Read and update it before making any code,
migration, data, or deployment change for this behavior.

## Problem

When a player and a character agree to meet, then revise that agreement in a
later chat, Yuralume currently processes each post-turn output independently.
As a result, one surface can update while the others retain the old date or
text:

- daily schedule activity;
- story-arc beat;
- medium-term character goal; and
- queued scheduled-promise follow-up.

The system has no shared, durable identity for one player-facing commitment.
Existing identifiers are local to each surface. In particular,
PendingFollowUp.delivery_slot_key is a delivery-window deduplication key and
must not be repurposed as a commitment identity.

## Agreed Product Rules

1. A revised meeting or promise must reconcile the four surfaces above when
   they refer to the same explicit commitment.
2. Activities at 16:30 and 18:00 may remain separate activities. A date or
   meeting revision must not collapse them merely because they are related.
3. Only one open commitment identity can represent the genuine first meeting.
   Its linked schedule activity and linked story beat may both carry the flag;
   they are two projections of the same commitment, not two first meetings.
4. Completed, skipped, realized, cancelled, resolved, memorialized, lapsed,
   abandoned, or otherwise historical records are immutable. Do not overwrite
   them to make a later chat look consistent.
5. Legacy records without a shared identity must not be fuzzy-matched and
   must not be auto-backfilled from titles, dates, or prose.
6. A failed reconciliation on one surface must be logged and fail soft. It
   must not fail the chat turn or prevent the other independent surfaces from
   reconciling safely.
7. The existing 30-minute cooldown after an actually sent proactive message
   remains unchanged.
8. This task is source-only until explicit deployment approval. Do not alter
   the runtime deployment, Docker volumes, database rows, character records,
   chat history, schedules, or promises as part of implementation.

## Shared Commitment Identity

Add one nullable commitment_key to these domain records:

- ScheduleActivity
- StoryArcBeat
- CharacterGoal
- PendingFollowUp

Add is_first_meeting: bool = False to:

- ScheduleActivity
- StoryArcBeat

Use one shared helper:

    def normalize_commitment_key(value: object) -> str | None:
        ...

Its behavior is deliberately small: accept strings, strip surrounding
whitespace, and turn empty values into None. Non-string values become None.
It must not infer a key from user-visible text.

Every entity constructor, factory, replace/with-fields method, SQLAlchemy row,
mapper, repository, in-memory repository, turn snapshot codec, and character
backup DTO must round-trip these fields. The additive database migration
joins the local outbound-delivery revision `t9q4v7x10045` with the upstream
v0.7.0 revision `e9x5p3m10054` before adding the new columns, preserving both
histories and leaving existing rows nullable. This ordering keeps the merged
deployment on one Alembic head.

### Approved Goal Target-Date Representation

`CharacterGoal.target_date` is a first-class optional `date` domain field.
Persistence stores the matching nullable `character_goals.target_date_iso`
(`YYYY-MM-DD`) column. The post-turn signal's `target_date_iso` is parsed and
validated before it reaches the domain; it must never be appended to
`review_notes`. Snapshots and character backup carry the field. This is an
additive source/migration change only until separately approved deployment.

## Post-turn Contract and Prompt

Extend the post-turn contract, LLM parser, and prompt so one revised
commitment can carry the same non-empty commitment_key through schedule,
story-arc, goal, and scheduled-promise outputs.

- Prefer a supplied local ID (activity_id or beat_id) when the parser has a
  verified ID in its context.
- Add the smallest exact-key goal reconciliation output needed to update an
  active goal; do not introduce broad free-text goal rewriting.
- Capture is_first_meeting only when the model is referring to the genuine
  first in-person meeting.
- Supply enough future schedule context to verify a known activity ID before
  the parser emits a change. Do not limit verification to today's row.
- Reject blank keys and invalid values. No text similarity matching, title
  matching, or date-only matching is permitted as a fallback.

When two candidates share a key, an adjustment without an exact local ID must
be treated as ambiguous and left unchanged. This preserves distinct 16:30 and
18:00 activities.

## Reconciliation Behavior

### Schedule

- Match an activity first by exact activity_id; otherwise only by a unique,
  exact, normalized non-empty commitment_key.
- Allow a matched activity to move from its old date row to a new date row.
  Persist removal from the old row and insertion into the new row safely.
- Do not modify a memorialized or other historical activity.
- Preserve distinct activities even when their surrounding conversation is
  related. Never merge records by title, date, time, or key alone.
- Enforce first-meeting uniqueness among live schedule activities. Clearing a
  replacement flag is allowed only on another live record for the same
  character; historical records remain untouched.

### Story Arc

- Match a beat first by exact beat_id; otherwise only by a unique, exact,
  normalized non-empty commitment_key.
- Only pending or active beats are eligible for reconciliation. Realized,
  skipped, and all terminal beats remain historical.
- Update date and relevant content together so a beat does not retain prose
  claiming the old meeting date.
- Enforce first-meeting uniqueness among live beats.
- Avoid stale aggregate replacement. Fetch fresh state and use a narrow,
  conditional update or equivalent compare-and-update operation so a post-turn
  write cannot overwrite a newer beat status.

### Goals

- Only active goals with a unique, exact, normalized non-empty commitment_key
  may be changed.
- Reconcile the target date and date-bearing goal text from the structured
  post-turn output. Do not attempt free-form historical cleanup.
- Paused, done, abandoned, and other terminal goals remain unchanged.

### Pending Follow-ups

- Only queued or resolving scheduled-promise records with a unique, exact,
  normalized non-empty commitment_key may be changed.
- Recalculate scheduled_for and its delivery-derived deduplication values
  after the time changes.
- Keep delivery_slot_key strictly for its existing delivery-window purpose; it
  is not a commitment key.
- Resolved and cancelled records remain unchanged.

## Implementation Order

1. Re-read this document and confirm the source worktree contains no intended
   partial implementation change.
2. Add domain fields and normalization helper, then update persistence,
   in-memory paths, snapshots, and backup DTOs.
3. Add the additive Alembic migration from t9q4v7x10045.
4. Extend the post-turn contracts, parser, prompt, and known-ID context.
5. Implement schedule cross-date movement and exact matching.
6. Implement story-arc reconciliation with a concurrency-safe narrow update.
7. Implement active-goal and queued-promise reconciliation.
8. Wire all four operations independently into ChatService._do_post_turn()
   with surface-level fail-soft handling.
9. Add focused regression tests, run them, inspect the diff, and update this
   reference if implementation reveals an approved design change.
10. Append the completed result to UPDATE_PROGRESS_LOG.md, then create a
    narrowly scoped local: commit. Do not deploy without a separate user
    request and the workflow's required backup and verification. **Complete**
    for this source-only change; commits `2e61b45`, `a73584d`, `e73f7dd`,
    `838cacf`, and `a339c4e` record the checkpoints.

## Required Regression Coverage

- A meeting moves to a different date across all four live surfaces.
- A move preserves two separate activities at 16:30 and 18:00.
- Exactly one commitment identity is marked as the live first meeting.
- A realized, skipped, cancelled, resolved, memorialized, or otherwise
  historical record is never changed.
- Blank, whitespace-only, legacy, missing, or ambiguous keys do not match.
- A schedule activity can move from a future date bucket to another bucket.
- Story-arc updates cannot overwrite a newly changed status with a stale
  aggregate save.
- Snapshots and backup export/restore retain the new fields.
- Existing scheduled-promise delivery-slot behavior remains intact.
- The proactive 30-minute post-send cooldown behavior remains intact.

## Current Baseline

- Source checkout: C:\Entertainment\yuralume-src
- Branch: local/customizations
- Alembic head at planning time: t9q4v7x10045
- Runtime deployment: untouched for this task
- The previous large patch attempt failed context validation in story_arc.py;
  it did not apply. Do not retry a broad patch. Work in small, verified file
  groups and update this reference as decisions are made.
