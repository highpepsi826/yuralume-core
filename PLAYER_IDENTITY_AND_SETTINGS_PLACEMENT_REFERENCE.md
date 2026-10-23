# Player Identity and Settings Placement — Implementation Reference

## Status

Design drafted 2026-10-23. **Awaiting explicit user approval. No code,
migration, data, or deployment operation has been performed.**

Applies to backlog item I-09 (continuation) and item I-12 (player profile
fields).

Owner decisions already taken (this session):

| Item | Decision |
|---|---|
| (a) Playground placement | Move to the **end** of the 全域體驗偏好 group |
| (b) Gender / pronoun input | Add a UI control writing the existing `OperatorProfile.pronouns` |
| (c) `player_persona_note` global scope | **Defer** — re-evaluate after (b) ships |
| (d) Empty-allowlist persona gap | **Require exactly one allowlisted sender**; do not loosen the gate |

## Problem

Three independent defects surfaced while closing the 10/19 mis-address
incident. They are unrelated in cause and are listed separately so each can
be reviewed and shipped on its own.

### Defect A — the Playground studio opens 設定

`PromptCustomizationSetting` is the first child of the 全域體驗偏好 group
(`frontend/src/components/PersonalSettingsSection.vue:245-248`). It is a full
studio UI, so opening the preferences tab shows a prompt-editing surface
before any preference. It was added in commit `2947918`; nothing was removed.

Secondary finding: the component uses zero `t()` calls — every string is
hardcoded Chinese, so it cannot follow the locale. That is out of scope here
(see Non-goals) but is recorded so it is not mistaken for a new regression.

### Defect B — there is no structured player gender

Verified on 2026-10-23:

- `operator_profiles.pronouns` exists (`models.py:1825`, `String(64)`,
  nullable) with entity, DTO, service update path and frontend type all in
  place. **No component ever sends it**, so the column is `null` in
  production and the field has never had a value.
- The field's own docstring calls it reserved
  (`domain/entities/operator_profile.py:14`), which is why the UI was never
  built.
- It **is** rendered in the live chat prompt at
  `infrastructure/prompt/sections/identity.py:82-84` (resolved-address
  branch) and `:96-97` (fallback branch), and in the post-turn extractor at
  `infrastructure/post_turn/llm_processor.py:444-445`.
- `_render_operator_block` returns `[]` entirely when `operator is None or
  not operator.has_real_name()` (`identity.py:91-92`). This is **not** a
  pronoun/name-confusion guard. Per its docstring (`identity.py:59-63`) it
  exists so that a profile with no saved name keeps the legacy 「使用者」
  wording everywhere else in the prompt consistent — the block is only
  opened once there is a name to attach to the role label.
- `has_real_name()` is a sentinel comparison against
  `DEFAULT_OPERATOR_DISPLAY_NAME = "操作者"` (`operator_profile.py:197`),
  so the guard fires only for profiles that never filled in a display name.
  The production owner profile is `display_name = 桃桃`, i.e. the guard does
  **not** apply here and the block already renders.
- Layer-1 persona gender was added by commit `e9339a7` and renders as
  「性別：X」 inside the 「對方資料」 line
  (`operator_persona_service.py:77-80, 480-486`).

So today the only gender channel that can fire is the *learned* one, which
requires the player to state it and the extractor to accept it — the exact
path that failed on 10/19.

### Defect C — empty allowlist silently suppresses the owner's persona

`persona_safe_for_account` (`persona_disclosure_gate.py:29-40`) returns True
only when exactly one non-empty sender ref is configured. The same empty
value means "accept anyone" inbound (`messaging_dispatcher.py:204`,
`MessagingAccount.is_sender_allowed`).

Consequences on the production Telegram account (`allowed_sender_refs_json
= []`, verified read-only 2026-10-23):

- `operator_persona_enabled=False` is passed at
  `messaging_dispatcher.py:244`.
- The prompt omits the learned persona, the player persona note
  (`chat_service.py:6397-6402`) and the resolved address
  (`chat_service.py:6564-6565`).
- No error, no log, no UI signal. The player's own 279-character
  self-description has never reached a Telegram turn since the feature
  shipped on 2026-08-23.

The gate's strictness is **correct** — a shared or group account genuinely
would leak the owner's declared persona. The defect is that "empty" is a
reachable, silently-lossy configuration with no UX preventing it.

### Defect D — address writes are not gated although address reads are

Confirmed by code and by production evidence.

- `run_post_turn` loads the operator unconditionally
  (`chat_service.py:7429`) and never consults `persona_enabled`.
- `_apply_observed_address_changes` (`chat_service.py:7792-7797`) therefore
  runs even when the prompt suppressed the persona.
- Production `operator_address_change_log` contains exactly one row:
  player/observed 桃桃→女朋友 at `2026-10-19 15:12:43Z`, source
  `telegram`, and every message in that window has
  `conversations.source='telegram'`. It has never been corrected.

This asymmetry is what let a blind, persona-less turn commit a durable
rename. It is a separate defect from C: even with a correct allowlist, a
turn where persona is off for any other reason should not write persona
derived state.

## Agreed scope

1. **(a)** Move `PromptCustomizationSetting` to the end of the 全域體驗偏好
   group in `PersonalSettingsSection.vue`, after the last existing item in
   that group. No behaviour change to the component itself.
2. **(b)** Add a pronoun input to the identity block at the top of
   `PersonalSettingsSection.vue` (next to 顯示名稱), reading and writing
   `OperatorProfile.pronouns` through the existing
   `updateOperatorProfile` client.
