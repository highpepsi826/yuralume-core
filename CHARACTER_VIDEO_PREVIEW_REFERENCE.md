# Character video previews and provider request controls

## Problem and scope
The custom OpenAI-compatible video adapter always sends a Sora-oriented size
and seconds value. A user's MiniMax H3 gateway rejects size. Add explicit
provider-level size and duration controls, including omission to let the model
choose its defaults, without guessing the gateway's accepted dimensions.
Expose a character-specific trial in Character > Memory album using the same
self-host LumeGram provider selection, visual style, appearance/state prompt,
portrait aspect and each adapter's default frame count. Fix the unstyled provider
prompt field.

## Boundaries and immutable data
Do not modify existing characters, chats, album entries, feed posts or schedules.
Trials are temporary previews with download, not automatic album/feed writes.
No paid API calls, credentials inspection, commit/push, production deployment,
or migration. Cloud asynchronous debug triggers publish posts and must not be
reused for previews. Self-host runtime is the supported preview scope.

## Affected components and compatibility
- Provider catalog, config/profile parsing and registry, request adapter and
  field localization: video_size and video_duration_seconds. Existing missing
  values retain historical behavior; explicit provider_default omits the relevant
  request field. No automatic retry that could create a second billed job.
- Feed composer service: a public preview path shares actual synchronous render
  preparation and parameters with LumeGram, returns bytes rather than storage.
- Ownership-protected, cloud-disabled album preview API and localized album
  prompt/confirmation/playback/download UI. Existing image album stays intact.
- Show preset/current-state scene prompt and explain that automatic LumeGram
  scene selection is a separate composer decision; do not claim a forced scene
  is an automatically chosen feed post. The shared runtime video prompt builder
  still applies character visual identity and state.

## Verification and deployment
Mock provider size/duration payload tests and configuration roundtrip; verify
preview provider overrides, character/state/style arguments, no publishing or
storage, ownership/cloud checks, errors, frontend API blob decoding and build.
Inspect affected UI styles and diff. Real gateway generation/playback and proxy
timeouts remain unverified until an authorized live test after deployment.

## Checklist
- [x] Inspect existing provider payload and album architecture.
- [x] Add provider request controls with compatibility tests.
- [x] Share runtime rendering preparation with character preview.
- [x] Add album API/UI and prompt-field styling.
- [x] Focused verification, explanation of existing settings, progress log.
- [ ] Deployment (not authorized in this task).

## Existing runtime behavior established from source
- LumeGram's composer chooses image/video/none, not a fixed video probability.
  Disabled video, missing prompt, quota gates or failed generation can produce
  images instead. A registered self-host video profile enables the LLM option.
- Missing controls on openai_videos retain 8 seconds and portrait 720x1280 in
  feed; the provider smoke test uses landscape 1280x720. generations_polling
  retains 5 seconds / 720p / 9:16 in feed. Other adapters have different defaults.
- Scene prompts are composed from persona/context, then visual style and adapter
  identity/state text are applied. Self-host native adapters are text-to-video;
  they do not currently use album photos or a first-frame/storyboard pass.
- Album previews resolve FEATURE_VIDEO_FEED with the real character, preserving
  character > feature > active > first-profile fallback. The scene is an editable
  current-intent preset, not a claim to reproduce the next autonomous LumeGram
  choice. No fixed length_frames argument is passed, preserving custom ComfyUI
  profile defaults. Unknown adapter settings are displayed as unavailable, not
  incorrectly described as actual provider defaults.

## Verification outcome
- 114 tests passed for provider settings/native adapters/profile loader/provider
  previews/character previews. Separately, the character preview and existing
  feed/internal-trigger suites passed 88 tests (overlap is intentional).
- New request-control compatibility suite passed; save-time normalization also
  rejects invalid controls before a configuration write.
- 25 frontend API/field tests, Vue TypeScript, locale checks and production/PWA
  build passed. No real paid generation, browser playback or deployment test.
- Diff inspected; no existing album/feed/character data was changed. Test temp
  cleanup was rejected by the approval service due to its unavailable reviewer
  model (HTTP404); ignored test temporary files were retained.
