@AGENTS.md

## Claude-specific

- All rules in `AGENTS.md` apply to Claude Code unchanged.
- Claude and Codex share `.codex-round.md` (execution checkpoint, updated after
  each verified small step) and `UPDATE_PROGRESS_LOG.md` (progress log, updated
  after verified completion). Mark new entries in both with `(by Claude)` or
  `(by Codex)`.
- Do not edit the same files concurrently with Codex; resume from the latest
  checkpoint's `Next action`.
- `.codex-round.md` is the live checkpoint and stays short (target under 250
  lines). Finished sections go to `.codex-round-archive.md`; do not re-read the
  archive during inventory, only grep it to trace a specific old decision.
- `UPDATE_PROGRESS_LOG.md` starts at 2026-09-01. Earlier entries live in
  `docs/archive/PROGRESS_LOG_ARCHIVE_PRE_2026-09.md`; append new entries only to
  the live file.
- Completed or superseded `*_REFERENCE.md` files move to `docs/archive/` with
  `git mv` instead of being deleted. Fix relative links the move breaks and
  leave a one-line "superseded by" pointer at the top of the old file.
- `FEATURE_MANUAL.md` describes current user-visible behavior. Update it in the
  same change as any feature addition, change, or removal.

## Owner environment — PowerShell, not bash

The owner runs **Windows 11** and pastes commands into **PowerShell**
(`PS C:\Entertainment\yuralume-src>`). Bash syntax silently breaks there, and
the failure is confusing rather than obvious, so never hand over bash-shaped
commands.

- **No `\` line continuations.** PowerShell does not read `\` at end of line as
  a continuation. A multi-line `git add a.md b.md \` becomes
  `fatal: \: '\' is outside repository` followed by
  `CommandNotFoundException` for every file on the following lines. Put the
  whole command on one line, or continue with a backtick — and a backtick must
  be the very last character on the line with nothing after it. One long line
  is safer than a backtick the owner has to copy exactly.
- **Prefer `;`-free, `&&`-free forms.** `&&` works in PowerShell 7 but not in
  Windows PowerShell 5.1. Do not chain commands; give one command per line.
- **No `$( )` command substitution, no `export VAR=value`** (use
  `$env:VAR = "value"`), no `sed`/`awk`/`grep` pipelines, no `rm -rf`, no
  `/dev/null`. Use `Test-Path`, `Get-ChildItem`, `Select-String`,
  `Remove-Item`, `$null` instead.
- **Quote paths with spaces** and use forward slashes or `-LiteralPath`.
- Bash commands that Claude itself runs through the Bash tool are separate —
  these rules are about what the *owner* is told to type.
- When a command is genuinely awkward as a one-liner, offer a `.ps1` script the
  owner can run, or run it yourself with the Bash tool and report the result.

## Model usage

- Default to Sonnet (medium effort) for scoped work: i18n/UI tweaks, bug fixes
  with clear reproduction, test/lint fixes, and implementing an approved design.
- Use Opus (medium–high effort) for: writing design/implementation references,
  cross-service issues (coordinator/worker/connector timing, Telegram polling
  ownership), migration/data/production-deploy work, bugs with unknown cause,
  or after two failed fix attempts.
- After the user explicitly approves a design file, delegate implementation to
  the `implementer` subagent (Sonnet), passing the design file path. If the
  subagent is unavailable, stop and ask the user to run `/model sonnet`
  instead of continuing on the current model.
- Keep review and deployment in the main session: review the subagent's result
  by reading the actual diff and running the targeted test suites for the
  touched modules. Do not run `/code-review`; the owner does not want it. The
  main session's own diff read plus targeted tests is the review.
- Do not raise effort to high by default; reserve it for reasoning-heavy
  investigation.
