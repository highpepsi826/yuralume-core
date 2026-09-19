import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.hoisted(() => {
  vi.stubGlobal('localStorage', {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
  })
})
import { DurableChatClient } from '../src/utils/durableChatClient'
import { createMemoryChatDurableOutboxStore } from '../src/utils/chatDurableOutbox'
import { getChatTurnStatus, submitDurableChatTurn } from '../src/utils/api/chat'

vi.mock('../src/utils/api/chat', async () => {
  return {
    getChatTurnStatus: vi.fn(),
    getActiveChatTurn: vi.fn(),
    submitDurableChatTurn: vi.fn(),
  }
})

describe('DurableChatClient', () => {
  beforeEach(() => vi.clearAllMocks())

  it('submits once with the saved client id and records the server receipt', async () => {
    vi.mocked(submitDurableChatTurn).mockResolvedValue({
      turn_id: 'turn-1',
      conversation_id: 'conversation-1',
      status: 'queued',
    })
    const client = new DurableChatClient({
      ownerKey: 'user-1',
      store: createMemoryChatDurableOutboxStore(),
      now: () => 100,
    })
    const record = await client.save({ character_id: 'character-1', message: 'hello' })
    const result = await client.submit(record)

    expect(submitDurableChatTurn).toHaveBeenCalledWith({
      character_id: 'character-1',
      message: 'hello',
      client_message_id: record.clientMessageId,
    })
    expect(result.record.state).toBe('accepted')
    expect(result.record.turnId).toBe('turn-1')
  })

  it('refreshes a known turn after the request response was lost', async () => {
    vi.mocked(getChatTurnStatus).mockResolvedValue({
      turn_id: 'turn-1',
      conversation_id: 'conversation-1',
      status: 'processing',
      phase: 'waiting_model',
    })
    const store = createMemoryChatDurableOutboxStore()
    const client = new DurableChatClient({ ownerKey: 'user-1', store })
    const record = await client.save({
      character_id: 'character-1',
      message: 'hello',
      client_message_id: 'client-1',
    })
    const result = await client.refresh({ ...record, turnId: 'turn-1', state: 'acceptance_unknown' })

    expect(getChatTurnStatus).toHaveBeenCalledWith('turn-1')
    expect(result.status.status).toBe('processing')
    expect(result.record.state).toBe('accepted')
  })

  it('keeps a transport failure acceptance-unknown for same-id recovery', async () => {
    vi.mocked(submitDurableChatTurn).mockRejectedValue(
      Object.assign(new Error('gateway unavailable'), { statusCode: 503 }),
    )
    const store = createMemoryChatDurableOutboxStore()
    const client = new DurableChatClient({ ownerKey: 'user-1', store })
    const record = await client.save({ character_id: 'character-1', message: 'hello' })

    await expect(client.submit(record)).rejects.toThrow('gateway unavailable')
    expect((await store.get('user-1', record.clientMessageId))?.state)
      .toBe('acceptance_unknown')
  })

  it('marks an explicit client refusal as needing input instead of retrying forever', async () => {
    vi.mocked(submitDurableChatTurn).mockRejectedValue(
      Object.assign(new Error('conversation busy'), { statusCode: 409 }),
    )
    const store = createMemoryChatDurableOutboxStore()
    const client = new DurableChatClient({ ownerKey: 'user-1', store })
    const record = await client.save({ character_id: 'character-1', message: 'hello' })

    await expect(client.submit(record)).rejects.toThrow('conversation busy')
    expect((await store.get('user-1', record.clientMessageId))?.state)
      .toBe('needs_input')
    expect(await client.pending()).toHaveLength(0)
  })

  it('continues through a temporary status read failure and cleans up on completion', async () => {
    vi.mocked(submitDurableChatTurn).mockResolvedValue({
      turn_id: 'turn-1', conversation_id: 'conversation-1', status: 'queued',
    })
    vi.mocked(getChatTurnStatus)
      .mockRejectedValueOnce(new Error('temporary network loss'))
      .mockResolvedValueOnce({
        turn_id: 'turn-1', conversation_id: 'conversation-1', status: 'processing',
      })
      .mockResolvedValueOnce({
        turn_id: 'turn-1', conversation_id: 'conversation-1', status: 'completed',
      })
    const store = createMemoryChatDurableOutboxStore()
    const client = new DurableChatClient({ ownerKey: 'user-1', store })
    const record = await client.save({ character_id: 'character-1', message: 'hello' })

    const result = await client.waitForCompletion(record, { intervalMs: 250 })

    expect(result.status.status).toBe('completed')
    expect(result.record.state).toBe('completed')
    expect((await client.pending())).toHaveLength(0)
  })
})
