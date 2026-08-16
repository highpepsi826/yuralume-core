# Pending Proactive Messaging Redesign

This file tracks the agreed local self-host design and its implementation
state. It deliberately contains no private message, character, schedule, or
database data.

## Implementation Status - 2026-08-17

The following work is implemented and verified on `local/customizations` in
source form. It awaits commit and an explicitly approved Docker deployment;
no runtime database rows, character memories, conversations, or schedules have
been changed by this work.

- **Implemented:** opt-in proactive-message policy, low-pressure relational
  messages, unanswered-message elapsed-time cues, narrowed sleep gate, and
  removal of stale deferred-intent refusal feedback.
- **Implemented:** lifecycle metadata and a bounded, fail-soft background
  reconciler for `current_intent`, including a character-owner manual check in
  the Player Goals panel. The action never sends a message by itself.
- **Implemented:** open `scheduled_promise` deduplication at the repository
  and database boundary, plus a read-only duplicate report for legacy rows.
- **Deliberately not implemented yet:** a separate player-facing
  `proactive_frequency` control. `operator_pace_preference` remains a
  dialogue-register preference and has not been repurposed.
- **Still required before rollout:** compare normal chat and background-tick
  latency in the running stack, inspect proactive-attempt reasons for a day,
  and decide separately whether the frequency control is needed.

The two migrations are additive. Existing intent values are treated as legacy
and reviewed conservatively; existing duplicate promise rows are reported but
are never automatically deleted or merged.

## Goal

When a player explicitly enables proactive messages, the character should feel
like an active RP partner: able to miss the player, share ordinary life,
approach after conflict, and show changing emotions. The system must still
prevent literal repetition, coercive messages, accidental overnight delivery,
and unbounded volume.

## Agreed Changes and Implemented Behavior

### 1. Treat proactive messaging as opt-in RP (implemented)

Replace the intention judge's default-silence / reply-pressure framing with:

> The player explicitly enabled proactive messages. Ordinary contact, longing,
> boredom, sharing small events, seeking company, and relationship emotions are
> valid RP motives. A temporary lack of reply is normal and is not, by itself,
> a reason to suppress a message. Control the wording, not whether the
> character may speak: do not demand, guilt, coerce, invent urgency, or require
> an immediate answer.

Remove operative uses of `刷存在感` as a rejection reason. Keep blocking ads,
diary broadcasts, fabricated urgency, and literal duplicate messages.

### 2. Relax the Decider's motive policy (implemented)

Delete this hard rule from `decider_instructions.txt`:

> 不要為了刷存在感而發言；不要抱怨無聊。

Keep the existing no-literal-repeat protection. Keep the unanswered-message
emotional-evolution rule for the first release so its behavior can be observed
after the conservative bias is removed.

### 3. Make unanswered-message emotional evolution explicit (implemented)

Current implementation leaves "new emotional state or angle" entirely to the
LLM. It counts messages sent after the player's most recent recorded turn and
shows their age, but it has no elapsed-time policy, state machine, or evidence
requirement. The dedicated streak prompt also starts only at two unanswered
messages. This is too easy for the model to collapse into "I should not
disturb them."

Desired behavior:

- A recent unanswered message can reasonably lead to initial restraint.
- After meaningful time has passed, the character may naturally become more
  worried, hurt, apologetic, stubborn, protective, or eager to repair the
  relationship, depending on the persona and conversation context.
- That evolution is a valid new motive even when the player still has not
  replied. It must use a genuinely different topic or emotional angle, not a
  paraphrase of the unanswered message.
- A character should not be forced to chase. Persona, relationship context,
  cooldown, daily cap, and anti-duplication protections still apply.
- The system knows only that no new player message was recorded; it must not
  claim to know whether the player read a message.

Implementation direction agreed for the first implementation:

- Surface a single unanswered proactive message as well as a multi-message
  streak, with the actual elapsed time since it was sent.
- Add a prompt-visible elapsed-time cue for the unanswered streak.
- State explicitly that elapsed silence can create a new relational motive;
  "fear of disturbing" alone must not veto it.
- Treat roughly two hours of silence as a prompt-level eligibility milestone,
  not a hard sending trigger. Earlier independent motives remain valid; after
  that point, concern or reconciliation is a valid fresh motive. The exact
  tone and whether to send remain character- and context-dependent.
- Do not encode a universal fixed number of hours that forces every character
  to send. The LLM retains persona-level judgment, but has a clear policy that
  reconciliation / concern after time passes is allowed.
