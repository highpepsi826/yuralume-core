import type { SendChatMessageRequest } from '@/types/chat'

export type DurableChatOutboxState =
  | 'saved_local'
  | 'submitting'
  | 'acceptance_unknown'
  | 'accepted'
  | 'needs_input'
  | 'completed'
  | 'failed'
  | 'recovery_required'

export interface DurableChatOutboxRecord {
  key: string
  ownerKey: string
  clientMessageId: string
  payload: SendChatMessageRequest
  state: DurableChatOutboxState
  turnId?: string
  conversationId?: string | null
  failureMessage?: string
  createdAt: number
  updatedAt: number
}

export interface ChatDurableOutboxStore {
  put(record: DurableChatOutboxRecord): Promise<void>
  get(ownerKey: string, clientMessageId: string): Promise<DurableChatOutboxRecord | null>
  list(ownerKey: string, states?: DurableChatOutboxState[]): Promise<DurableChatOutboxRecord[]>
  delete(ownerKey: string, clientMessageId: string): Promise<void>
}

const DATABASE_NAME = 'yuralume-chat-outbox'
const DATABASE_VERSION = 1
const STORE_NAME = 'turns'

function recordKey(ownerKey: string, clientMessageId: string): string {
  return `${ownerKey}:${clientMessageId}`
}

function idbAvailable(): boolean {
  return typeof globalThis.indexedDB !== 'undefined'
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'))
  })
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (database.objectStoreNames.contains(STORE_NAME)) return
      const store = database.createObjectStore(STORE_NAME, { keyPath: 'key' })
      store.createIndex('ownerKey', 'ownerKey', { unique: false })
      store.createIndex('updatedAt', 'updatedAt', { unique: false })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
  })
}

class IndexedDbChatDurableOutboxStore implements ChatDurableOutboxStore {
  private databasePromise: Promise<IDBDatabase> | null = null

  private database(): Promise<IDBDatabase> {
    this.databasePromise ??= openDatabase()
    return this.databasePromise
  }

  async put(record: DurableChatOutboxRecord): Promise<void> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put(record)
    await transactionDone(transaction)
  }

  async get(ownerKey: string, clientMessageId: string): Promise<DurableChatOutboxRecord | null> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const value = await requestResult(
      transaction.objectStore(STORE_NAME).get(recordKey(ownerKey, clientMessageId)),
    )
    return (value as DurableChatOutboxRecord | undefined) ?? null
  }

  async list(ownerKey: string, states?: DurableChatOutboxState[]): Promise<DurableChatOutboxRecord[]> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const values = await requestResult(
      transaction.objectStore(STORE_NAME).index('ownerKey').getAll(ownerKey),
    ) as DurableChatOutboxRecord[]
    return values
      .filter((record) => states === undefined || states.includes(record.state))
      .sort((left, right) => left.updatedAt - right.updatedAt)
  }

  async delete(ownerKey: string, clientMessageId: string): Promise<void> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).delete(recordKey(ownerKey, clientMessageId))
    await transactionDone(transaction)
  }
}

class MemoryChatDurableOutboxStore implements ChatDurableOutboxStore {
  private readonly records = new Map<string, DurableChatOutboxRecord>()

  async put(record: DurableChatOutboxRecord): Promise<void> {
    this.records.set(record.key, { ...record, payload: { ...record.payload } })
  }

  async get(ownerKey: string, clientMessageId: string): Promise<DurableChatOutboxRecord | null> {
    const record = this.records.get(recordKey(ownerKey, clientMessageId))
    return record ? { ...record, payload: { ...record.payload } } : null
  }

  async list(ownerKey: string, states?: DurableChatOutboxState[]): Promise<DurableChatOutboxRecord[]> {
    return [...this.records.values()]
      .filter((record) => record.ownerKey === ownerKey)
      .filter((record) => states === undefined || states.includes(record.state))
      .sort((left, right) => left.updatedAt - right.updatedAt)
      .map((record) => ({ ...record, payload: { ...record.payload } }))
  }

  async delete(ownerKey: string, clientMessageId: string): Promise<void> {
    this.records.delete(recordKey(ownerKey, clientMessageId))
  }
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error ?? new Error('IndexedDB transaction failed'))
    transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction aborted'))
  })
}

/** Real browser store; it falls back to memory for SSR/private browsing. */
export function createChatDurableOutboxStore(): ChatDurableOutboxStore {
  return idbAvailable()
    ? new IndexedDbChatDurableOutboxStore()
    : new MemoryChatDurableOutboxStore()
}

/** Exported for deterministic unit tests and non-browser app shells. */
export function createMemoryChatDurableOutboxStore(): ChatDurableOutboxStore {
  return new MemoryChatDurableOutboxStore()
}

export function newDurableChatClientMessageId(): string {
  const cryptoObject = globalThis.crypto
  if (cryptoObject?.randomUUID) return cryptoObject.randomUUID()
  const bytes = new Uint8Array(16)
  if (cryptoObject?.getRandomValues) {
    cryptoObject.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function createDurableChatOutboxRecord(
  ownerKey: string,
  payload: SendChatMessageRequest,
  now = Date.now(),
): DurableChatOutboxRecord {
  if (!ownerKey.trim()) throw new Error('ownerKey is required for chat outbox isolation')
  const clientMessageId = payload.client_message_id ?? newDurableChatClientMessageId()
  return {
    key: recordKey(ownerKey, clientMessageId),
    ownerKey,
    clientMessageId,
    payload: { ...payload, client_message_id: clientMessageId },
    state: 'saved_local',
    createdAt: now,
    updatedAt: now,
  }
}

export async function saveDurableChatOutboxRecord(
  store: ChatDurableOutboxStore,
  record: DurableChatOutboxRecord,
  patch: Partial<DurableChatOutboxRecord> = {},
  now = Date.now(),
): Promise<DurableChatOutboxRecord> {
  const updated = { ...record, ...patch, updatedAt: now }
  await store.put(updated)
  return updated
}
