# Yuralume Development and Deployment Instructions

Read `LOCAL_CUSTOMIZATION_WORKFLOW.md` before modifying this repository or the
local Yuralume deployment.

## Current Hosted Production

OVHcloud/Coolify is the accepted production runtime as of 2026-10-18. Read
`C:\Users\high_\Documents\ChatGPT\ai_livelife\deployment\ovh-yuralume\PLAN.md`
and `OVHCLOUD_DEPLOYMENT_STATUS.md` before a production operation.

- Public application: `https://yuralume.tototoproject.com`.
- Coolify service: `yuralume` (`lg4wotyohbnhgs5y2mlhwb5z`) with six services:
  `postgresql`, `storage`, `app`, `coordinator`, `worker`, and `connector`.
- The four app roles use an explicitly selected immutable GHCR image digest.
  Database/storage volumes and secrets must be preserved for an app update.
- Zeabur program services are stopped and retained for rollback evidence only.
  Do not restart them or treat the historical Zeabur workflow step as a deploy.

## Hosted Development and Deployment

- After completing a user-requested source change and its proportionate checks,
  automatically create a scoped `local:` commit, push `local/customizations`,
  wait for the immutable image publication, and deploy the four application
  roles in Coolify. Treat this as standing authorization unless the user says
  to stop, the release crosses a migration/data/destructive boundary, checks
  fail, or an unrelated dirty change makes the intended commit ambiguous.
  Preserve unrelated work through explicit staging and report each release
  stage; never auto-deploy support images, volumes, secrets, or data changes.

- Edit source in `C:\Entertainment\yuralume-src` and push reviewed commits on
  `local/customizations`. GitHub Actions `Publish container images` publishes
  the moving `local` tag and an immutable `sha-<commit>` tag to GHCR. It does
  not deploy Coolify. Do not edit a running cloud container or treat a manual
  dashboard build as a substitute for a source commit.
- After image publication succeeds, resolve the new immutable digest. Updating
  Coolify's `app`, `coordinator`, `worker`, and `connector` services to that
  digest and deploying them is a separate production action. A later GitHub
  push never changes services pinned to an earlier digest. Preserve the
  `postgresql` and `storage` images, volumes, secrets, and role environments
  for a no-migration app release.
- Once the user authorizes deployment of a named reviewed commit, continue
  through publication, digest selection, Coolify deployment, and verification
  without repeatedly asking which stage to perform. Stop for a new
  migration/data/destructive approval boundary, a material discrepancy, or a
  failed check.
- At each material stage, report and persist: source commit, GitHub Actions
  run/result, published immutable digest, Coolify configuration/deployment
  state, and health/login/representative-media checks. Update
  `UPDATE_PROGRESS_LOG.md` after verified completion; do not wait for the user
  to ask which deployment stage has been reached.
- Local development on this computer or another notebook must use an isolated
  local Compose stack. Never point a default local runtime at the hosted
  database or storage, and never run local Telegram polling or schedulers at
  the same time as the hosted app. There must be exactly one Telegram polling
  owner.
- For a production bug, obtain a labelled encrypted cloud snapshot/export and
  restore it into an isolated local stack. Disable Telegram and other external
  connectors there. Reproduce, test, and repair locally; never write a local
  development database back into production.
- Before any production migration or data operation, read the OVHcloud runbook,
  check the current service status, obtain explicit user confirmation, and
  create and verify a PostgreSQL custom-format backup. Migrations run once in
  a controlled environment; never run Alembic concurrently from local and
  cloud. Prefer an app-only redeploy when no schema change is involved.
- A storage migration must move `objects/` and `metadata/` together. Use the
  staged encrypted transfer procedure in the OVHcloud runbook and do not
  expose plaintext storage during transfer.
- After a Coolify deployment, verify all six services are healthy, `GET
  https://yuralume.tototoproject.com/health` returns `status=ok`, representative
  media can be read, admin login works, and only the live connector owns
  Telegram polling. Only after those checks should a release be accepted.
- Keep `CONFIG_ENCRYPTION_KEY` stable across deployments so encrypted Admin
  provider configuration remains readable. Store all secrets only in Coolify
  variables or local ignored environment files; never commit, log, paste, or
  print them.
- Production uploads, deletes, rollback changes, public-port changes, and
  actions that may incur OVHcloud charges require explicit confirmation at the
  point of action. Preserve rollback backups until the resulting deployment
  and data have been verified.

