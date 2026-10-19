import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
const axios = vi.mocked((await import('axios')).default, true)
const { listPromptPlaygroundCharacters, runPromptPlayground, previewPromptPlayground } = await import('@/utils/api/promptPlayground')

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

it('previews scoped draft metadata without a generation request', async () => {
  const data = { template_usage: { published: [], draft: [] }, draft_templates: [] }
  axios.get.mockResolvedValueOnce({ data })
  const params = { include_current_progress: true, draft_scope: 'admin' as const }
  expect(await previewPromptPlayground('character/id', params)).toEqual(data)
  expect(axios.get).toHaveBeenCalledWith('/api/v1/characters/character%2Fid/prompt-playground/preview', { params })
  expect(axios.post).not.toHaveBeenCalled()
})

it('publishes only the authenticated scope draft collection', async () => {
  const { publishPlayerPromptTemplateDrafts, publishAdminPromptTemplateDrafts } = await import('@/utils/api/promptCustomizations')
  axios.post.mockResolvedValue({ data: { published_names: ['chat/instructions_footer_style'], templates: [] } })
  await publishPlayerPromptTemplateDrafts()
  expect(axios.post).toHaveBeenLastCalledWith('/api/v1/prompt-templates/publish-drafts')
  await publishAdminPromptTemplateDrafts()
  expect(axios.post).toHaveBeenLastCalledWith('/api/v1/admin/prompt-templates/publish-drafts')
})
