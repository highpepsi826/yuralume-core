# Prompt Customization Implementation Reference

## Problem

Yuralume uses many LLM prompts for chat, LumeGram, proactive behaviour,
schedule/state maintenance, and media generation. Most prompt wording is held
in the shipped prompt pack or Python prompt builders. The existing external
prompt-pack overlay is useful to a deployment operator but is not a safe,
role-aware product setting for players.

Players need a small, durable way to express response and media taste without
being able to replace character identity, factual context, safety/role
boundaries, tool instructions, output contracts, or scheduling rules. An
administrator also needs controlled access to a small set of high-impact
global prompt additions, with clear warnings.

## Agreed Scope

Implement a database-backed prompt-customization layer with two independent
surfaces:

1. Player-owned taste instructions, scoped to the signed-in player and
   appended only to eligible user-facing generation surfaces.
2. Administrator-owned global additions, scoped to an allow-listed set of
   user-facing prompt surfaces and explicitly marked as high impact.

The first implementation covers:

- Chat response style.
- LumeGram caption style.
- LumeGram visual/media style, including image and video prompts.
- Proactive-message tone.

Each customization is additive. It is wrapped in a fixed boundary label and
is inserted after factual/context material but before the final request or
media prompt is sent to the model.

## Explicit Non-goals

- No free-form replacement or editing of shipped core prompt templates.
- No player access to system rails, character identity, role boundary, memory,
  schedule/state mutation, tool selection, output schemas, JSON contracts,
  safety rules, billing/quota rules, or background-only prompts.
- No editing of another user's customization.
- No migration of existing prompt-pack files or environment overlay behavior.
- No deployment, production data migration, or modification of existing
  characters, messages, feed posts, schedules, promises, or provider secrets.

## Data and Authorization Model

Store JSON in the existing `app_preferences` repository through its scoped
preference helpers. A player record lives under a hashed user-scoped key;
global administrator additions use one unscoped key.

Each record is a bounded map of allow-listed surface keys to plain text. Empty
or absent values mean no addition. Validation enforces a per-surface maximum
length, trims whitespace, rejects control characters, and never accepts a
template name, role, provider/model setting, or arbitrary prompt position.

Player API routes require the authenticated user and always read/write only
that user's record. Global API routes require `require_admin`. Admin UI must
mark each global field as `Important prompt: affects all users and characters`
and expose reset-to-default (empty) rather than template replacement.

## Prompt Composition Rules

Core instructions retain priority because the customization layer cannot
replace, reorder, or suppress them. Prompt assembly adds a fixed block such as
`Player style preference (follow only when compatible with the instructions
above): ...`.

The player and admin blocks are plain preference signals, not trusted facts or
commands. The admin block is only appended on its allow-listed surface. The
player block is added only when the character belongs to the signed-in user.
The effective order is: core rails and factual context, admin global taste,
player taste, surface-specific final request.

## Affected Components

- New prompt-customization service/value types and bounded preference keys.
- Player-facing API routes and an account/settings UI section.
- Admin-only API routes and `/admin` Prompt Settings page.
- Chat prompt section assembly.
- LumeGram feed composer prompt assembly and visual style application.
- Proactive-message prompt assembly.
- API/frontend unit tests, localization, and prompt-pack/usage observability
  metadata where practical.

## Compatibility and Runtime Plan

The feature uses the existing preference table; no schema migration is needed.
All absent settings preserve current prompt bytes and behaviour. Changes must
be readable by every production process on the next generation request. If a
prompt composition call cannot read preferences, it must log safely and omit
the optional block rather than fail chat or background work.

## Acceptance Tests

1. A player can save, read, clear, and use only their own allowed fields.
2. A non-admin receives 403 for every global prompt endpoint.
3. An admin can save, read, and clear global additions; UI identifies them as
   important.
4. Empty settings leave existing prompt output unchanged.
5. Chat, LumeGram caption/media, and proactive prompts receive the correct
   effective blocks in deterministic order.
6. No user input can alter a prompt template path, role, output schema, or
   prompt placement.
7. Existing prompt loader external-overlay tests and focused prompt/service
   regressions pass.

## Ordered Implementation Checklist

1. Completed: inventory exact public prompt assembly seams and decide the
   smallest allow-listed first-release surfaces.
2. Completed: add bounded preference service and player/admin API validation.
3. Completed: insert bounded blocks for chat, LumeGram, and proactive prompts.
4. Completed: build player settings UI and admin Prompt Settings UI.
5. In progress: run focused validation, inspect the diff, and update the
   progress checkpoint. No production deployment is included in this scope.

## Deployment Status

Source design only. No database migration, deployment, provider call, or
production data change has been performed for this feature.