## Branches and Upstream

- Work only on `local/customizations` for local changes.
- Treat `main` as an upstream mirror. Do not commit local changes to it.
- `origin` is the personal fork and `upstream` is `Yuralume/yuralume-core`.
- Before an upstream update, fetch both remotes and merge the updated `main`
  into `local/customizations`. Do not discard local commits to make updates
  appear clean.

## Owner Environment — Windows 11 PowerShell

The owner runs **Windows 11** and pastes commands into **PowerShell**
(`PS C:\Entertainment\yuralume-src>`). This applies to every assistant working
in this repository, Claude and Codex alike. Bash syntax silently breaks in
PowerShell, and the failure is confusing rather than obvious, so never hand
over bash-shaped commands.

- **No `\` line continuations.** PowerShell does not read `\` at end of line as
  a continuation. A multi-line `git add a.md b.md \` becomes
  `fatal: \: '\' is outside repository`, followed by
  `CommandNotFoundException` for every file on the following lines. Put the
  whole command on one line, or continue with a backtick — and a backtick must
  be the very last character on the line with nothing after it. One long line
  is safer than a backtick the owner has to copy exactly.
- **Do not chain commands.** `&&` works in PowerShell 7 but not in Windows
  PowerShell 5.1. Give one command per line.
- **No `$( )` command substitution, no `export VAR=value`** (use
  `$env:VAR = "value"`), no `sed`/`awk`/`grep` pipelines, no `rm -rf`, no
  `/dev/null`. Use `Test-Path`, `Get-ChildItem`, `Select-String`,
  `Remove-Item`, `$null` instead.
- **Quote paths with spaces** and use forward slashes or `-LiteralPath`.
- Commands an assistant runs through its own shell tool are separate — these
  rules are about what the *owner* is told to type.
- When a command is genuinely awkward as a one-liner, offer a `.ps1` script the
  owner can run, or run it with the assistant's own shell and report the
  result.

## Deployment Boundaries

- Runtime files live in `C:\Entertainment\yuralume`.
- Source files live in `C:\Entertainment\yuralume-src`.
- Do not edit code inside a running Docker container.
- Do not overwrite `C:\Entertainment\yuralume\.env.container`, uploads,
  backups, or Docker volumes.
- Treat `C:\Entertainment\yuralume\docker-compose.yml` as the
  installer-managed deployment base. It is not interchangeable with either
  source Compose file. Never replace it with `docker-compose.yml` or
  `docker-compose.container.yml` from this repository: their service and
  volume names differ and can make Docker start a separate, empty database.
- Keep the existing storage port mapping `127.0.0.1:19012:9000` unless the
  user explicitly requests a verified change.

## Local Source Builds

