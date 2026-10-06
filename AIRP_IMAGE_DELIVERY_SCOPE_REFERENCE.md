# AIRP Image Delivery Scope Repair

Date: 2026-10-07 (Asia/Hong_Kong)

## Problem And Agreed Scope

Yuralume is an AIRP experience. The broad outcome-claim judge and always-on
honesty instructions can reinterpret character life and shared scenes as
claims of real browsing or computer use. The user approved removing broad
search/outcome auditing while retaining real image delivery checks. Search
tools remain available; ordinary discussion of videos, news, browsing, games,
and scene devices must not require tool proof or trigger a repair.

This reference supersedes the broader evidence requirements in
`AIRP_HONESTY_BOUNDARY_REFERENCE.md` for this change. That document records the
earlier repair and remains historical. October screenshots do not establish
whether a particular reversal was a next-turn response or a delayed audit.

## Behavior

- The shared outcome-claim judge checks only a completed claim of delivering
  a real image attachment to the player through the product.
- Fictional photographs, in-game images, scene actions, ordinary character
  life, and future promises are allowed without an attachment. Explicitly
  fictional image exchanges must not be reported as unsupported delivery.
- Image delivery requires a usable image attachment in the outgoing message;
  successful tool status or a non-image attachment alone is insufficient.
- Supply bounded recent dialogue as data so an implicit caption can be
  interpreted in context. Persona remains excluded from the judge.
  New dialogue context uses the existing frontier-safe summaries for marked
  historical NSFW messages, or omits them when no safe summary exists; it does
  not widen content routing to auxiliary models.
- Chat retains its existing background audit/repair lifecycle, but only image
  delivery may produce a new repair. Existing before-send image execution and
  failure fallbacks remain. This change does not promise to block every bad
  caption before its first display or redesign chat streaming.
- Proactive and scheduled/busy composers retain their existing before-send
  gates, retry budgets and attachment fallbacks; their judge becomes image-only.
- Replace the every-turn general honesty/browser-incapability text with a short
  image delivery rule and affirmative AIRP examples. Apply the same scope to
  shared role/tool guidance and busy/scheduled composer prompts.
- Search calls, web fetching and actual tool outputs still work. Remove broad
  completed-search prohibitions and automatic capability disclaimers. Preserve
  tool JSON syntax/execution instructions, character knowledge/memory guidance,
  and normal use of real search output when requested.
- Corrections and newly created repair intents concern missing images only;
  they must not demand that fictional acts be performed on external systems.

## Components And Ownership Boundaries

- `contracts/outcome_claim.py`: additive bounded-context and image-count facts.
- `infrastructure/prompt/outcome_claim_honesty.py`: image-only judge,
  correction and repair wording; existing verdict/intent formats retained.
- `application/services/chat_outcome_claim_auditor.py` and `chat_service.py`:
  forward contextual image evidence without changing durable follow-up logic.
- `composer_tool_loop.py` and `proactive_dispatcher.py`: count deliverable
  image attachments for their shared judge.
- `infrastructure/prompt/sections/honesty.py`, `tools_block.py`, shared role
  boundary, busy follow-up and scheduled-promise prompts: generation scope.
- `data/prompts/novelty_gate/gate.txt`: distinguish actual media prompt defects
  from allowed fictional images and ordinary discussion, retaining media quality
  checks so another gate does not override the same AIRP boundary.
- Focused tests and intentional prompt golden updates.

## Non-goals And Immutable Data

- The implementation step included no push, migration, runtime configuration
  change or real provider calls. On 2026-10-07 the user subsequently authorized
  committing and pushing this reviewed diff to `origin/local/customizations`.
  No manual production operation or live-data change is included.
- Do not alter character records, conversations, schedules, uploads, backups,
  existing queued follow-ups or other live data. Do not touch untracked `temp/`.
- Do not remove web tools, persona knowledge limits, tool-result injection,
  image quota controls, undo/coalescing, retry fencing or ordinary promises.
- Do not redesign the existing keyword-based automatic image intent/trigger
  behavior in this slice. The semantic audit must distinguish fictional image
  exchanges, but auto-generation heuristics remain an explicit limitation.
- Do not clean or cancel old broad repair rows. They can still be released
  after deployment; removal would require a separately authorized data change.

## Compatibility, Risks And Deployment

No database/schema migration. Keep public names, feature routing,
`chat_outcome_claim`, verdict JSON, repair row identity and metrics for
compatibility, with the narrower behavior documented. New evidence fields have
defaults so legacy callers and tests can continue to construct evidence.
Historical records retain their original broad semantics. The image count is
an outgoing-payload fact, not proof that an external platform/device received
the message. A branch push is expected to trigger the app's existing Zeabur
Git integration; deployment completion must be verified separately.

