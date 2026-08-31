# Cross-Channel Story Arc Planner Reference

## Status

Approved for implementation on `local/customizations`; source and live data are
unchanged at the start of this work. This reference covers only the normal
LLM-planned story-arc dialogue context. It does not change abandoned-arc
history handling.

## Problem

`StoryArcService._summarize_recent_dialogue()` currently calls
`ConversationRepositoryPort.latest_for_character(..., source="web")`. When an
operator creates or regenerates an LLM-planned daily story, Telegram and LINE
messages are therefore absent even though they are stored for the same
character. The resulting planner context can describe an earlier web state as
if it were current.

The repository already exposes `recent_messages_for_character(...)`, whose SQL
and in-memory implementations merge web, Telegram, LINE, and other channels by
message timestamp. Manual beat reassessment already uses this cross-channel
path.

## Agreed Scope

1. Change the normal StoryArcService recent-dialogue summary helper to use the
   bounded cross-channel message tail, excluding tool-only artifacts.
2. Keep the existing content-tolerance sanitization, dialogue summarizer, and
   fail-soft empty-summary behavior.
3. Apply the helper consistently to its existing callers: new LLM arcs,
   regeneration, season context, and autonomous beat recheck.
4. Add regression coverage proving messages from web, Telegram, and LINE are
   passed to the summarizer in chronological order and then forwarded to the
   planner.

## Explicit Non-Goals

- Do not change abandoned/completed arc history or its anti-repetition context.
- Do not alter templates, beats, schedules, goals, promises, memories,
  cooldowns, or existing conversation rows.
- Do not change the UI or add a new channel selector.
- Do not change the manual reassessment's confirmation or first-meeting rules.
- Do not expose raw message content in logs or API responses.

## Data and Compatibility Rules

- This is a read-path-only change; no migration and no live-data repair are
  required.
- The bounded window remains `_DIALOGUE_CONTEXT_LIMIT` (40 messages), oldest
  first after the repository merge.
- `exclude_tool_only=True` remains enabled so bare tool artifacts do not become
  planner evidence.
- If the repository or summarizer fails, planner creation still receives an
  empty summary exactly as before.
- Legacy callers that explicitly pass `recent_dialogue_summary` keep that
  value; the helper is used only when no override is supplied.

## Affected Components

- `src/kokoro_link/application/services/story_arc_service.py`
- `tests/unit/test_story_arc_dialogue_summary.py`
- `CROSS_CHANNEL_ARC_PLANNER_REFERENCE.md`
- `.codex-round.md` and `UPDATE_PROGRESS_LOG.md` for verified state

## Verification Plan

1. Update the story-arc dialogue-summary tests for the cross-channel contract.
2. Cover web + Telegram + LINE merge order, tool-only exclusion, missing
   history, and summarizer failure.
3. Run the focused StoryArcService/planner/context suites, source compilation,
   and `git diff --check`.
4. Commit a narrow `local:` source change. Deployment is separate and requires
   explicit approval; no deployment is implied by this implementation request.

## Ordered Checklist

1. [x] Inspect repository contract and existing planner callers.
2. [x] Record the cross-channel design and non-goals in this reference.
3. [x] Switch the normal planner summary helper to the merged message tail.
4. [x] Add/update focused regression tests.
5. [x] Verify and update checkpoint; local commit is the next immediate step.
6. [ ] Await separate deployment approval.

## Checkpoint

- Current implementation step: source change and focused verification complete;
  commit and any deployment remain pending.
- Last verified commit: `0471b7c local: record schedule identity hotfix deployment`.
- Working tree: source, tests, and this reference are uncommitted.
- Last test: StoryArcService/planner/context suites — 63 passed; cross-source
  conversation repository suites — 26 passed; broader story-arc / event /
  planner suite — 276 passed; compile and `git diff --check` passed. The
  broader suite's sandbox-only Windows temp permission errors were reproduced
  as environmental and passed unchanged in the local-permission rerun.
- Files changed: `src/kokoro_link/application/services/story_arc_service.py`,
  `tests/unit/test_story_arc_dialogue_summary.py`, and test-only isolation
  updates in `tests/unit/test_story_arc_service.py`.
- Next action: inspect the final diff, update the progress record, and create
  a narrow `local:` commit; deployment requires separate approval.
- Blocked reason: none.
