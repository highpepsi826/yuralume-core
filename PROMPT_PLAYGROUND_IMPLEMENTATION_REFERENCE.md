# Prompt Playground Implementation Reference

## Problem

Prompt Studio currently writes edits directly to effective overrides. This makes
testing an edit alter the version that players receive after the effective
override refresh. The product now needs private Draft lifecycle support for both
players and administrators, followed by a read-only Playground that compares
the current effective prompt with the owner's Draft using one frozen gameplay
snapshot.

## Authorized Scope

Implement the following in ordered slices:

1. Prompt Studio Draft lifecycle for players and administrators.
2. Read-only chat Playground with effective/Draft comparison.
3. Prompt Studio links and Playground UI.

Players may draft and publish only their five allowed style templates. Their
publish action writes only their own effective override. Administrators may
draft and publish all registered templates; administrator publish writes the
global effective override. Drafts are private per user/template and never
become effective until published.

## Non-goals

- No media, LumeGram, proactive, tool, image, video, TTS or external connector
  Playground in this release.
- No Playground persistence of test inputs, outputs, prompt text or chat rows.
- No memory, state, schedule, story, goal, persona, durable-command, notification
  or post-turn writes from Playground.
- No database schema migration: use existing `app_preferences` with user-scoped
  keys.
- No commit, push or production deployment without the applicable later user
  authorization.

## Data Model

- Current effective player overrides: existing user-scoped
  `player_prompt_template_overrides`.
- Current effective admin overrides: existing global
  `admin_prompt_template_overrides`.
- Player Drafts: user-scoped `player_prompt_template_drafts` map.
- Admin Drafts: user-scoped `admin_prompt_template_drafts` map.

Empty Draft content removes the owner's Draft. A Draft is validated with the
same registered-template, length, control-character, placeholder and template
syntax rules as an effective override. An effective override reset remains
separate from Draft deletion.

## Effective and Draft Semantics

For a player, the effective content is: player's effective style override,
then global admin effective override, then shipped template. For an admin
editing an admin template, effective means global admin override, then shipped
template. A Draft starts as a copy of the owner's current effective content.

Publishing a player Draft updates only the user's effective override. Publishing
an admin Draft updates only the global admin effective override, updates the
in-process admin snapshot, and removes that owner's published Draft. A player
reset returns to the current admin effective version but does not delete Draft.

## API Plan

Extend the existing player and admin template endpoints with private Draft
operations. Responses include effective content, `draft_content`, `has_draft`,
and `editing_scope` metadata. Endpoints will be named under the current template
route group, for example `GET|PUT|DELETE .../{name}/draft` and
`POST .../{name}/publish-draft`.

All routes use the current authenticated user. Admin routes retain `require_admin`.
No API accepts an arbitrary user id.

## Playground Plan

Add a dedicated `PromptPlaygroundService`; it must not call `ChatService` send,
stream, post-turn or persistence entry points. It builds one read-only snapshot,
renders a single no-tool chat prompt for the effective version and, where a
Draft exists, one for the Draft version. It calls the chat model directly and
returns text plus limited metadata only.

The snapshot reuses existing read-only loaders where feasible. It must not call
repository write methods, schedulers, connectors, tool orchestrators or media
services. The surface is `prompt_playground` for bounded observability; prompt
or response bodies are not persisted by this feature.

## Affected Components

- `PromptCustomizationService`, prompt-template routes and focused tests.
- Frontend Prompt Studio player/admin controls and API client.
- New Playground service, DTO/routes/frontend page and read-only tests.
- Container wiring, router, navigation and localization as necessary.

## Test Plan

1. Player/admin Draft isolation and access restrictions.
2. Loading, saving, discarding and publishing Draft behavior.
3. Player publish affects only that player; admin publish updates global default.
4. Reset effective override does not delete a Draft.
5. Playground owns character access and freezes one snapshot for both runs.
6. Playground makes no writes and invokes no post-turn, tool or connector path.
7. Draft run differs only by owner Draft overrides; no-Draft run calls model once.
8. Frontend build/typecheck and focused API/component behavior tests pass.

## Progress

1. Draft service/API and Prompt Studio controls deployed at `758c281`.
2. Completed locally: dedicated Playground service, authenticated API and
   read-only character listing. Character access bypasses `CharacterService`
   because its read-time refresh can write rest-recovery state.
3. Completed locally: player/admin Prompt Studio links, explicit Load Draft
   buttons, Playground page, two-result display, clear/loading/error states.
4. Verification: 101 backend tests passed (Playground service/routes, Drafts,
   prompt loader and container wiring); 3 frontend API tests passed; Vue
   typecheck and production/PWA build passed. A real in-memory container/fake
   model test fenced character/conversation/memory/preference writes.
5. User authorized commit, push and Coolify deployment on 2026-10-19. Release in progress; no paid model call for this slice.
   Browser visual acceptance is not yet performed.

## Implemented Snapshot and Comparison Contract

- Player access uses repository ownership; administrators can select every
  character. Role checks come from authenticated identity, never request data.
- `draft_scope=player|admin` selects the caller's private Draft collection;
  only administrators may request admin scope. Admin Studio links set admin
  scope; the player Studio link uses player scope even for an admin account.
- Selected character owner supplies operator identity, persona, declared note,
  relationship seed and address preference. No cross-owner fallback is used
  for a missing operator profile.
- Optional progress reads 12 recent cross-source messages with shared mirror
  deduplication, an 80-item memory pool ranked to 8 using the chat fallback
  ranker, active goals, existing current/future schedules, active story arc,
  recent story events, open scene and eligible stored world events. World
  events are read from the repository; no RSS ingestion occurs.
- Both prompts are fully rendered before the first model call using a copied
  snapshot, fixed timestamp, full template defaults/effective overrides and
  the same resolved chat model. An admin refresh or intervening game write
  cannot change the second run's source. Drafts never become global overrides.
- The `FEATURE_CHAT` route deliberately skips automatic auxiliary usage rows;
  Playground does not call the main-chat usage recorder. Body-free diagnostic
  correlation uses `source_surface=prompt_playground`.
- Request data allows only text (2,000 characters), progress toggle and Draft
  scope. It rejects client prompt bodies, arbitrary user IDs and attachments.
  No Draft means one model call and `draft_reply=null`.

## First-Release Limits

- Context is representative rather than a replay of the full formal-chat
  workflow. No new dialogue summary, semantic embedding, schedule, material
  digest or auxiliary LLM context is generated. Memory selection uses the
  formal chat's salience/recency fallback, not its embedding-based branch.
- Disabling progress omits historical conversations, memories, goals,
  schedules and story/world progress. Character card/current stored state,
  declared player identity and initial relationship remain available.
- One run per user at a time, 6 attempts/minute and 30/hour are in-process
  limits for the current single-API deployment. They are not distributed
  quotas and are not yet editable in admin runtime settings; multiple API
  replicas require a shared limiter before relying on these as fleet quotas.
- Each generation times out after 120 seconds; outputs are bounded to 1,200
  characters plus an ellipsis. Provider failures return a generic error.
- The model port has no fixed-seed argument. The UI states that two calls can
  vary randomly and both can consume provider credit. Non-chat templates are
  explicitly labelled as outside this chat-only Playground's evaluated paths.