- Add regression cases for an upset or withdrawn player: an early restraint,
  then a later, low-pressure repair attempt that is allowed to send.

### 3a. Allow low-pressure messages that do not demand a reply (implemented)

The current Decider says every proactive message must leave a reply hook. That
is incompatible with a natural repair or reassurance message after conflict:
forcing a question or invitation recreates the reply-pressure problem.

Add a second valid message shape for relationship moments:

- **Conversation-opening message:** has a concrete, easy reply hook.
- **Low-pressure relational message:** may simply acknowledge concern, give
  space, apologise, or express care. It must be personal and connected to the
  relationship, but it must not require a response or end in a repeated
  question.

This is not permission for diary broadcasts. It is limited to a genuine
relationship development and remains subject to the duplicate-topic rule.

### 4. Narrow the quiet-activity gate (implemented)

The gate currently does substring matching, so `睡` and `休息` incorrectly
block normal free time such as `睡前閱讀` and `睡前空閒`.

Keep only actual-sleep terms:

```python
"sleep", "asleep", "nap", "napping",
"睡眠", "安眠", "就寢",
```

Remove `rest`, `resting`, `睡`, and `休息`. Keep the 00:00-07:00 night floor,
cooldown, daily cap, and promise-trigger bypass unchanged.

### 5. Break the deferred-intent refusal loop (implemented)

The current prompt can receive up to five active deferred intents, including
their previous risk and rejection reason. This lets earlier "怕打擾／怕重複"
decisions reinforce themselves.

First implementation should avoid a database migration:

- Supply only the newest representative deferred motive.
- Preserve motive, purpose, expected reply, selected timing, and elapsed time.
- Omit old risk and rejection reason from the prompt, or label them as stale
  history rather than current constraints.
- When `revisit_at` has arrived, state clearly that the selected time is now
  due for a fresh judgment; it is not an instruction to defer again.
- Let existing rows expire through TTL. Do not alter current rows manually.

### 6. Keep `operator_pace_preference` as dialogue pacing (implemented)

Do not redefine upstream `quiet` / `balanced` / `lively`. They remain the
author's cadence controls, which map to daily limit and cooldown.

The codebase already has a persisted per-character prompt preference named
`operator_pace_preference` with these values:

- `more_active`
- `balanced`
- `more_quiet`
- empty / unset

It is currently editable in the admin disposition editor and is rendered as a
fact about what the operator wants from the conversation (for example,
"主動一點 / 多話一點"), alongside observed address, formality, and reply
length. It is therefore a dialogue-register preference, not the character's
intrinsic personality and not an autonomous-send switch.

Do **not** reuse this field for the new proactive-message control. Doing so
would make a player/operator register choice silently change the character's
initiative threshold and could pull the character out of persona. Leaving the
field at the value that matches the desired conversational rhythm is valid,
but the proactive judge must continue to take initiative primarily from
persona, relationship, emotion, and the explicit `proactive_enabled` opt-in.

If a frequency control is added later, make it a separate
player-character/relationship setting, for example `proactive_frequency`:

| UI label | Meaning | Scope |
| --- | --- | --- |
| 跟隨角色 | Let persona and existing cadence decide. | No prompt override. |
| 較少 | Fewer eligible opportunities / longer cooldown. | Scheduler policy only. |
| 自然 | Normal user-selected cadence. | Scheduler policy only. |
| 較多 | More eligible opportunities within hard limits. | Scheduler policy only. |

This setting may adjust opportunity frequency, cooldown, or a bounded daily
cap, but must not rewrite the character's personality, bypass
`proactive_enabled`, night/sleep gates, promise semantics, or literal-topic
deduplication. Keep the explicit preference in its own prompt block only if a
motivation threshold truly needs it; do not mix it into the observed dialogue
register block. Adding this separate setting will require an explicit schema,
backup, and migration decision; it is not a free reuse of the existing field.

### 7. Reconcile stale `current_intent` before it becomes misleading (implemented)

`current_intent` is currently a short-lived string in `CharacterState`, with no
intent-specific timestamp and no link to a schedule. Post-turn processing and
idle drift can replace it, but idle drift runs only when a later player turn
arrives. A silent player can therefore leave an old line such as
"睡醒後再找桃桃" visible indefinitely, even though it never schedules a
message and may no longer fit the character's day.

The fix should be a reconciliation pass in the background character tick (or
an equivalent low-frequency due job), before proactive intention judging:

