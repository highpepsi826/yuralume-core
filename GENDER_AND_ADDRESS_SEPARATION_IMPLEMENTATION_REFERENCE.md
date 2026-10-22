# Gender / Address Separation Implementation Reference

## Status

Design confirmed (B-lite). Checklist items 1–12 implemented and reviewed in
the working tree; not committed, pushed, or deployed.

Applies to backlog item I-09, remaining work items 1 (player name/gender
injection) and 2 (address mis-read guard).

## Problem

On 2026-10-19 23:09 HKT a chat turn produced the wrong form of address. The
player wrote 「晚安，男朋友，愛你」 (「男朋友」 refers to the character). The
character replied 「晚安，男朋友。我也愛你」 — echoing the term back at the
player.

The diagnostic bundle `yuralume-diagnostic-full-20261022T122440Z.zip`
(window 2026-10-19 23:00–23:30 HKT, export id
`3fd36fce-2ce5-49f6-ac40-07c7a6b6a710`) established three independent
defects. All three are code/architecture defects, not model quality issues.

### Defect 1 — the prompt contains no operator-gender fact

The assembled prompt for the failing turn was 15,610 characters. The string
「性別」 occurs twice; both are the character's own
(`- 性別身份：男性`). The operator side has no gender line at all.

Four candidate channels are all empty by design:

| Channel | Why it was empty |
|---|---|
| `OperatorProfile.pronouns` | Rendered only when set (`identity.py:84-85`). Not set. |
| `OperatorPersona` layer 1 | Field dictionary has no gender key at all. |
| `player_persona_note` | Not filled. |
| Seed `user_profile_notes` | Seed is empty; the whole 起始關係 block is absent. |

The persona extractor's layer-1 dictionary is
`name, nickname, age, occupation, company_or_school, residence, family`
(`llm_extractor.py:71-75`). **Gender can never be learned, regardless of how
many times the player states it.** This is the root cause.

### Defect 2 — the prompt instructs the model to trust the player's self-label

`identity.py:86-89` tells the model:

> 若對方先以特定暱稱**自稱**，優先使用對方剛剛用的版本。

The model read the trailing 「男朋友」 in the player's sentence as a
self-label and reused it. With no gender fact in the prompt, nothing could
contradict that reading.

### Defect 3 — the correction was stored as a rename

The turn after the reply, the prompt contained:

```
- 稱呼：女朋友
- 別稱：桃桃
稱呼變更（關係事件，請自然 acknowledge，不要照稿念）：
- 使用者自 10/19 起希望你改稱呼他為「女朋友」，先前是「桃桃」…
```

The declarative correction 「我是女的！是女朋友！」 was parsed by the
post-turn LLM as an `address_changes` entry with `direction="player"` and
`new_value="女朋友"`, then written to the relationship seed and the rename
log (`chat_service.py:8024`, `source=SOURCE_OBSERVED`).

The system therefore did not record "the player is female". It recorded
"call the player 女朋友" — a term that is both wrong as an address form and
evidence that the gender fact was lost.

### Why prompt rules alone did not prevent Defect 3

`data/prompts/post_turn/processor.txt:234-253` already excludes this case
under three separate rules:

- (a) stating an existing form of address is not a rename request;
- (e) using a kinship or affectionate term **to address the character**
  (e.g. a partner calling the character 老公/寶貝) is never
  `direction="player"`;
- the closing criterion requires an imperative, deliberate instruction
  ("必須是對方**祈使式、刻意指定**" and "模糊或不確定就給空陣列").

None of them fired. The reason is structural: **there is no Python-side
check on this path.**

- `_parse_address_changes` (`llm_processor.py:753-800`) validates only
  `direction ∈ {player, character}`, non-empty `new_value`, and
  `subject == "operator_self"` for the player direction. It never inspects
  the text.