3. **(d1)** Telegram allowlist UX: make the single-sender requirement
   explicit, and surface the consequence of an empty allowlist in the UI.
   **Amendment 2026-10-24:** the warning must also be visible while the
   account card is collapsed. The first implementation put it only inside
   `account-detail` (`ChannelBindingsPanel.vue:697`, gated by
   `v-if="expandedAccountId === account.id"`), so a collapsed card still
   showed only 「啟用」 plus 「最近一次成功連線：N 秒前」 — the exact pair that
   convinced the owner the channel was working during the migration that
   lost the allowlist. The warning now also renders in the summary row.
4. **(d2)** Stop the post-turn address-change write when the turn ran with
   the persona suppressed.

## Explicit non-goals

- **No** global `player_persona_note` (decision (c) deferred). No new table,
  no nullable `character_id`, no fallback merge rule.
- **No** loosening of `persona_safe_for_account`. Its contract is unchanged.
- **No** change to the persona-note or persona-extraction prompt blocks
  beyond the gating fix in (d2).
- **No** migration. Every field touched already exists.
- **No** i18n sweep of `PromptCustomizationSetting`'s hardcoded strings. It is
  recorded as a separate follow-up.
- **No** correction of the live 「女朋友」 seed or address row. That is a
  separate, explicitly approved data write (see Immutable data).
- **No** change to `PlayerPersonaNote` cardinality or ceiling.

## Immutable data rules

- Do not rewrite, delete, or "fix up" `operator_address_change_log`,
  `player_persona_notes`, `characters`, chat history, schedules, deferred
  intents, or character records as part of this work.
- The 10/19 「女朋友」 rename stays in place. Repairing it requires its own
  approval and its own reference.
- Any deployment is app-only. `postgresql` and `storage` images, volumes,
  secrets and role environments are untouched.
- Do not print or log allowlist values, credentials, or message content.

## Affected components

Backend (b, d2):

- `api/routes/operator.py`, `application/dto/operator.py`,
  `application/services/operator_profile_service.py` — already accept
  `pronouns`; expected to need **no change**. Verify, do not assume.
- `application/services/chat_service.py:7429` and `:7792-7797` — pass the
  existing `persona_enabled` flag into the address-change write.
- `application/services/persona_disclosure_gate.py` — **read only**. Do not
  modify.

Frontend (a, b, d1):

- `components/PersonalSettingsSection.vue` — reorder (a); pronoun field (b).
- `components/ChannelBindingsPanel.vue` — allowlist messaging (d1).
- `types/operator.ts` — `pronouns` already declared; verify only.
- `i18n/locales/{zh-TW,en-US,ja-JP}.ts` — new keys under
  `playerSidebar.pronouns.*` and `channelBindingsPanel.allowlist.*`.
- `utils/api/operatorProfile.ts` — already forwards the payload; verify.

## Migration and compatibility plan

None. No schema change, no data rewrite, no new endpoint.

Compatibility notes:

- The prompt assembly is **unchanged**. `pronouns` is already rendered at
  `identity.py:82-84` and `:96-97`, and the owner profile already passes the
  `has_real_name()` gate. No prompt, DTO, service or route change is expected
  for (b): the work is the missing frontend control only.
- The `has_real_name()` gate is left exactly as it is. A profile that never
  filled a display name will still render no 對方身份 block, pronoun or not.
  This is the documented, intended behaviour and is out of scope.
- Existing empty-allowlist accounts keep behaving as they do today unless
  (d1) changes validation. If (d1) rejects empty allowlists on write, it must
  not retroactively disable the one existing account.

## Test cases

1. `PersonalSettingsSection` renders Chat Assist before the Playground studio
   in 全域體驗偏好; Playground remains reachable.
2. Saving a pronoun persists it and survives a reload; clearing it writes
   `null` (entity trims to None) rather than an empty string.
3. Prompt rendering: pronoun appears in 對方身份 only when a display name
   exists; a pronoun without a display name renders no block (pins the
   documented dependency).
4. Prompt rendering: layer-1 learned gender and a configured pronoun both
   appear without contradiction (one in 對方資料, one in 代名詞).
5. `persona_safe_for_account`: `[]`, `["a","b"]` → False; `["a"]` → True;
   whitespace/empty entries ignored. (Pin; do not change behaviour.)
6. Post-turn with `persona_enabled=False`: no `operator_address_change_log`
   row is written and no seed address is mutated; with True, the existing
   behaviour is unchanged.
7. Allowlist UX: empty value is either rejected on save or renders a visible
   warning naming the consequence; a single value is accepted silently.

## Deployment status

Not started. No commit, no push, no image publication, no Coolify action.
Release is app-only and requires separate user authorization once the diff
is reviewed.

## Ordered implementation checklist

1. Re-read this file in-context.
2. Verify the backend `pronouns` path end-to-end. Expected result: no backend
   change needed. If verification shows otherwise, stop and report rather than
   widening scope.
3. (a) Reorder `PromptCustomizationSetting`; update nothing inside it.
4. (b) Add the pronoun input with zh-TW/en-US/ja-JP keys and the
   display-name dependency hint.
5. (d2) Thread `persona_enabled` into `_apply_observed_address_changes`.
6. (d1) Allowlist validation/warning in `ChannelBindingsPanel`, rendered in
   BOTH the collapsed summary row and the expanded detail block.
7. Run targeted suites: frontend component tests, i18n completeness, prompt
   section tests, post-turn gating tests, disclosure-gate test.
8. Review the diff in the main session against this file.
9. Report; request commit + release authorization.

## Follow-ups recorded, not in scope

- `PromptCustomizationSetting` hardcoded strings (needs a design pass).
- Decision (c): global `player_persona_note`, to be reconsidered after (b).
- Read-only production repair of the 「女朋友」 seed, if the user wants it.