1. Store `intent_updated_at` and a small source/anchor record when the intent
   is written. The existing post-turn processor should emit these small
   structured fields in its current LLM response; do not add a second LLM call
   just to timestamp or classify a normal intent. An untimestamped legacy value
   is treated as stale/unknown, not as a fresh commitment.
2. Compare the intent's normalized action and time anchor with current and
   upcoming schedule activities, recent promises, conversation state, emotion,
   and the character's local time.
3. Classify it as `valid`, `fulfilled`, `blocked_by_schedule`,
   `needs_schedule`, or `expired/impossible`.
4. For an actionable intent with a concrete time (including a resolvable
   "睡醒後" anchor), create one internal character task or proactive
   candidate when no matching schedule exists. Use an idempotency fingerprint
   so every later tick observes the same task instead of adding another one.
5. If a matching activity already exists, keep the intent linked to it and do
   not create a second schedule. If the activity moves, re-evaluate the anchor
   and update the intent/checkpoint rather than leaving yesterday's text.
6. If the action is fulfilled, past-dated, contradicted, or impossible, clear it
   or ask the state processor for a replacement intent consistent with the
   current schedule. Keep a short audit event so the UI can explain why it
   changed.
7. A vague private thought with no reliable time anchor must not become a
   confirmed appointment with the player. It can remain a candidate for the
   proactive judge or receive a review checkpoint; only an explicit agreement
   creates a shared appointment.

The UI should expose the intent age/status (and, when present, its next review
or scheduled action) so an old sentence is visibly stale instead of looking
like a live plan. Reconciliation must be idempotent and must not send a message
solely because `current_intent` exists; the normal proactive gates still make
the final send decision.

### 7a. Add a manual immediate intent check (implemented)

Add a compact refresh-icon action with a tooltip such as `立即檢查當下意圖`
to the current-intent card in `PlayerGoalsPanel.vue`. It is available to the
character owner/admin and is an explicit request to reconcile only that
character's current intent.

The action has two phases:

1. Run the same cheap deterministic check immediately: reload the latest
   character state and schedule, classify the intent, and persist any safe
   idempotent correction. The UI can show `有效` / `已更新` / `已排入檢查` /
   `已過期` without waiting for an LLM.
2. Only when that check is ambiguous or requires a replacement intent, enqueue
   or join one `manual_intent_reconcile` background job. Return its accepted /
   already-running state to the UI, show an inline progress state, and refresh
   the card when the job completes. "Immediate" means that the check starts
   now, not that an LLM result is forced into the same HTTP response.

The manual path uses the same controls as automatic fallback, plus:

- at most one active manual reconciliation job per character; a second click
  joins the existing job instead of starting another one;
- a short UI debounce for the deterministic pass and a configurable manual LLM
  fallback cooldown (initially five minutes per character);
- a per-character idempotency key and state-version/update-time comparison, so
  a completed manual job cannot overwrite a newer player turn or post-turn
  state update;
- explicit result/audit values such as `unchanged`, `updated`, `scheduled`,
  `cleared`, `queued_for_llm`, `rate_limited`, and `superseded`;
- no bypass of proactive consent, cooldown, sleep/night rules, duplicate-topic
  protection, or the normal send decision. The action never sends an outgoing
  message by itself.

The endpoint should be a separate, owner-authorized action (for example,
`POST .../current-intent/reconcile`), not part of `send_message`. It must reuse
the existing scheduler/job infrastructure and must not introduce a new Docker
process. An LLM-backed manual check may take seconds for the button requester,
but it must not delay, lock, or compete unboundedly with a normal chat turn.

### 8. Deduplicate pending replies and scheduled promises (implemented for new scheduled promises)

There are two different queues that should not be conflated:

- `busy_defer` rows represent a deferred answer in one conversation. Keep at
  most one open row per conversation; append later user messages for audit and
  let the next normal turn cancel/release the row as the existing policy does.
- `scheduled_promise` rows represent a future promised action. Repeated
  post-turn extraction can currently insert a new UUID for the same intent and
  time, so the same promise may appear two or three times.

Use a deterministic promise fingerprint containing at least character,
promise kind, normalized intent, and scheduled instant (optionally the source
conversation when two independent promises are intentionally allowed). Store
it as a `dedupe_key` and enforce uniqueness for open rows at the database
boundary. The repository must handle the insert race, not rely only on an
LLM-side comparison.

When a duplicate arrives:

