# Proactive Intention Judge Prompt Fix Reference

## Problem

The proactive intention judge crashes while rendering an active deferred intent
that has a non-null `revisit_at`. The refactored
`_optional_deferred_intents_block()` builds its lines in `body`, but the
elapsed-time branch calls an undefined `parts` variable. The exception is
reported as `intention judge raised` and prevents the judge's LLM call.

## Approved Scope

- Replace the stale variable use with the already-built `body` list.
- Keep the existing wording and timing semantics for deferred intents.
- Add regression coverage for a future and an already-due `revisit_at`.
- Build and deploy only the local `app` image after tests pass.
- Preserve the real-message 30-minute proactive cooldown and all deferred-intent
  rows, audit history, conversations, schedules, goals, and memories.

## Explicit Non-Goals

- Do not delete or rewrite the historical `errored` audit rows.
- Do not clear or reschedule the active deferred intent.
- Do not change which proactive outcomes anchor cooldown.
- Do not change provider configuration, payload format, prompts beyond the
  undefined-variable fix, or database schema.

## Verification Plan

1. Add the scoped regression test and run the intention-judge test module.
2. Run the broader proactive dispatcher/scheduler tests, compile, and diff
   checks.
3. Commit the source/reference change with a `local:` commit.
4. Create and verify a PostgreSQL custom-format backup before app recreation.
5. Build the local image, run the existing migrate service, and recreate only
   `app`.
6. Verify Compose health, `/health`, runtime commit, and that the deferred
   intent remains intact. Confirm no new `NameError` appears in subsequent
   scheduler logs.

## Status

Source fix and focused regression verification are complete; source commit
`c574ddb` is recorded. Backup and app-only deployment remain.

## Verification So Far

- `tests/unit/test_llm_proactive_intention_judge.py`: 33 passed.
- Proactive dispatcher/deferred-intent/attempt/scheduler suite: 77 passed.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- No live data or database schema change is part of this fix.

## Deployment Checkpoint

- The running stack remains on the previous app image until the backup is
  verified.
- Next action: create a fresh PostgreSQL custom-format dump, then rebuild and
  recreate only `app` with `c574ddb`.
