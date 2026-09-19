import { describe, expect, it } from 'vitest'
import {
  createDurableChatOutboxRecord,
  createMemoryChatDurableOutboxStore,
  saveDurableChatOutboxRecord,
} from '../src/utils/chatDurableOutbox'

describe('durable chat outbox', () => {
  it('keeps records isolated by owner and preserves a stable client id', async () => {
    const store = createMemoryChatDurableOutboxStore()
    const record = createDurableChatOutboxRecord(
      'user-a',
      { character_id: 'character-1', message: 'hello' },
      100,
    )
    await store.put(record)
    await saveDurableChatOutboxRecord(store, record, { state: 'submitting' }, 200)

    expect(record.clientMessageId).toBeTruthy()
    expect(record.payload.client_message_id).toBe(record.clientMessageId)
    expect((await store.get('user-a', record.clientMessageId))?.state).toBe('submitting')
    expect(await store.get('user-b', record.clientMessageId)).toBeNull()
  })

  it('lists unresolved records oldest first', async () => {
    const store = createMemoryChatDurableOutboxStore()
    const first = createDurableChatOutboxRecord(
      'user-a',
      { character_id: 'character-1', message: 'one' },
      100,
    )
    const second = createDurableChatOutboxRecord(
      'user-a',
      { character_id: 'character-1', message: 'two' },
      200,
    )
    await store.put(second)
    await store.put(first)
    await saveDurableChatOutboxRecord(store, second, { state: 'accepted' }, 300)

    const records = await store.list('user-a', ['saved_local', 'accepted'])
    expect(records.map((item) => item.payload.message)).toEqual(['one', 'two'])
  })
})