- retain one canonical open row and one release job;
- merge useful source/audit context;
- keep the clearest confirmed time and intent;
- treat a genuinely different future time as a separate promise only when it
  is not an accidental reschedule of the same action;
- allow a new promise after the old row is resolved/cancelled/expired.

Add a read-only reconciliation/report for existing open duplicates before any
cleanup. Do not delete rows blindly. A promise must also be cancelled or
updated when its underlying appointment is explicitly removed, changed,
fulfilled, or no longer possible, and its one-shot release job must follow the
same state transition. Tests should cover repeated extraction, concurrent
insertion, rescheduling, distinct times, and resolved rows.

## Performance and Foreground-Wait Constraints (agreed)

The redesign must not turn background character maintenance into part of the
player's chat response path. The following are acceptance constraints:

- Do not add a Docker service, a second web request, or a second LLM call for a
  normal player message. Intent metadata is added to the existing post-turn
  result, and promise deduplication is a database operation.
- The self-host path may currently await the existing post-turn extraction;
  that existing wait is the baseline, not a reason to add another synchronous
  stage. The redesign may add a few structured output fields and one
  idempotent persistence lookup to that same stage, but reconciliation and
  new intent-driven schedule creation stay in the background tick.
- Run intent reconciliation in the existing character scheduler/tick. Start
  with deterministic time, schedule, and state checks; inspect only characters
  with a non-empty, stale, or due intent. Do not scan every character on every
  tick.
- An ambiguous or impossible intent may use an LLM fallback, but it must be
  low-frequency, bounded per character, concurrency-limited, and subject to a
  short timeout. A failed fallback must leave the old state untouched for the
  next review rather than delaying chat.
- New intent-driven schedule creation must be asynchronous and idempotent.
  Existing post-turn promise persistence remains one write point, enhanced with
  an indexed lookup/unique `dedupe_key`; never run a full duplicate cleanup
  query inside a player message request.
- Keep added prompt policy compact. The normal Judge/Decider call may receive
  a few more facts, but it must not cause an additional model round trip.
- Background failures are fail-soft: they are logged and retried on a later
  tick, while the player still receives the normal chat response.
- Before and after rollout, record chat p50/p95 latency, LLM calls and tokens
  per turn, background tick duration, and reconciliation fallback count. A
  rollout is not accepted if normal chat gains an extra LLM call or a material
  p95 regression.
- A manual check is an explicit separate request. It may show a short progress
  state while an LLM fallback runs, but it must never delay the normal chat
  request or create more than one active fallback for the same character.

## Implementation Order and Rollout State

1. **Pending rollout measurement:** establish before/after normal chat and
   background-tick latency from the running stack. This is operational
   observation, not a new foreground LLM stage.
2. **Complete:** Judge/Decider policy, unanswered-message emotional evolution,
   low-pressure message shape, quiet-activity tokens, and deferred-intent
   feedback were updated in the existing calls without a new round trip.
3. **Complete:** post-turn and state writers persist intent lifecycle metadata;
   legacy unstructured values remain readable and are treated as stale/unknown.
4. **Complete for future rows:** scheduled-promise deduplication uses a stable
   fingerprint, repository race handling, a partial unique index, and a
   read-only legacy duplicate report. Existing rows are untouched.
5. **Complete:** the background reconciler performs deterministic checks first
   and queues at most two short LLM fallbacks for stale/ambiguous intents.
   It creates only an internal candidate checkpoint, never a shared
   appointment or automatic message.
6. **Complete:** the owner-authorized manual check joins an in-flight review,
   uses a five-minute manual fallback cooldown, and cannot block a chat turn.
7. **Deferred intentionally:** add `proactive_frequency` only after observing
   the new behavior. It must remain separate from `operator_pace_preference`.
8. **Pending deployment:** run migrations after a verified database backup,
   rebuild the local app image, then inspect proactive-attempt reasons and
   latency for one day before considering another adjustment.

## Guardrails That Must Remain

- Per-character daily limit and cooldown.
- 00:00-07:00 local night floor.
- Actual sleep and critically low energy gates.
- Promise fulfilment bypass behavior.
- Literal duplicate / repeated-question protection.
- No coercion, guilt-tripping, fabricated urgency, or demands for immediate
  reply.
- `operator_pace_preference` remains a dialogue-register preference.
- A private `current_intent` never silently becomes a confirmed shared
  appointment.
- Schedule and promise creation is idempotent; existing rows are not deleted
  as part of the first implementation.
