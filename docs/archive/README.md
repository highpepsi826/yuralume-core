# Archive

Completed, superseded, and one-off documents moved out of the repository root
on 2026-10-25 so the root stays a working set rather than an accumulation.

**This directory is read-only history.** Do not append new work here, and do
not treat anything below as current scope. Read the live files instead:

- current task → `.codex-round.md`
- current design / implementation references → repository root `*_REFERENCE.md`
- behaviour reference → `FEATURE_MANUAL.md`
- recent progress → `UPDATE_PROGRESS_LOG.md`

Each entry says why it was archived, so you can tell at a glance whether it is
still worth opening.

## Superseded by a newer reference

| File | Why it is here | Read instead |
|---|---|---|
| `DIAGNOSTIC_EXPORT_IMPLEMENTATION_REFERENCE.md` | Its own header says the completeness work replaced the older no-new-log-table restriction. | `DIAGNOSTIC_COMPLETENESS_IMPLEMENTATION_REFERENCE.md` |
| `MULTI_SERVICE_DIAGNOSTIC_BUNDLE_IMPLEMENTATION_REFERENCE.md` | Absorbed into the completeness work; its D1-not-started checkpoint was explicitly not the current state. | `DIAGNOSTIC_COMPLETENESS_IMPLEMENTATION_REFERENCE.md` |
| `DIAGNOSTIC_TRACE_BUILD_REFERENCE.md` | Finished build-identity and background-trace work, now part of the same diagnostic surface. | `DIAGNOSTIC_COMPLETENESS_IMPLEMENTATION_REFERENCE.md` |
| `AIRP_HONESTY_BOUNDARY_REFERENCE.md` | Its own header points at the image-only policy that replaced its broader search and outcome requirements. | `AIRP_IMAGE_DELIVERY_SCOPE_REFERENCE.md` |
| `TEMP_SAME_SPACE_RELIABILITY_PLAN.md` | Written as a temporary plan; its own header says to use the durable-chat reference for new scope. | `SAME_SPACE_DURABLE_CHAT_IMPLEMENTATION_REFERENCE.md` |
| `PROMPT_PLAYGROUND_PROPOSAL_ZH_TW.md` | Chinese proposal draft; the implementation reference is the authoritative version. | `PROMPT_PLAYGROUND_IMPLEMENTATION_REFERENCE.md` |

## Obsolete runtime

| File | Why it is here |
|---|---|
| `ZEABUR_DEPLOYMENT_IMPLEMENTATION_REFERENCE.md` | Zeabur was retired on 2026-10-18 in favour of OVHcloud/Coolify. See `AGENTS.md` for the current production runtime. |
| `ZEABUR_LOCAL_IMAGE_WORKFLOW.md` | Same retirement. The moving-`local`-tag workflow no longer drives deployment. |
| `PENDING_ZEABUR_STABILITY_AND_ADMIN_MENU.md` | The memory and backup-streaming work it tracked shipped; the Zeabur host it refers to is stopped. |

## Completed one-off work

| File | Why it is here |
|---|---|
| `LEGACY_COMMITMENT_DATA_REPAIR_DRAFT.md` | The approved 2026-08-29 production data repair ran to completion and was verified. Kept for the transaction record. |

## Split-out logs

| File | Contents |
|---|---|
| `PROGRESS_LOG_ARCHIVE_PRE_2026-09.md` | `UPDATE_PROGRESS_LOG.md` entries dated before 2026-09-01, in source order. |
