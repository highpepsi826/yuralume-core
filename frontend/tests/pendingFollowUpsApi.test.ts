import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import {
  createScheduledPromise,
  deleteScheduledPromise,
  listAdminPendingFollowUps,
  updateScheduledPromise,
} from '@/utils/api/pendingFollowUps'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedAxios = vi.mocked(axios, true)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('admin pending-follow-up API', () => {
  it('loads the character-scoped admin list', async () => {
    mockedAxios.get.mockResolvedValueOnce({ data: [] })

    await expect(listAdminPendingFollowUps('char-1')).resolves.toEqual([])
    expect(mockedAxios.get).toHaveBeenCalledWith(
      '/api/v1/admin/pending-follow-ups/characters/char-1',
    )
  })

  it('creates, updates, and deletes a scheduled promise', async () => {
    const row = { id: 'row-1' }
    mockedAxios.post.mockResolvedValueOnce({ data: row })
    mockedAxios.patch.mockResolvedValueOnce({ data: row })
    mockedAxios.delete.mockResolvedValueOnce({})

    await expect(createScheduledPromise({
      character_id: 'char-1',
      scheduled_for: '2026-09-04T09:00:00.000Z',
      promise_intent: '提醒帶卡',
    })).resolves.toEqual(row)
    await expect(updateScheduledPromise('row-1', {
      scheduled_for: '2026-09-04T10:00:00.000Z',
      promise_intent: '改成十點提醒',
    })).resolves.toEqual(row)
    await expect(deleteScheduledPromise('row-1')).resolves.toBeUndefined()

    expect(mockedAxios.post).toHaveBeenCalledWith(
      '/api/v1/admin/pending-follow-ups',
      {
        character_id: 'char-1',
        scheduled_for: '2026-09-04T09:00:00.000Z',
        promise_intent: '提醒帶卡',
      },
    )
    expect(mockedAxios.patch).toHaveBeenCalledWith(
      '/api/v1/admin/pending-follow-ups/row-1',
      {
        scheduled_for: '2026-09-04T10:00:00.000Z',
        promise_intent: '改成十點提醒',
      },
    )
    expect(mockedAxios.delete).toHaveBeenCalledWith(
      '/api/v1/admin/pending-follow-ups/row-1',
    )
  })
})