- `AddressChangeSignal.source_text` is parsed, carried on the DTO, then
  discarded. It is never substring-checked, never persisted, never logged.
  `RelationshipNamesService.update_names` has no `source_text` parameter and
  `AddressChangeEvent` has no such field.
- No test anywhere asserts that a non-imperative self-description produces
  no address change. All 16 existing tests in
  `test_post_turn_address_changes.py` and
  `test_chat_observed_address_changes.py` reject on structural grounds only.

Contrast: the persona extractor **does** have a verbatim-quote guard
(`llm_extractor.py:321-324`). The address path has no equivalent.

## Agreed Scope

Two parts. Part 1 fixes the root cause; Part 2 stops the address channel
from absorbing declarative self-descriptions.

Plan B was chosen over plan A. Plan A (downgrade `source=observed` renames
to pending candidates that require repetition or an explicit imperative
before promotion) is **not adopted**; see Non-Goals.

### Part 1 — `gender` as a learned layer-1 persona field

Add `gender` to the layer-1 persona vocabulary so the character can learn
and retain the player's gender from conversation, with the same
confidence and evidence discipline as every other layer-1 fact.

Requirements:

1. `gender` is added to the extractor's layer-1 dictionary
   (`llm_extractor.py:71-75`).
2. `gender` **must** carry `subject == "operator_self"`, like `name` and
   `nickname`. A player saying 「我朋友是女的」 or 「我妹是女的」 must not set
   the operator's gender. This requires a new self-attribution gate, because
   the existing gate `_IDENTITY_FIELD_KEYS` (`llm_extractor.py:100`)
   semantically means "fields that NAME the operator" and is reused by
   `relationship_coherence_service.py:57` and `address_resolver.py:147` for
   address resolution. Adding `gender` there would be wrong.
   → Introduce a separate `_SELF_FACT_FIELD_KEYS` set (starts as
   `{"gender"}`) enforced where `_IDENTITY_FIELD_KEYS` is enforced today
   (`llm_extractor.py:348-352`), leaving the name/address sets untouched.
3. The value is free text in the operator's content language (e.g. 「女性」
   「男性」「非二元」), not an enum. An enum would both violate the
   LLM-first rule and exclude players whose gender does not fit two values.
4. Dream consolidation must accept the key: `llm_consolidator.py:70-74`
   maintains a **second, independent** `_LAYER_FIELD_KEYS`. Missing it there
   means promote/merge/supersede/infer silently reject the field.
5. Prompt rendering: add `gender` to `_LAYER1_RENDER_ORDER`
   (`operator_persona_service.py:77-80`) and a clause to
   `_format_layer1_clause` (`:480-495`). Without the render-order entry the
   field is learned and stored but never shown — exactly the live `family`
   bug described in Observations.
6. Player-facing projection: add `gender` to `_LAYER1_SAFE_LABELS`
   (`operator_persona_projection_service.py:43-50`) so the player can see
   and correct what the character believes. This is deliberate: a wrong
   gender the player cannot inspect is how the original bug stayed
   invisible.
7. Frontend labels: add the key to `OperatorPersonaPanel.vue`'s
   `FIELD_LABEL_KEY` and to the `operatorPersona.fields.*` bundles in
   `en-US.ts`, `ja-JP.ts`, `zh-TW.ts`, plus
   `memoir.personaProjection.factLabels.*`. Without these the UI falls back
   to the raw key `gender`.
8. No migration. `field_key` is a plain `String(64)` with a non-unique
   index; the only table constraint is a uniqueness tuple. The whitelist
   lives entirely in Python.

### Part 2 — address channel must carry validated evidence

The address channel must not be able to consume a declarative
self-description. Two layers, both required:

**2a. Prompt-level separation (already partly present, made explicit).**
`processor.txt` `address_changes` section gains an explicit routing rule:
a declarative statement about the player's own identity (gender, age,
occupation) is a **persona fact**, not an address change, and belongs to
the persona extractor; the address channel is reserved for an instruction
about what to call someone. This alone is not sufficient (see Defect 3) but
keeps the two channels coherent.

