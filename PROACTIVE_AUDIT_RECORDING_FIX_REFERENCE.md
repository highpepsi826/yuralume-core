# Proactive Audit Recording Fix Reference

## Problem

After the local image-delivery guard was merged, the proactive dispatcher
called `is_image_commitment` and `IMAGE_TOOL_NAME` without importing them. The
exception occurs after the LLM and quality checks but before outbound delivery
and `ProactiveAttempt` logging, so the scheduler keeps ticking while the
evaluation history stops advancing. The same merge also dropped the existing
post-tool fallback that prevents an attachment-less image promise from being
sent when the renderer fails.

## Approved Scope

- Restore the missing imports in `proactive_dispatcher.py`.
- Restore the post-tool truthful fallback for image commitments with no
  deliverable image attachment.
- Verify the existing positive proactive tool-use regression path and related
  scheduler tests.
- Build and redeploy the local app image, recreating only `migrate` if needed
  and `app`; retain all database, storage, and channel volumes.
- Preserve the 30-minute proactive cooldown and all message/schedule/memory
  data.

## Non-goals

- No database migration or row repair.
- No changes to image-claim semantics, provider routing, or scheduler policy.
- No manual evaluation request that could send an unsolicited user message.

## Verification Checklist

1. Source import and Python compilation pass.
2. Positive proactive tool-use tests pass, including image-commitment paths
   and renderer failure fallback.
3. Related proactive dispatcher/scheduler regression tests pass.
4. Runtime app is healthy and the next normal tick no longer logs the
   `is_image_commitment` `NameError`; evaluation rows can resume normally.

## Status

Source fix implemented, deployed, and verified on `local/customizations`.

## Deployment Record

- Commit: `5dc8672`
- Backup: `pre-proactive-audit-hotfix-20260830-140137.dump` (custom format,
  verified before deployment)
- Image: `yuralume-local/app:custom`, running container/image digest matched
- Migration: existing `migrate` service exited successfully; database stayed
  at `u2c6m8p10046 (head)`
- Runtime: only `app` was recreated; all support services and volumes retained;
  `/health` returned `status: ok`
- Natural tick: the first post-deploy scheduler tick completed successfully
  and wrote a new `gate_blocked` proactive audit row at 14:09:47 HK; no
  `is_image_commitment` exception appeared in its logs.
- Tests: 15 image-tool tests and 321 proactive/scheduler/tick tests passed;
  compilation and diff checks passed.
