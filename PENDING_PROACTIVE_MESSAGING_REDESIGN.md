# Pending Proactive Messaging Redesign

This file tracks proposed local self-host changes that have been agreed in
principle but are not yet implemented. It deliberately contains no private
message, character, schedule, or database data.

## Goal

When a player explicitly enables proactive messages, the character should feel
like an active RP partner: able to miss the player, share ordinary life,
approach after conflict, and show changing emotions. The system must still
prevent literal repetition, coercive messages, accidental overnight delivery,
and unbounded volume.

## Agreed Changes

### 1. Treat proactive messaging as opt-in RP

Replace the intention judge's default-silence / reply-pressure framing with:

> The player explicitly enabled proactive messages. Ordinary contact, longing,
> boredom, sharing small events, seeking company, and relationship emotions are
> valid RP motives. A temporary lack of reply is normal and is not, by itself,
> a reason to suppress a message. Control the wording, not whether the
> character may speak: do not demand, guilt, coerce, invent urgency, or require
> an immediate answer.

Remove operative uses of `刷存在感` as a rejection reason. Keep blocking ads,
diary broadcasts, fabricated urgency, and literal duplicate messages.

### 2. Relax the Decider's motive policy

Delete this hard rule from `decider_instructions.txt`:

> 不要為了刷存在感而發言；不要抱怨無聊。

Keep the existing no-literal-repeat protection. Keep the unanswered-message
emotional-evolution rule for the first release so its behavior can be observed
after the conservative bias is removed.

### 3. Make unanswered-message emotional evolution explicit

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

Implementation direction to decide before coding:

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

### 3a. Allow low-pressure messages that do not demand a reply

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

### 4. Narrow the quiet-activity gate

The gate currently does substring matching, so `睡` and `休息` incorrectly
block normal free time such as `睡前閱讀` and `睡前空閒`.

Keep only actual-sleep terms:

```python
"sleep", "asleep", "nap", "napping",
"睡眠", "安眠", "就寢",
```

Remove `rest`, `resting`, `睡`, and `休息`. Keep the 00:00-07:00 night floor,
cooldown, daily cap, and promise-trigger bypass unchanged.

### 5. Break the deferred-intent refusal loop

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

### 6. Separate cadence from autonomous messaging willingness

Do not redefine upstream `quiet` / `balanced` / `lively`. They remain the
author's cadence controls, which map to daily limit and cooldown.

The codebase already has a persisted per-character prompt preference named
`operator_pace_preference` with these values:

- `more_active`
- `balanced`
- `more_quiet`
- empty / unset

It is currently editable in the admin disposition editor and already reaches
the intention judge, but is not exposed beside the normal proactive-message
controls. Prefer reusing this existing field rather than adding a second
database column with overlapping meaning.

Proposed player-facing UI in `ProactiveMessageSetting.vue`:

| UI label | Stored value | Judge effect |
| --- | --- | --- |
| 自主發訊意願：依角色本身 | empty / unset | Preserve legacy per-character behavior; no explicit preference is injected. |
| 自主發訊意願：較低 | `more_quiet` | Preserve slots unless the motive is especially clear. |
| 自主發訊意願：自然 | `balanced` | Ordinary RP motives are valid; no extra push or restraint. |
| 自主發訊意願：較高 | `more_active` | Treat ordinary relational contact and later reconciliation as stronger valid motives, while retaining all hard gates. |

This setting must affect only the LLM's motivational threshold. It must not
silently change daily limit, cooldown, night-hours, sleep gate, promise
behavior, or bypass duplicate-topic protection.

The `more_active` prompt wording must be revised with the same policy as above:
it may encourage initiative, but must not say that the character should avoid
"刷存在感". The explicit player choice should be shown as an authoritative
preference, not weakened into an inferred communication-style signal.

The preference needs a dedicated prompt block in both LLM stages. Today it is
only rendered by the intention judge and is mixed with observed address-style
data; the Decider cannot see it at all. Keep observed address style as its own
fact layer, and render the explicit autonomous-messaging preference separately
for both the intention judge and the Decider.

No migration is required for this UI addition because the field already exists
in the character API, domain model, repository, backup format, and database.

## Implementation Order

1. Update judge / decider prompt policy and focused tests.
2. Narrow quiet-activity tokens and tests.
3. Expose the existing autonomous-messaging preference UI and revise its prompt
   wording; add frontend and backend prompt tests.
4. Reduce deferred-intent feedback and add due-intent regression tests.
5. Build, deploy, observe proactive-attempt reasons for one day, then decide
   whether the unanswered-message policy needs a second adjustment.

## Guardrails That Must Remain

- Per-character daily limit and cooldown.
- 00:00-07:00 local night floor.
- Actual sleep and critically low energy gates.
- Promise fulfilment bypass behavior.
- Literal duplicate / repeated-question protection.
- No coercion, guilt-tripping, fabricated urgency, or demands for immediate
  reply.