- Use both Compose files for any local-source deployment:

  ```powershell
  docker compose --env-file .env.container `
    -f docker-compose.yml -f docker-compose.local.yml ...
  ```

- Build only `app`; `migrate` must reuse the same `yuralume-local/app:custom`
  image.
- Do not run `docker compose pull` for every service while the local override
  is active. Pull only upstream-managed support services explicitly.
- A source merge does not automatically update the installer-managed Compose
  base. Review upstream self-host release notes separately before changing it.
- After a verified source, deployment, or upstream update, append a concise,
  non-sensitive entry to `UPDATE_PROGRESS_LOG.md`. Do not write secrets,
  message content, or database rows into that log.

## Persistent Change References

- When a new plan discussed with the user (a change or a new idea) is about to
  be executed, first create a dedicated design Markdown file for that plan.
  Present it to the user and wait for explicit confirmation before executing;
  then implement according to that design file. Record any later design change
  in the file and confirm it with the user before acting on it.
- Before starting a non-trivial implementation that spans multiple files,
  services, persistence surfaces, migrations, user-visible behavior, or a
  deployment boundary, create or update a scoped Markdown implementation
  reference in this repository.
- The reference is required before any code, migration, data, or deployment
  operation. Re-read it in the current context before editing; chat history,
  a condensed handoff, or an earlier failed patch is not a durable substitute.
- Include the problem, agreed scope, explicit non-goals, immutable-data rules,
  affected components, migration and compatibility plan, test cases,
  deployment status, and an ordered implementation checklist. Record later
  design decisions there before implementing them.
- Keep the reference factual, non-sensitive, and narrowly scoped. Update it
  when a discovery changes the approved design or execution order.
- For the current post-turn meeting and promise synchronization repair, the
  authoritative reference is
  COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md. Read it before
  changing that behavior, and do not replace it with a large
  context-dependent patch.
- For every task, read `.codex-round.md` (and `待修.md` when it applies)
  after checking `git status` and the latest commit. Then read
  `docs/atlas/INDEX.md` before scanning `src/`. Update
  `.codex-round.md` after each verified small step with the exact next action,
  test result, changed files, and any blocker. Do not restart completed
  inventory after context compaction.
- Claude Code also works in this repository; see `CLAUDE.md` for the shared
  Claude/Codex conventions. Mark new entries in `.codex-round.md` and
  `UPDATE_PROGRESS_LOG.md` with `(by Codex)` or `(by Claude)`.

## Document Lifecycle

Four tiers, and a file lives in exactly one of them:

| Tier | Where | Rule |
|---|---|---|
| Live checkpoint | `.codex-round.md` | Only the current task, the last few completed steps, and `Next action`. Keep it under ~250 lines. |
| Architecture atlas | `docs/atlas/` | Stable map of what the code **is now**: layers, invariants, change map, domains, flows. Never archived — updated in place. |
| Active reference | repository root `*_REFERENCE.md` | Design or implementation reference for behavior that is still being changed or still governs running code. |
| Archive | `docs/archive/` | Completed, superseded, or one-off work. Read-only history. |

- When a reference's work is finished and nothing points at it any more, move
  it to `docs/archive/` with `git mv`. Do not delete it — future archaeology
  needs it. Fix any relative links the move breaks.
- Superseded references keep a one-line pointer at the top saying which file
  replaced them, so a reader who lands there is not misled.
- Move finished `.codex-round.md` sections to `.codex-round-archive.md` rather
  than leaving them in the live file. Never re-read the archive as part of
  task inventory; grep it only to trace a specific old decision.
- A reference that is still approved-but-not-implemented, or implemented but
  awaiting a release decision, stays in the root and keeps an accurate
  `Status` line. Stale status headers are a defect: correct them as part of the
  next edit.
- `UPDATE_PROGRESS_LOG.md` holds entries from 2026-09-01 onward. Older entries
  are in `docs/archive/PROGRESS_LOG_ARCHIVE_PRE_2026-09.md`. Keep appending new
  entries to the live file only.

## Architecture Atlas

`docs/atlas/` describes what the code is **now** — layers, invariants, change
map, domains, flows. It is the first thing to read before scanning source, and
it is not a design document.

### First stop — before any investigation

Every new bug and every new idea starts here, not in `src/`. Follow this order
and stop as soon as the question is answered:

| Situation | Read, in this order |
|---|---|
| New bug report | `docs/atlas/INDEX.md` → `PENDING_FIXES.md` (is it already known?) → `docs/atlas/change-map.md` (which layer?) → source |
| New idea or feature request | `docs/atlas/INDEX.md` → `IDEAS_BACKLOG.md` (already recorded?) → `FORK_DELTA.md` (does the fork or upstream already have it?) → `docs/atlas/layers.md` (which layer can own it?) |
| "How does X work?" | `docs/atlas/INDEX.md` → the relevant `domains/` or `flows/` page → `change-map.md` → source |
| Upstream update | `FORK_DELTA.md` → `make fork-delta-check` |
| Anything that must not break | `docs/atlas/invariants.md` |

Do not skip to `src/` because the atlas "might be out of date". If it is out of
date, fixing it is part of the task — that is cheaper than re-deriving the map
every session, and it is the only reason the atlas stays worth reading.

The inverse also holds: when the atlas answers the question, say so and cite
the page instead of re-explaining the structure from scratch.

### Mandatory update

A change is not finished until the registers that describe it are updated in the
same commit:

| If the change… | Then update |
|---|---|
| alters a domain's behavior, layering, or invariants | the affected `docs/atlas/` page, and refresh `verified_at_commit` / `verified_at` |
| introduces, fixes, or invalidates a known defect | `PENDING_FIXES.md` — add, update, or remove the entry and its atlas cross-reference |
| adds, changes, or removes a fork-only behavior | `FORK_DELTA.md` — add an `F-xx` row, or set its status to `MERGE` |
| is a new design or plan | a root `*_REFERENCE.md` (existing rule, unchanged) |
| changes user-visible behavior | `FEATURE_MANUAL.md` (existing rule, unchanged) |

Run both checkers before committing:

```powershell
make atlas-check
make fork-delta-check
```

### Investigation findings

The atlas is updated by investigation, not only by code changes. Whenever an
investigation — a bug hunt, design work for an idea, or a "how does X work"
question — verifies a structural fact against the code that the atlas does not
already record, write it into the atlas as part of that same piece of work,
even when no source file changes.

The test is one question: **would the next session have to re-read source to
learn this?** If yes, it belongs in the atlas.

| Write it | Do not write it |
|---|---|
| A mechanism or call order (what runs before what, what short-circuits) | A proposed or unimplemented design — that is a `*_REFERENCE.md` |
| A gate or threshold and what it actually gates | Speculation that was not checked against code |
| Who writes a given piece of data, and through which method | One-off data state, database rows, message content |
| A rule inside a prompt template that governs behavior | Secrets |
| A non-obvious absence ("this function never receives X") | Anything already recorded — update the existing entry instead |

- **Where:** the existing page that owns the topic — a `flows/` page for
  cross-layer order, a `domains/` page for one domain, `change-map.md` for
  "where do I change this", `invariants.md` for rules, `glossary.md` for terms.
  Add a cross-link from the `change-map.md` row. Open a new page only when no
  existing page fits and the topic is likely to be revisited.
- **When:** before reporting the finding to the owner, and in the same commit
  as the design reference or backlog entry that relies on it.
- **A reference is not the home of a fact.** `*_REFERENCE.md` files are
  archived when their work ends. A reference may summarize what it relies on,
  but the fact itself lives in the atlas and the reference points at it.
- **Anchors:** prefer `file::Symbol` over line numbers; add the new symbols to
  the page's `symbols` frontmatter so `make atlas-check` guards them.
- **Freshness:** when only a section was added and the rest of the page was not
  re-checked, mark the section `（查證於 <short-sha>，<date>）` and leave the
  page-level `verified_at_commit` alone — that field means the whole page was
  verified.
- **Corrections count too:** when an investigation shows an atlas statement is
  wrong or stale, fix it in the same work.
- **Report it:** the final message for an investigation states which atlas
  pages were updated, or says plainly that nothing new was found.
- **Report every atlas change at the end of the turn:** whenever a
  conversation turn adds, updates, or deletes anything under `docs/atlas/`
  — for any reason, not only an investigation — the last message of that
  turn lists each change: the page, the section, whether it was an add, an
  update, or a delete, and one line on what it now says. Do not batch this
  into a later turn or leave it only in a commit message.

- Every atlas page carries YAML frontmatter with `verified_at_commit`,
  `verified_at`, `sources` and `symbols`. `make atlas-check` verifies that
  every source path still exists and every symbol anchor still resolves.
- When a change alters a domain's behavior, layering, or invariants, update the
  affected atlas page in the same commit and refresh `verified_at_commit` /
  `verified_at`. A release that changes structure and leaves the atlas
  describing the old structure is incomplete.
- Cosmetic changes that do not alter any claim in a page do not require an
  atlas edit; they only make that page's freshness age.
- Atlas pages are never moved to `docs/archive/`. They describe code that is
  still running, so they are updated in place.
- Where the atlas and the code disagree, the code wins and the atlas is a
  defect.
- Do not put secrets, message content, or database rows in atlas pages.

## Feature Manual

- `FEATURE_MANUAL.md` is the operator- and player-facing description of what
  Yuralume actually does — features, surfaces, settings, behavior. It is not a
  design reference, not a changelog, and not a deployment runbook.
- When a user-visible feature is added, changed, or removed, update the manual
  in the same change. A release that alters behavior and leaves the manual
  describing the old behavior is incomplete.
- The manual describes the current deployed behavior of this fork, including
  local customizations that upstream does not have. Mark fork-only features so
  it is clear what an upstream reader would not find.
- Keep it in the language the rest of the operator documentation uses. Product
  names, setting labels, and route paths stay as they appear in the UI.

## Ideas Backlog

- `IDEAS_BACKLOG.md` tracks the user's brainstormed feature ideas (IDs
  `I-xx`) and their status. It is a backlog, not an approval: an idea still
  needs its own design file and explicit user approval before implementation.
- When starting, designing, or finishing work for a backlog idea, update its
  status, `Ref` link, and the Change Log there, marked `(by Claude)` or
  `(by Codex)`.

## Safety Checks

- Before an update that may run migrations, create and verify a PostgreSQL
  custom-format dump in `C:\Entertainment\yuralume\backups`.
- Verify `docker compose ps` and `http://127.0.0.1:8012/health` after every
  deployment.
