# AIRP Honesty Boundary Repair

## Problem

The outcome-claim honesty judge is misclassifying embodied actions inside the
shared roleplay world as real computer or external-system operations. This
queues delayed apology messages that break character and halt AIRP scenes.

The 2026-09-16 diagnostic shows two concrete false positives:

- logging into and moving inside a fictional online game;
- pressing and listening to an in-world answering machine.

Both were followed by queued honesty repairs despite being ordinary scene
narration. Real attachment delivery, web access, and persisted system changes
must remain evidence-bound.

## Scope

- Clarify the always-on chat honesty boundary.
- Clarify the outcome-claim judge's definition and admissible examples.
- Add prompt regression tests for the two observed AIRP cases and the retained
  real-world evidence boundary.

## Non-goals

- No production deployment or live-data changes.
- No changes to character records, chat history, or queued follow-ups.
- No relaxation for claims about delivered files, fetched web content, sent
  messages, calendar changes, or other externally verifiable side effects.

## Compatibility And Data

This is a prompt-only behavior correction. It adds no schema or migration and
does not rewrite existing messages or pending follow-ups. Existing rows already
queued before deployment may still be delivered under their original intent;
the scheduled-promise composer must apply the same roleplay boundary when it
renders those rows after deployment.

## Acceptance Cases

1. The judge is explicitly told that joining a fictional game, moving a
   fictional avatar, pressing an in-world recorder, and hearing story content
   are admissible roleplay actions without a tool call.
2. The chat composer receives the same boundary so it can continue the scene
   without unnecessary refusals or capability disclaimers.
3. Claims that a real image was attached, a web page was fetched, or persisted
   data was changed still require matching tool evidence.
4. Focused prompt and honesty-judge tests pass.
5. Scheduled promises to continue an AIRP game, inspect an in-world object, or
   listen to an in-world recording continue the scene without requesting a
   real file or asserting that the character lacks physical hardware.

## Implementation Checklist

- [x] Refine the chat honesty section.
- [x] Refine the judge role and admissible-action section.
- [x] Add focused regression assertions.
- [x] Regenerate and review affected prompt golden snapshots.
- [x] Run focused tests and `git diff --check`.
- [x] Record verified source progress; leave deployment pending.
- [x] Clarify the scheduled-promise composer boundary and add a regression
  assertion for in-world recordings.
