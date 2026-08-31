# Same-Space Detail Guidance Reference

## Status

Approved for a source-only prompt adjustment on `local/customizations`. The
goal is to make ordinary web same-space replies describe the immediate
environment, senses, and continuous character actions with more detail while
preserving the existing chat surface and data pipeline. No deployment is part
of this step.

## Problem

The stage branch of the shared chat response-format instruction currently
requires action, expression, and state text to be short and explicitly rejects
an entire prose paragraph inside the `*...*` convention. This biases same-space
replies toward one short action plus one line of dialogue, even when the player
is trying to play a scene with richer local detail.

## Agreed Scope

1. Replace the stage-only wording that suppresses long action descriptions
   with positive guidance to use concrete environment, sensory, spatial,
   pauses, and continuous-action details when the current scene warrants them.
2. Keep the existing `*...*` boundary so the frontend can distinguish action
   spans from speech. Instruct the model to use several moderate spans rather
   than one giant span and to keep each span on one line, matching the current
   parser.
3. Keep the existing player non-invention, schedule, privacy, honesty,
   language, and safety rules intact.
4. Leave phone / Telegram / LINE wording unchanged.
5. Add focused regression assertions for stage-vs-texting prompt separation
   and the new detail guidance.

## Explicit Non-Goals

- No fixed 400–500 character target or length validator.
- No new `response_style` field, UI mode, conversation type, or separate
  Roleplay area.
- No change to `PresenceFrame`, conversation/message schema, streaming
  protocol, billing, cooldowns, or frontend rendering code.
- No change to post-turn memory, state, schedule, arc, goal, promise, or
  persona extraction. The prompt only asks for immediate known details and
  forbids inventing durable facts; existing extraction behavior remains the
  same in this first, reversible step.
- No changes to Telegram, LINE, external messaging, LumeGram, story-scene
  opener/closer, branching drama, or fusion-story prompts.

## Immutable Data and Compatibility Rules

- Existing conversations and messages are read and written exactly as before.
- Existing clients that omit any new field continue to use the same stage or
  texting frame; no request shape changes are introduced.
- The stage prompt remains action/speech compatible with
  `ChatBubble.splitActionSegments`: `*...*` spans contain no newline.
- The texting branch continues to prohibit action narration and keeps its
  short-message guidance byte-for-byte unchanged.
- Richer prose is optional and scene-driven; the model may still answer briefly
  when the player's message does not call for scene elaboration.

## Affected Components

- `src/kokoro_link/infrastructure/prompt/sections/dialogue.py`
- `tests/unit/test_prompt_action_narration.py`
- `tests/unit/test_prompt_builder_presence_frame.py`
- `.codex-round.md`
- `UPDATE_PROGRESS_LOG.md` after verification

## Verification Plan

1. Render a web-stage prompt and assert the new positive detail guidance is
   present while the old blanket prohibition is absent.
2. Render web-DM and Telegram prompts and assert their existing no-action,
   short-text guidance remains present and the stage detail guidance does not
   leak into them.
3. Run focused prompt tests, Python compilation, and `git diff --check`.
4. Commit a narrow `local:` source change. Deploy only after explicit
   approval and a verified backup.

## Ordered Checklist

1. [x] Record the clarified requirement and safety boundaries here.
2. [x] Replace the stage response-format wording.
3. [x] Update focused regression assertions.
4. [x] Refresh the intentional prompt goldens and run focused tests,
   compilation, and diff checks.
5. [x] Commit the verified source change and progress record.
6. [x] Deploy the local app after separate approval and a verified backup.

## Checkpoint

- Current implementation step: stage guidance is deployed to the local app.
- Last verified source commits: `1386a00 local: enrich same-space reply
  guidance`; `caa41a8 local: record same-space guidance checkpoint`.
- Working tree: clean after the deployment-record commit.
- Last tests: `test_prompt_action_narration.py` +
  `test_prompt_builder_presence_frame.py` — 19 passed; `prompt_golden` — 85
  passed; `python -m compileall -q src/kokoro_link/infrastructure/prompt` and
  `git diff --check` passed.
- Golden note: 19 stage-prompt snapshots changed for this instruction. The
  `tools_and_outcomes` snapshot also caught up with the pre-existing source
  wording for an explicit image trigger; its source was not changed here.
- Deployment: user approval received on 2026-08-31. Verified backup
  `pre-same-space-detail-guidance-20260831-231054.dump` (SHA-256
  `86DFF9650FB0CD089208FCB88AA231E72F8C4302AFCDB6C8F1CA839669D4D167`);
  built `yuralume-local/app:custom` image
  `sha256:cda6321024f9eb3927bc6ed38201f1488fba72d13f237b8acdca33234bcc7e3d`;
  the migration gate exited 0; and only `app` was recreated. PostgreSQL,
  storage, WhatsApp sidecar, and volumes were retained.
- Runtime verification: all Compose services are healthy; `/health` returned
  `status=ok`; Alembic is `u2c6m8p10046 (head)`; the container build SHA is
  `caa41a8`; and the container contains the new same-space detail guidance.
- Next action: normal use; no further deployment or data operation is pending.
- Blocked reason: none.
