import type { SendChatMessageRequest } from '@/types/chat'
import {
  getActiveChatTurn,
  getChatTurnStatus,
  submitDurableChatTurn,
  type ChatTurnStatus,
} from '@/utils/api/chat'
import {
  createChatDurableOutboxStore,
  createDurableChatOutboxRecord,
  saveDurableChatOutboxRecord,
  type ChatDurableOutboxStore,
  type DurableChatOutboxRecord,
} from '@/utils/chatDurableOutbox'

export interface DurableChatClientOptions {
  ownerKey: string
  store?: ChatDurableOutboxStore
  now?: () => number
}

export interface DurableChatSubmission {
  record: DurableChatOutboxRecord
  status: ChatTurnStatus
}

export interface DurableChatWaitOptions {
  intervalMs?: number
  timeoutMs?: number | null
  /** Stop a sync loop when the panel is abandoned or unmounted. */
  signal?: AbortSignal
}

export class DurableChatSyncAbortedError extends Error {
  constructor() {
    super('Durable chat sync was aborted')
    this.name = 'DurableChatSyncAbortedError'
  }
}

/**
 * Short-request client for the durable chat route. It never waits for model
 * output; the returned receipt is enough to resume from another page/device.
 */
export class DurableChatClient {
  private readonly ownerKey: string
  private readonly store: ChatDurableOutboxStore
  private readonly now: () => number

  constructor(options: DurableChatClientOptions) {
    if (!options.ownerKey.trim()) throw new Error('ownerKey is required')
    this.ownerKey = options.ownerKey
    this.store = options.store ?? createChatDurableOutboxStore()
    this.now = options.now ?? (() => Date.now())
  }

  async save(payload: SendChatMessageRequest): Promise<DurableChatOutboxRecord> {
    const record = createDurableChatOutboxRecord(this.ownerKey, payload, this.now())
    await this.store.put(record)
    return record
  }

  async submit(record: DurableChatOutboxRecord): Promise<DurableChatSubmission> {
    const submitting = await saveDurableChatOutboxRecord(
      this.store,
      record,
      { state: 'submitting' },
      this.now(),
    )
    try {
      const status = await submitDurableChatTurn({
        ...submitting.payload,
        client_message_id: submitting.clientMessageId,
      })
      const updated = await saveDurableChatOutboxRecord(
        this.store,
        submitting,
        {
          state: 'accepted',
          turnId: status.turn_id,
          conversationId: status.conversation_id,
          failureMessage: undefined,
        },
        this.now(),
      )
      return { record: updated, status }
    } catch (error) {
      const statusCode = errorStatusCode(error)
      await saveDurableChatOutboxRecord(
        this.store,
        submitting,
        {
          state: isClientActionableStatus(statusCode)
            ? 'needs_input'
            : 'acceptance_unknown',
          failureMessage: error instanceof Error ? error.message : String(error),
        },
        this.now(),
      )
      throw error
    }
  }

  async submitOrRecover(
    record: DurableChatOutboxRecord,
  ): Promise<DurableChatSubmission> {
    if (record.turnId) return this.refresh(record)
    return this.submit(record)
  }

  async refresh(record: DurableChatOutboxRecord): Promise<DurableChatSubmission> {
    if (!record.turnId) return this.submit(record)
    const status = await getChatTurnStatus(record.turnId)
    const updated = await saveDurableChatOutboxRecord(
      this.store,
      record,
      {
        state: 'accepted',
        turnId: status.turn_id,
        conversationId: status.conversation_id,
        failureMessage: status.failure_message ?? undefined,
      },
      this.now(),
    )
    return { record: updated, status }
  }