- Keep changes narrowly scoped. Do not modify character records, chat history,
  schedules, deferred intents, or scheduled promises unless the user
  explicitly asks for that data change.
- Do not expose secrets in `.env.container`, provider connections, logs, or
  command output.
## Diagnostic export debugging

- The diagnostic download UI should support time ranges (default: recent 1 hour), incident-type presets, and advanced checkboxes for detailed data. Keep full prompts, chat bodies, and credentials opt-in; show estimated size and sensitivity.
- A debug integration may let Codex sign in to and authorize the Yuralume diagnostic page, then fetch a bounded bundle through a protected, read-only diagnostic export API. Scope authorization to admin, short-lived tokens, and explicit export scopes. Fall back to manual download or shared workspace when the connector/session is unavailable.

## Read-only Production Investigation Access

Both Claude and Codex may inspect the hosted deployment to diagnose production
bugs. This is read-only investigation, not a deployment path.

### What is allowed

- SSH to the OVH host with the existing deploy key at
  `C:\Users\high_\Documents\ChatGPT\ai_livelife\.deploy-ssh\ovh_deploy_ed25519`
  (host `ubuntu@54.39.231.18`, `known_hosts` in the same directory).
- Read-only inspection: `docker ps`, `docker logs`, `docker inspect`,
  `docker compose config`, and read-only SQL against PostgreSQL.
