# Diagnostic completeness implementation (2026-10-15)

## Authorization and scope

The user authorized implementation of the draft at
`temp/DIAGNOSTIC_COMPLETENESS_PROPOSAL_20261015.md`, including durable application
diagnostics and housekeeping without Zeabur paid logs or Pro alerts.
Source-only work on `local/customizations`; no commit/push, production migration,
deployment, message replay, provider setting changes or historical-data repair.
Preserve unrelated files, diagnostic ZIPs, chats, characters, media and backups.

## Design

- Retain existing ZIP names/fields; add versioned manifest, honest collection and
  diagnostic coverage, generation/feed/durable/fleet sources and safe routing snapshot.
- Mark absent historical instrumentation as unknown; snapshots are not history.
- Fix generation_failed health omission and report every exported text truncation.
- Use an additive PostgreSQL diagnostic event store for bounded structured events
  and sanitized application logs, asynchronous bounded batches, short shutdown
  flush, fail-soft ring-buffer fallback, explicit persistence gaps.
- Capture lifecycle, route selection, config sync, provider attempts and feed
  outcomes with safe identifiers and structural metadata, never full bodies.
- Default important INFO retention 14 days, WARN/ERROR and config/lifecycle 30
  days; DEBUG remains off. New diagnostics alone get 512 MiB soft / 1 GiB logical
  hard quotas plus row/batch caps. Quota accounting is not physical disk usage.
- Cleanup is idempotent and bounded, serialized across writers/cleaners as needed;
  admission prevents unlimited growth. Cleanup status and drops are observable.
- Host disk capacity unknown unless actually measured from a confirmed source;
  no Zeabur alerts, external Telegram notifications or paid probes.
- Redact before persistence using allow-listed event fields and safe exception
  summaries; protect URL query strings, headers, credentials and payload content.
- Missing new tables return partial diagnostics; no automatic migrations.

## Components and migration

Observability export/helpers; generation/feed/durable/fleet read sources; diagnostic
buffer/store/publisher; additive Alembic table; app lifespan and instrumentation;
frontend download status/capacity information and locales. Existing usage/durable
tables are read-only in this repair. Migrations must be rehearsed locally; live
execution requires separate authorization and verified backup.

## Ordered checklist

1. [x] Inspect baseline and create this reference before code edits.
2. [x] Honest export health/coverage/truncation and bounded additional sources.
3. [x] Durable diagnostic sink, additive migration, retention/quota/cleanup tests.
4. [x] Safe runtime instrumentation, lifecycle integration and export of persisted events.
5. [x] Frontend completeness/housekeeping UI and localization.
6. [x] Focused regression/compatibility/frontend checks; SQLite migration and sample ZIP review.
7. [x] Review diff, record results and remaining PostgreSQL/deployment gates.

## Acceptance

Generation-failed receipts degrade historical health; missing logs/build/config
history never imply completeness. A provider switch and feed image downgrade can
be traced from safe route/attempt/outcome events. Events survive a restarted
collector, cleanup cannot touch business data, overload cannot block chat or
grow storage without bound, persistence/cleanup gaps appear in export/UI.
Cross-window work and correlations remain explicit; secret and opt-in body tests
cover new sources. Multi-role and all-role deployments report actual topology.

## Execution state

Baseline `cfe3425`; only untracked `temp/` exists before implementation.
Source implementation and local checks complete. No production state changed.

## Implementation decisions and operating limits

- Chosen storage is additive PostgreSQL `diagnostic_events` + serialized
  `diagnostic_quota`, rather than duplicating chunks in object storage. SQLite
  is supported for isolated tests. Migration head `x3l8n0p10061` adds only these
  tables/indexes; existing business tables and data remain unchanged.
- Buffer: 2,000 queued records, batches of 100, flush poll 0.5 seconds, cleanup
  check at most once/minute when idle, cleanup batches of 500, 250,000 row cap.
  Low-priority records are reclaimed before lifecycle/config/errors; hard quota
  bounds logical event bytes, not PostgreSQL/WAL/index/backup disk allocation.
- Application WARN/ERROR logs retain structural source/exception metadata,
  not formatted message bodies/arguments, provider bodies, chat or local variables.
  Structured phase/route/provider/feed events supply actionable semantic evidence.
  DEBUG stays disabled (there is no temporary-debug UI in this implementation).
- Important phases: HTTP stream lifetime, chat request/prelude/lease/generation,
  inbound messaging, feed tick/materialise/image/storage, config sync and
  lifecycle. LLM provider/model and image-profile resolution record provenance
  independently, preserving model/provider inheritance behavior.