  async waitForCompletion(
    record: DurableChatOutboxRecord,
    options: DurableChatWaitOptions = {},
  ): Promise<DurableChatSubmission> {
    const intervalMs = Math.max(250, options.intervalMs ?? 1000)
    const timeoutMs = options.timeoutMs ?? null
    const deadline = timeoutMs === null
      ? null
      : this.now() + Math.max(intervalMs, timeoutMs)
    let current = record
    let attempt = 0
    while (deadline === null || this.now() <= deadline) {
      throwIfAborted(options.signal)
      let result: DurableChatSubmission | null = null
      try {
        if (current.turnId) {
          result = await this.refresh(current)
        } else {
          result = await this.submit(current)
        }
      } catch (error) {
        current = await this.store.get(this.ownerKey, current.clientMessageId) ?? current
        if (current.state === 'needs_input') throw error
        // A lost ACK or a temporary status read does not prove rejection.
        // Keep the same client id and try again after a bounded backoff.
        await waitWithJitter(backoffMs(intervalMs, attempt), options.signal)
        attempt += 1
        continue
      }
      attempt = 0
      if (isExpiredWorkerLease(result.status)) {
        const recoveryStatus: ChatTurnStatus = {
          ...result.status,
          status: 'recovery_required',
          phase: 'recovery_required',
          failure_code: 'worker_lease_expired',
          failure_message: 'The worker lease expired; the turn needs reconciliation',
        }
        const recovery = await saveDurableChatOutboxRecord(
          this.store,
          result.record,
          {
            state: 'recovery_required',
            failureMessage: recoveryStatus.failure_message ?? undefined,
          },
          this.now(),
        )
        return { record: recovery, status: recoveryStatus }
      }
      current = result.record
      if (result.status.status === 'completed') {
        const completed = await saveDurableChatOutboxRecord(
          this.store,
          current,
          { state: 'completed', failureMessage: undefined },
          this.now(),
        )
        return { record: completed, status: result.status }
      }
      if (result.status.status === 'failed' || result.status.status === 'cancelled') {
        const failed = await saveDurableChatOutboxRecord(
          this.store,
          current,
          { state: 'failed', failureMessage: result.status.failure_message ?? undefined },
          this.now(),
        )
        return { record: failed, status: result.status }
      }
      if (result.status.status === 'recovery_required' || result.status.post_turn_effect_state === 'recovery_required') {
        const recovery = await saveDurableChatOutboxRecord(
          this.store,
          current,
          { state: 'recovery_required', failureMessage: result.status.failure_message ?? undefined },
          this.now(),
        )
        return { record: recovery, status: result.status }
      }
      await waitWithJitter(intervalMs, options.signal)
    }
    throw new Error('Durable chat turn is still processing')
  }

  async recoverConversation(
    conversationId: string,
  ): Promise<ChatTurnStatus | null> {
    return getActiveChatTurn(conversationId)
  }

  async pending(): Promise<DurableChatOutboxRecord[]> {
    return this.store.list(this.ownerKey, [
      'saved_local',
      'submitting',
      'acceptance_unknown',
      'accepted',
      'recovery_required',
    ])
  }

  async forget(record: DurableChatOutboxRecord): Promise<void> {
    await this.store.delete(this.ownerKey, record.clientMessageId)
  }
}

function errorStatusCode(error: unknown): number | null {
  if (!error || typeof error !== 'object') return null
  const value = (error as { statusCode?: unknown }).statusCode
  return typeof value === 'number' ? value : null
}

function isClientActionableStatus(statusCode: number | null): boolean {
  return statusCode !== null && statusCode >= 400 && statusCode < 500
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DurableChatSyncAbortedError()
}

function backoffMs(base: number, attempt: number): number {
  return Math.min(30_000, base * 2 ** Math.min(attempt, 5))
}

function isExpiredWorkerLease(status: ChatTurnStatus): boolean {
  if (!['claimed', 'processing', 'generated', 'committed'].includes(status.status)) {
    return false
  }
  if (!status.lease_until) return false
  const leaseUntil = Date.parse(status.lease_until)
  return Number.isFinite(leaseUntil) && leaseUntil <= Date.now()
}

async function waitWithJitter(ms: number, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal)
  await new Promise<void>((resolve, reject) => {
    const jitter = Math.floor(Math.random() * Math.max(100, ms * 0.2))
    const timer = globalThis.setTimeout(done, ms + jitter)
    const onAbort = () => {
      globalThis.clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      reject(new DurableChatSyncAbortedError())
    }
    function done() {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

export function createDurableChatClient(ownerKey: string): DurableChatClient {
  return new DurableChatClient({ ownerKey })
}