- `GET /api/v1/admin/observability/diagnostic-export` with a short-lived admin
  token (see `src/kokoro_link/api/routes/observability.py`).
- Read-only Coolify API calls using a token stored **only** in
  `C:\Users\high_\Documents\ChatGPT\ai_livelife\.deploy-ssh\coolify-api.env`
  (a local file outside the repository).

### What is not allowed

- No writes to the production database, storage volumes, schedules, deferred
  intents, character records, or chat history.
- No `docker exec` into a running container to edit files.
- No production restart, redeploy, migration, or image change as part of
  investigation.
- Never print, commit, or paste secrets (SSH key material, Coolify token,
  provider credentials, `.env.container` contents) into chat or logs.

### Diagnostics are opt-in

Diagnostic export never includes prompts or message bodies unless
`include_prompt` / `include_messages` are explicitly enabled. Enable them only
for the specific window being investigated, and treat the resulting bundle as
sensitive. Do not write chat content into `UPDATE_PROGRESS_LOG.md` or any
committed reference file; record only file paths, timings, and conclusions.

### Permission configuration is per-machine

- Shared policy lives here in `AGENTS.md` so both assistants follow it.
- The actual tool allow-rules live in `.claude/settings.local.json`, which is
  gitignored (`.gitignore`), and in Codex's own local configuration. Do not
  commit either.
- Credentials live only in `.deploy-ssh/`, outside the repository.

### When Auto Mode Blocks a Step

The user runs Claude Code in **auto mode** by default because
`default` mode's per-command prompts are too disruptive. Some read-only
investigation steps (SSH, `docker exec`, provider API calls) are
nonetheless rejected by auto mode's classifier, and an `allow` rule in
`settings.local.json` does **not** override that rejection.

Handle it in one of two ways, chosen by whether the blocked step is
optional or essential:

1. **Optional step** — finish the whole task with what is reachable,
   then report at the end which steps were skipped and offer to re-run
   them in `default` mode if the user wants them.
2. **Essential step** — stop, persist a checkpoint, and hand the mode
   switch to the user:
   - Write the exact commands still needed, what each one is for, and
     why it cannot be replaced, into `.codex-round.md` under a heading
     marked `(by Claude)` or `(by Codex)`.
   - Tell the user plainly: switch to `default`, approve this list,
     switch back to auto.
   - Do not mark the task done, and do not guess at the missing data.

Do not fall back to an unreviewed workaround, and do not silently widen
the scope of a permitted command to accomplish a blocked one.


Follow the existing rule: fetch a labelled encrypted snapshot, restore it into
an isolated local stack, disable Telegram and other external connectors there,
and reproduce locally. Never write a local development database back to
production.

