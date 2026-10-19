import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
const axios = vi.mocked((await import('axios')).default, true)
const { listPromptPlaygroundCharacters, runPromptPlayground } = await import('@/utils/api/promptPlayground')

beforeEach(() => vi.clearAllMocks())

it('loads only the read-only playground character listing', async () => {
  axios.get.mockResolvedValueOnce({ data: { characters: [{ id: 'c', name: 'Test' }] } })
  expect(await listPromptPlaygroundCharacters()).toEqual([{ id: 'c', name: 'Test' }])
  expect(axios.get).toHaveBeenCalledWith('/api/v1/prompt-playground/characters')
})

it('sends scope and message without client draft content or user identity', async () => {
  axios.post.mockResolvedValueOnce({ data: { published_reply: 'effective', draft_reply: 'draft' } })
  const payload = { message: 'test', include_current_progress: true, draft_scope: 'admin' as const }
  const result = await runPromptPlayground('character/id', payload)
  expect(axios.post).toHaveBeenCalledWith('/api/v1/characters/character%2Fid/prompt-playground/runs', payload)
  expect(result.draft_reply).toBe('draft')
})

it('preserves an unavailable draft as null', async () => {
  axios.post.mockResolvedValueOnce({ data: { published_reply: 'effective', draft_reply: null } })
  const result = await runPromptPlayground('c', { message: 'test', include_current_progress: false, draft_scope: 'player' })
  expect(result.draft_reply).toBeNull()
})
