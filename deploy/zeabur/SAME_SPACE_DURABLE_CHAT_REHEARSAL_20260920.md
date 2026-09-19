# Same-Space Durable Chat Rehearsal Evidence

- Date: 2026-09-20 (Asia/Hong_Kong)
- Scope: Zeabur backup/restore proof, read-only Prod schema verification, and isolated process-role rehearsal.
- Production mutation: none. No Prod migration, role cutover, feature flag change, service creation, or frontend rollout was performed.
- Source image used for rehearsal: `yuralume-rehearsal/durable-chat:20260920-preflight`
- Rehearsal image digest: `sha256:fe6ddf19d39d9831c54133ac495f16b30b6897de85475d7abdac7bb9c69a2454e`

## Backup Proof

Zeabur backup job `6aaeac60f5be144f77d6724f` completed with `SUCCESS`.

- Created: `2026-09-19T15:38:08.891Z`
- Finished: `2026-09-19T15:38:55.083Z`
- Reported size: `140818940` bytes
- Local archive: `C:\Entertainment\yuralume\backups\same-space-durable-20260919-153855-prod.dump`
- Archive SHA-256: `31d9f8b264903d59b36352d62e70c83bb2cb6ff4babdafdfe597febd38c1836c`

The native Zeabur download is a ZIP archive, despite the presigned object name ending in `.sql.gz`. It contains `data/_manifest.json` and `data/data.sql`; the manifest reports PostgreSQL major version 18. Direct `pg_restore --list` against the native archive correctly rejects it as a non-custom archive.

The archive was restored into a new PostgreSQL 18/pgvector container. A custom-format dump was then created from that restored database and restored into a second disposable database:

- Derived custom dump: `C:\Entertainment\yuralume\backups\same-space-durable-20260919-153855-restored.custom`
- Size: `141250333` bytes
- SHA-256: `86028f6e60bc83ab2cfae682db9ea87d57233a8e48b411686da86f20a638373`
- `pg_restore --list`: passed; archive header is `FORMAT: CUSTOM`
- Second custom-format restore: passed

This proves both the Zeabur native archive restore path and the custom-format verification path. The deployment runbook now treats the native archive plus derived custom dump as one backup evidence chain.

## Prod Read-Only Gate

The live `app` service executed a read-only asyncpg query through Zeabur's one-off command path. Result:

- Alembic revision: `s7h3k9m10057`
- pgvector: `vector 0.8.6`
- `chat_turn_commands`: absent
- `chat_turn_effects`: absent

The database-service `executeDatabaseCommand` path was not used as evidence because Zeabur returned a port-forward placeholder resolution error. No SQL mutation occurred. The successful app-service query is the authoritative live check for this rehearsal.

## Migration Rehearsal

The restored clone started at `s7h3k9m10057`. A disposable database was upgraded once through:

```text
s7h3k9m10057 -> t8d6f1a10058 -> u9e7b2a11059
```

The resulting clone verified:

- Both durable tables exist and are empty.
- Owner/client idempotency unique constraint exists.
- Active-conversation partial unique index exists.
- Effect `(turn_id, effect_kind)` and stable idempotency-key constraints exist.
- Effect state/turn indexes exist.
- `vector 0.8.6` remains installed.

## Process-Role Rehearsal

All roles used the same image on an internal-only Docker network connected to the disposable clone. No host port or public domain was exposed.

- `api`: health `200`, DB site-settings overlay, public API available only inside the rehearsal network.
- `coordinator`: health `200`, public API route `404`.
- `worker`: health `200`, public API route `404`.
- `connector`: health `200`, public API route `404`.
- Observed idle memory: approximately 165–194 MiB per role; connector CPU was higher because its external DNS access was intentionally blocked.
- Pause/drain barrier succeeded: `embedded -> paused(epoch 1) -> distributed(epoch 2)` with two zero-claim observations.
- Exactly one `background-coordinator` lease owner was observed in distributed mode.
- Background execution was returned to `paused` before foreground-only tests.

The connector logged expected DNS failures in the internal-only network. This validates isolation and headless startup, not real Telegram/Discord/WhatsApp connectivity; connector canary remains a Prod-window prerequisite.

## Durable Acceptance/Worker Tests

Backend acceptance was enabled only on the disposable `api`; frontend `VITE_DURABLE_CHAT_ENABLED` remained off.

- First synthetic submit returned `202 queued`.
- Repeating the same `client_message_id` returned `202`, the same `turn_id`, and `duplicate=true`.
- `active-turn` returned the same queued turn.
- The unique foreground worker completed the command once: attempt `1`, lease generation `1`.
- Canonical history contained exactly one user row at position `0` and one assistant row at position `1`.
- Message idempotency keys were `{turn_id}:user` and `{turn_id}:assistant`.
- Post-turn ledger contained exactly one `post_turn` row in `completed` state with attempt `1`.
- Stopping and restarting the worker after an intentionally invalid synthetic command fenced it as `recovery_required` at attempt `1`; it did not create an effect row or replay the command.
- A second queued command survived an API restart, remained queryable as `queued`, and completed after the worker restarted.

## Remaining Gates

- The rehearsal image was built from the dirty worktree with a rehearsal-only build identity. A committed SHA must be built and rerun through the release gate before Prod.
- No real model/provider, billing, or external connector call was used in the destructive-failure tests.
- No Prod migration or role cutover is approved by this evidence alone. Fresh backup and the same read-only revision gate are required immediately before any such operation.
- Frontend flag and any cohort/allowlist mechanism remain off. The current backend/frontend flags are global toggles, not percentage rollout controls.