The new policy intentionally removes independent judging of search/web and
product-data completion claims. Search functionality remains, but this judge
will not catch fabricated web outcomes. Stubbed tests verify routing and
contracts, not the quality of every live-model semantic decision.

## Acceptance Cases

1. Ordinary video/news/browsing narration and shared-game invitations require
   no evidence and have no search-specific repair instructions.
2. A real image delivery claim with zero image attachments is checked and
   repairs/retries according to the existing surface policy.
3. Image tool failure and successful tool output with no usable image cannot
   justify a completed image-delivery claim.
4. A non-image attachment cannot satisfy an image-delivery claim; a delivered
   image permits its caption. Image counts use final surface attachments.
5. Recent dialogue reaches the image judge as untrusted data, without persona,
   allowing an implicit caption to be assessed in its actual context.
6. Explicitly fictional images and future image promises are allowed by the
   semantic policy; normal image execution/failure regressions still pass.
7. Web tool invocation/output and tool JSON contracts remain intact.
8. Existing chat repair/undo/coalescing and proactive/promise gate behavior
   remains compatible. Golden changes are limited to intended prompt sections.

## Ordered Implementation Checklist

- [x] Inspect the current source, history, actual tools and baseline tests.
      Baseline focused image/outcome/prompt suites: 137 passed.
- [x] Write this approved scope before implementation.
- [x] Narrow the judge/corrections/repair prompts and extend evidence defaults;
      run focused judge tests and update the round checkpoint.
- [x] Remove broad generation/browser restrictions and preserve image rules;
      run focused prompt tests and update the round checkpoint.
- [x] Wire bounded dialogue and actual image counts through chat and background
      surfaces; add focused flow regressions and update the round checkpoint.
- [x] Align the media-quality rubric with fictional photo narration and verify
      the independent-review context routing fix.
- [x] Regenerate/review intentional prompt goldens; run relevant compatibility
      tests and `git diff --check`.
- [x] Inspect the final diff, record verification and limitations here and in
      `.codex-round.md` / `UPDATE_PROGRESS_LOG.md` before the authorized push.

## Verification Checkpoints

- Image judge scope, image-count override, bounded untrusted context and
  image-only correction/repair tests: 63 passed.
- Generation prompts, tool guidance, busy/scheduled composers and proactive
  decider focused tests: 178 passed.
- Dialogue only interprets the current caption; an old delivery claim alone
  cannot create a new missing-image claim. Mixed messages still have their
  image delivery checked while non-image parts remain out of scope.
- Existing chat repair/coalescing and background audit compatibility: 86
  passed. Updated flow suites with real call-site context/count checks: 58
  passed. These include non-image artifacts, empty image URLs, filtered
  historical NSFW dialogue, both chat write points and background composers.
- Independent review identified raw historical NSFW context forwarding in the
  community composer path. Explicit frontier-safe context substitution fixes
  this without changing composer/quality defaults; focused tests: 57 passed.
- The existing quality rubric's missing-media-prompt clause also needs an AIRP
  exception for fictional photo exchanges. This is a scoped rubric clarification,
  not a change to quality-gate machinery or real media prompt validation.
- Final state: the rubric exception is implemented and both scheduled-promise
  and busy-follow-up image contexts use safe summaries or omit marked NSFW
  source text. Existing community composer inputs remain unchanged.
- Final integrated run: 703 passed across image/judge, chat, proactive,
  scheduled/busy promise, undo/coalescing/shutdown, output-quality, loader and
  golden suites. No live LLM/provider calls were made. Existing dependency
  deprecation warnings remain; no test failures. `git diff --check` passed.
- All 20 chat goldens were regenerated and reviewed: changes are the shared
  AIRP/image-delivery text, removed general/browser restrictions, and tool-rail
  scope. UTF-8/LF and branch-marker checks pass.
- Independent review's new-context routing and fictional-media quality findings
  are resolved. All four runtime evidence constructors supply explicit image
  counts. Existing repair rows and the keyword-based auto-image trigger remain
  unchanged. The user has now authorized commit/push; no successful deployment
  is asserted by this source checkpoint.
- Authorized Git checkpoint is blocked before staging: two automatic approval
  attempts returned local CC Switch proxy HTTP 404 for unsupported
  `gpt-5.6-luna`. No `git add`, commit or push executed. Resolve that route
  before retrying the same authorized operation; do not bypass approval.