- OpenAI-compatible completion attempts capture HTTP/structural response facts;
  streaming captures attempt headers, first chunk, completion/failure/cancellation.
  Anthropic captures completion/stream phases. Adapter-specific detailed raw
  diagnostics for other third-party providers remain outside this instrumentation.
- Current routing snapshot includes global/owner/character overrides, registered
  IDs, bounded enabled provider projections and configured NSFW target. It never
  invokes the NSFW active-status API because that API can write expiration events;
  active state is therefore explicitly unknown in this read-only export.
- No reliable host filesystem source exists in this scope: host_disk is unknown.
  Logical quota/cleanup/error state appears in admin UI; no external alerts are
  sent. There is no auto-expansion or paid dependency.
- Existing build metadata injection remains supported. If a deployed build lacks
  it, coverage explicitly lists missing build identity; no SHA is fabricated.
- Old data has no retroactive phase/config history. The manifest therefore keeps
  historical diagnostic coverage partial, separately from source query success.
- Existing usage/commands/feed records provide durable correlation where those
  fields exist; generated request IDs join new events. New-conversation IDs are
  bound after prelude; messaging account/message/binding IDs and durable turn IDs
  are recorded when available. No business payloads are copied for correlation.
- Existing multi-service reference is superseded for export scope by this
  implementation, reusing its already-present heartbeat table/publisher. No
  duplicate heartbeats or forced four-role topology is introduced.

## Verification evidence so far

- SQLite migration upgrade/downgrade/upgrade rehearsal and single-head check pass.
- Frontend API tests, i18n/typecheck and PWA production build pass (local Node
  version advisory; successful build used a workspace-scoped temporary directory).
- Application role/lifecycle compatibility: 53 passed. Runtime correlation,
  cancellation, stream/HTTP observation and safe response shape: 11 passed.
- Synthetic ZIP generated through the real route at
  `temp/diagnostic-synthetic-review-20261015.zip`; entries/manifest checked,
  unavailable sources correctly marked partial. It contains synthetic test data.
- PostgreSQL rehearsal blocked: Docker daemon named pipe unavailable on this host.
  No production migration attempted; this is a release gate, not a passed check.
- Admin browser visual smoke test has not run; frontend compile/build is verified.

Final integration: 495 backend tests passed. Final feed/context/buffer set 68
passed; final lifecycle/shutdown/collector/context regression set 32 passed.
Final export projections/ref sanitization regression set: 20 passed. Structural
auxiliary route/latency/error-presence evidence is retained without generated prose.
These sets overlap and must not be summed as unique test counts. Independent
review fixes cover priority admission, read timeouts, metadata truncation,
no-database shutdown, and failure-event flush before DB disposal.
An end-to-end synthetic SQLite-backed ZIP at
`temp/diagnostic-e2e-synthetic-20261015.zip` contains two persisted correlated
events and one generation failure; missing unrelated tables are honestly partial.

No push/deployment is authorized by this implementation turn. A production release
requires a verified PostgreSQL backup, isolated PostgreSQL migration rehearsal,
reviewed source and the explicit production-operation approval in the runbook.

## PostgreSQL rehearsal authorization (2026-10-15)

The user started Docker and authorized the isolated local rehearsal. Use only a
new uniquely named loopback PostgreSQL container, synthetic data and disposable
container storage. Exercise the full migration graph to the previous head,
upgrade/downgrade/re-upgrade, concurrent quota admission and diagnostic-only
cleanup. Remove only the owned labelled rehearsal container afterwards; no
Compose stacks, existing volumes, hosted services or live credentials are used.
Current attempt: sandbox Docker access denied; elevated read-only Docker status
request failed automatic approval review because the CC Switch approval model
gpt-5.6-luna returned HTTP 404. No elevated command ran. Prepare a repeatable
local runner while the approval-service issue is resolved; do not bypass it.

Rehearsal completed by the user on 2026-10-15. Report independently read from
`temp/diagnostic-postgres-rehearsal-5bebe969c36b.json`: status `passed`, cleanup
`owned_disposable_container_removed`. Full migration graph to baseline, upgrade,
downgrade/re-upgrade, previous-schema/sentinel preservation, restart/redaction,
retention/hard quota/business isolation, concurrent collectors, priority cleanup
and 16 concurrent writers all passed on disposable local PostgreSQL. This
supersedes the earlier PostgreSQL rehearsal blocker; Docker approval access for
agent-run commands is not claimed resolved. Production backup/migration and
commit/push/deployment remain unperformed and separately authorized.
