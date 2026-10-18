# Prompt Customization Implementation Reference

## Problem

Yuralume uses many LLM prompts for chat, LumeGram, proactive behaviour,
schedule/state maintenance, and media generation. Most prompt wording is held
in the shipped prompt pack or Python prompt builders. The existing external
prompt-pack overlay is useful to a deployment operator but is not a safe,
role-aware product setting for players.

Players need to inspect and directly edit the prompt templates that control
their visible experience, rather than guessing at an opaque additive style
layer. They must still be unable to replace character identity, factual
context, safety/role boundaries, tool instructions, output contracts, or
scheduling rules. An administrator needs controlled access to all registered
templates, with explicit warnings for high-impact ones.

## Agreed Scope

Replace the first additive prompt-customization release with a database-backed
Prompt Studio and two independent template-override scopes:

1. Player-owned template overrides, scoped to the signed-in player and only
   available for selected visible-experience templates.
2. Administrator-owned global template overrides, available for all registered
   templates and explicitly marked when high impact.

The first player-visible template catalogue covers:

- Chat response style.
- LumeGram caption style.
- LumeGram visual/media style, including image and video prompts.
- Proactive-message tone.

The administrator catalogue additionally covers registered background prompts
such as memory/persona extraction, schedule planning, intention judgement and
quality gates. Each entry has a stable logical template name, title, category,
impact description, sensitivity level, and allowed placeholder names.

## Explicit Non-goals

- No player access to important/background templates: role boundary, memory,
  schedule/state mutation, tool selection, output schemas, JSON contracts,
  safety rules, billing/quota rules, or evaluation/judgement prompts.
- No editing of another user's customization.
- No migration of existing prompt-pack files or environment overlay behavior.
- No production data migration or modification of existing
  characters, messages, feed posts, schedules, promises, or provider secrets.

## Data and Authorization Model

Store template overrides in the existing `app_preferences` repository through
its scoped preference helpers. A player record lives under a hashed user-scoped
key; global administrator overrides use one unscoped key.

Each record is a bounded map of registered template names to raw template text.
Empty or absent values mean use the shipped template. Validation enforces a
per-template maximum length, trims whitespace, rejects control characters,
requires the template's original placeholder set to remain valid, and rejects
unregistered names. Admin overrides win over shipped templates; a player
override wins only for a player-editable template and only in that player's
request scope.

Player API routes require the authenticated user and always read/write only
that user's record. Global API routes require `require_admin`. Admin UI must
mark each high-impact entry as `重要 prompt：改動會影響…`, show the concrete
impact description and allowed variables, and expose reset-to-default.

## Prompt Composition Rules

Prompt assembly keeps its existing dynamic composition. A template override
replaces only the static template fetched by `PromptLoader`; dynamic variables
such as character details, memory, time, schedule and recent dialogue are
still substituted or assembled per request. The Studio editor shows template
source and required placeholders; it must not expose private live
conversation, memory, secrets or another user's data.

## Affected Components

- Prompt template registry, override repository/service and scoped loader.
- Player-facing Prompt Studio plus admin Prompt Studio.
- Prompt loader integration and prompt-pack hash inclusion for stored overrides.
- Removal of additive prompt-customization blocks from chat, LumeGram and
  proactive flows.
- API/frontend unit tests, localization, and prompt-pack/usage observability
  metadata where practical.

## Compatibility and Runtime Plan

The feature uses the existing preference table; no schema migration is needed.
All absent settings preserve current prompt bytes and behaviour. Loader access
must be request-scoped so a player override cannot leak into a background task
or another user's request. If preferences cannot be read, it must safely fall
back to admin/shipped templates rather than fail a generation.

## Acceptance Tests

1. A player can list, read, save and reset only allowed style templates.
2. A non-admin cannot list/read/write important or admin-only templates.
3. An admin can list, read, save and reset all registered templates;
   high-impact warnings name the affected workflows.
4. Empty/reset overrides reproduce shipped/admin effective template bytes.
5. Placeholder validation rejects missing/unknown placeholders before storage.
6. Per-player overrides do not leak across users or background work.
7. Prompt-pack hashes change when an effective override changes.
8. Existing prompt loader external-overlay and focused prompt/service
   regressions pass.

## Ordered Implementation Checklist

1. Completed: inventory prompt templates and existing loader paths.
2. Completed: build registry and request-scoped override mechanism.
3. Completed: replace additive first-release UI/API with Prompt Studio.
4. Completed: remove additive prompt blocks and verify effective-template behavior.
5. Completed locally: backend/frontend validation and review; commit and deploy as a separate release remain pending.

## Deployment Status

The additive first release was deployed to OVHcloud/Coolify on 2026-10-19 in
app image digest `sha256:c3da3e296d13fcb4fe61e82c802492530f826806488be83c1215338747f7025c`.
This revision supersedes it. No database migration or production data operation
has been performed for Prompt Studio.

## Verification Update

Release review: before publication, load template overrides in the tool-cycle
chat scope and remove the obsolete Zeabur restart workflow. The authorized
release targets OVHcloud only; publication must not restart retained services.

Release blockers found and being corrected: split the five mixed templates into
player-editable style templates and admin-only core templates; add owner-scoped
override loading for feed comments and storyboard jobs. All processes load admin
overrides before starting work and refresh the shared immutable snapshot every
10 seconds, so schedule/memory/judge templates use the same admin settings.
Player reset inherits the current administrator default. Catalogue defaults
must read physical template bytes rather than any active request override.

All release blockers above have been corrected. The final integrated release
suite passed 228 tests; an additional 204 consumer/golden tests passed (sets
overlap). The frontend production/PWA build passed. User authorized commit,
push, image publication and the four-role Coolify app-only rollout on 2026-10-19.

On 2026-10-19, the focused backend suite passed 90 tests, including template
scope, reset, placeholder and prompt-pack hash coverage, plus feed, proactive
and chat prompt regressions. Python compilation and `git diff --check` pass.
The frontend production build passes when its temporary directory is set inside
the workspace. No migration is required because overrides use existing
`app_preferences` records.