**2b. Code-level evidence guard.** `source_text` stops being decorative:

- `_parse_response` must receive the player's message text. It currently
  does not (`llm_processor.py:573-585`), so the guard cannot run at parse
  time. Thread `user_message` through from `process()`
  (`llm_processor.py:124-152`, `:217`, `:296`) into `_parse_response`
  (`:198`).
- An `address_changes` entry whose `source_text` is not a verbatim substring
  of the player's message is dropped. This mirrors the persona extractor's
  existing guard (`llm_extractor.py:321-324`).
- An entry with empty `source_text` is dropped. An unquotable rename is not
  a rename.

**Decision required — 2c.** The 2b guard does not block the observed case,
because 「我是女的」 genuinely appears in the player's message. Two options:

- **Option B-lite (recommended).** Accept that the residual risk is handled
  by Part 1: once gender is a learned fact, the prompt carries
  `性別：女性`, and the same turn that misfires the address channel also
  produces the correct gender fact. The wrong address term is then
  contradicted by a stronger, inspectable fact. Cost: no new LLM call, no
  new feature key. Residual risk: a brand-new player whose first statement
  of gender is also phrased as an address correction could still get one
  bad rename row.
- **Option B-strict.** Add a narrow verifier that judges whether the quoted
  span is an imperative rename instruction, modelled on the existing
  verifier pattern (`LLMDisclosureJudge`, `LLMOutcomeClaimJudge`,
  `LLMStoryBeatRechecker`, `LLMRelationshipCoherenceDetector`). Cost: a new
  feature key requiring `feature_keys.py` registration (`GLOBAL_FEATURE_KEYS`,
  `FEATURE_LABELS`, one `FEATURE_GROUP_MEMBERS` group), the generated
  `contracts/feature-key-manifest.json` export, and three frontend i18n
  bundles. Also one more LLM call per turn that produces any address
  change (which is rare).

**Decision (confirmed 2026-10-22).** **B-lite is adopted.** No verifier LLM
call, no new feature key, no contract-manifest export. The residual risk is
accepted deliberately: a brand-new player whose first statement of gender is
also phrased as an address correction could still produce one bad rename row,
because the 2b guard cannot reject a genuine verbatim quote. Part 1 is what
makes that state recoverable — the same turn records the correct gender fact,
and the player can see and correct it in the persona projection.

Rationale for rejecting B-strict at this time: its cost is paid on every
deployment surface (feature-key registry, generated manifest, three i18n
bundles) to guard a rare path, and Part 1 independently removes the
user-visible symptom. If a second mis-read is observed after this ships,
revisit B-strict with that incident as evidence.

## Explicit Non-Goals

- **Plan A is not adopted.** Observed renames are not downgraded to pending
  candidates and do not gain a repetition threshold. `source=SOURCE_OBSERVED`
  keeps writing the seed directly.
- **No enum or constraint on gender.** No two-value assumption.
- **`OperatorProfile.pronouns` is not changed.** It remains a manual,
  optional field. Part 1 does not depend on it. (Note: the frontend has no
  input for it today — `PersonalSettingsSection.vue` only edits
  `display_name`. Wiring it is separate work, and unnecessary once gender is
  learned.)
