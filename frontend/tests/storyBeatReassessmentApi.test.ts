import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authedFetch } from '@/utils/authedFetch'
import {
  confirmStoryArcBeatReassessment,
  reassessStoryArcBeat,
} from '@/utils/api/storyArc'

vi.mock('@/utils/authedFetch', () => ({
  authedFetch: vi.fn(),
}))

const mockedAuthedFetch = vi.mocked(authedFetch)

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('story beat reassessment API', () => {
  it('previews without a request body and confirms with the reviewed narrative', async () => {
    mockedAuthedFetch
      .mockResolvedValueOnce(jsonResponse(200, {
        status: 'completed',
        reason: 'interaction_evidence_confirmed',
        narrative: '2026-08-30 我們在入口見面。',
        can_confirm: true,
      }))
      .mockResolvedValueOnce(jsonResponse(200, {
        id: 'event-1',
        arc_beat_id: 'beat-1',
      }))

    await expect(reassessStoryArcBeat('beat-1')).resolves.toMatchObject({
      status: 'completed',
      can_confirm: true,
    })
    await expect(confirmStoryArcBeatReassessment(
      'beat-1',
      '2026-08-30 我們在入口見面。',
    )).resolves.toEqual({ id: 'event-1', arc_beat_id: 'beat-1' })

    expect(mockedAuthedFetch).toHaveBeenNthCalledWith(
      1,
      '/api/v1/story-arc-beats/beat-1/reassess',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mockedAuthedFetch).toHaveBeenNthCalledWith(
      2,
      '/api/v1/story-arc-beats/beat-1/reassess/confirm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ narrative: '2026-08-30 我們在入口見面。' }),
      }),
    )
  })
})