- **No change to `identity.py:86-89`** (the "prefer the player's recent
  self-label" instruction). It is correct when a gender fact exists; the
  defect was the missing fact, not this line.
- **`family` projection gap and the `character_service` layer mismatch are
  not fixed here.** See Observations. They are recorded so the next person
  does not rediscover them.
- **No rewrite of existing memory or history.** Old recollections keep the
  wording they were stored with.

## Immutable Data Rules

- Do not modify existing characters, chat history, schedules, deferred
  intents, scheduled promises, or memories.
- Do not backfill or repair persona rows as part of this change.
- No migration. This is an app-only release.
- `CONFIG_ENCRYPTION_KEY` and all secrets remain untouched.

## Affected Components

| Component | Change |
|---|---|
| `infrastructure/persona/llm_extractor.py` | `_LAYER_FIELD_KEYS[1]` + new `_SELF_FACT_FIELD_KEYS` |
| `infrastructure/persona/llm_consolidator.py` | mirror `_LAYER_FIELD_KEYS[1]` (second copy) |
| `application/services/operator_persona_service.py` | `_LAYER1_RENDER_ORDER`, `_format_layer1_clause` |
| `application/services/operator_persona_projection_service.py` | `_LAYER1_SAFE_LABELS` |
| `data/prompts/persona/extractor.txt` | rule 6 area: gender requires `operator_self` |
| `data/prompts/post_turn/processor.txt` | `address_changes`: declarative-vs-imperative routing |
| `infrastructure/post_turn/llm_processor.py` | thread `user_message`; substring guard in `_parse_address_changes` |
| `frontend/src/components/OperatorPersonaPanel.vue` | `FIELD_LABEL_KEY` |
| `frontend/src/i18n/locales/{en-US,ja-JP,zh-TW}.ts` | persona field + projection fact labels |

Explicitly **not** touched: `domain/entities/operator_profile.py`,
`domain/services/address_resolver.py`,
`infrastructure/prompt/sections/identity.py`, `relationship_names_service.py`,
`chat_service.py`.

## Migration and Compatibility

- No schema change. `field_key` is `String(64)`, free-form; adding a value
  needs no migration.
- Existing personas are unaffected: no row gains or loses a field.
- Existing renames already written to seeds and the rename log are not
  reverted by this change. Where a wrong rename is currently live, it needs
  a separate, explicitly approved data repair (see Pending Items).
- Prompt golden snapshots: `MARKER_OPERATOR_IDENTITY` is present in
  `full_material`, `operator_persona_five_layers`, `address_change_lines`
  and absent in `minimal`
  (`tests/unit/prompt_golden/cases.py`). Adding a rendered `gender` clause
  changes `operator_persona_five_layers` and any case carrying a layer-1
  fact. Snapshots must be regenerated deliberately, not blindly.
- Rollback: reverting the app image restores prior behaviour; no data
  written by this change needs undoing, since no row is mutated.

## Test Cases

New:

1. `gender` extracted from 「我是女的」 with `subject="operator_self"` is
   accepted as a candidate.
2. `gender` extracted from 「我朋友是女的」 with `subject="other_person"` is
   rejected (self-attribution gate).
3. `gender` missing `subject` is rejected, matching the existing
   name/nickname policy.
4. Dream consolidation accepts a `gender` promote/merge action (guards the
   second whitelist copy in `llm_consolidator.py`).
5. A layer-1 `gender` field at confidence 0.7+ renders in the prompt
   `對方資料` line.
6. A layer-1 `gender` field appears in the player-facing projection facts.
7. `_parse_address_changes` drops an entry whose `source_text` is not a
   substring of the player's message.
8. `_parse_address_changes` drops an entry with empty `source_text`.
9. Regression: the exact 2026-10-19 input
   （player 「我是女的！是女朋友！你又打錯了！」） still produces no address
   change under the new prompt + guard. This is the acceptance test for the
   whole document.
10. Guard against whitelist drift: assert `llm_extractor._LAYER_FIELD_KEYS[1]`
    and `llm_consolidator._LAYER_FIELD_KEYS[1]` are equal. No such test
    exists today; the two copies are already unguarded.

Updated:

- `tests/unit/prompt_golden/cases.py` snapshots carrying layer-1 facts.

Known pre-existing failures, unrelated, must not be used as a pass signal:
`test_character_backup_registry` (missing `diagnostic_events` registration),
`test_feature_key_manifest` (artifact path resolves outside this checkout —
`_REPO_ROOT` is `C:\Entertainment`, artifact lives in the sibling cloud
repo), and the `style_instruction` template tests.

## Deployment Status

Not started. When implementation is confirmed and merged, follow the standard
release path in `AGENTS.md`: commit, push `local/customizations`, wait for
the immutable image, pin the four app roles to the digest, deploy, verify six
services healthy, `/health` ok, representative media, admin login, single
Telegram polling owner. No migration boundary is crossed.

## Pending Items

1. **Live wrong rename.** The 10/19 bundle shows the seed set to
   `稱呼：女朋友`. Whether that row is still live has not been checked. One
   read-only query would confirm it and would also locate the first
   (earlier, unknown-date) mis-gender occurrence. Confirmation of the
   symptom is already sufficient for design; this is cleanup scoping only.
   Any correction is a production data write and needs explicit approval.
2. **First mis-gender occurrence.** Not located. Same root cause; deferred
   with item 1, not required for design.
3. **`dialogue_checkpoints` still empty.** Observation carried from the
   previous session; no action until enough turns accumulate.

## Observations (out of scope, recorded to avoid rediscovery)

- `family` is extracted (`_LAYER_FIELD_KEYS[1]`) and rendered
  (`_LAYER1_RENDER_ORDER`, `_format_layer1_clause:492`) but is **absent**
  from `_LAYER1_SAFE_LABELS`, so it never reaches the player-facing
  projection. Adding `gender` to both lists would fix the class of bug;
  `family` itself is left alone here.
- `character_service.py:202-205` seeds `occupation` and
  `company_or_school` at **layer 2**, while the extractor and the render
  order place them at **layer 1**. Seeded values therefore land where
  neither renderer looks. Pre-existing, unrelated to this change.

## Ordered Implementation Checklist

- [ ] 1. Confirm Option B-lite vs B-strict (section "Decision required — 2c").
- [ ] 2. `llm_extractor.py`: add `gender` to `_LAYER_FIELD_KEYS[1]`; add
      `_SELF_FACT_FIELD_KEYS = frozenset({"gender"})` and extend the
      self-attribution gate at `:348-352` to require `operator_self` for it.
- [ ] 3. `llm_consolidator.py`: mirror the key into its own
      `_LAYER_FIELD_KEYS[1]`.
- [ ] 4. `extractor.txt`: state that gender must be `operator_self` and must
      quote the player verbatim.
- [ ] 5. `operator_persona_service.py`: add `gender` to
      `_LAYER1_RENDER_ORDER` and a clause to `_format_layer1_clause`.
- [ ] 6. `operator_persona_projection_service.py`: add `gender` to
      `_LAYER1_SAFE_LABELS`.
- [ ] 7. Frontend: `FIELD_LABEL_KEY` + locale bundles for the new key.
- [ ] 8. `llm_processor.py`: thread `user_message` into `_parse_response`
      (signature at `:573`, call at `:198`, origin at `:124-152`, `:296`).
- [ ] 9. `llm_processor.py`: substring + non-empty `source_text` guard in
      `_parse_address_changes`.
- [ ] 10. `processor.txt`: declarative-vs-imperative routing rule.
- [ ] 11. Tests 1–10 above; regenerate golden snapshots deliberately.
- [ ] 12. Run unit tests; record which failures are the known pre-existing
      ones.
- [ ] 13. Update `.codex-round.md` and `UPDATE_PROGRESS_LOG.md`, marked
      `(by Claude)`.
- [ ] 14. Release per `AGENTS.md` after explicit approval.

## Change Log

- 2026-10-22 Created from the 2026-10-19 diagnostic bundle.
  Plan B (gender/address separation) chosen over plan A at the user's
  direction. (by Claude)
- 2026-10-22 B-lite confirmed. Items 2–12 implemented via the implementer
  subagent; `_parse_address_changes` takes `user_message` as an optional
  keyword (None skips the guard) so existing direct-call tests keep working,
  while `process()` always supplies it. Added a test pinning the accepted
  residual risk. (by Claude)
