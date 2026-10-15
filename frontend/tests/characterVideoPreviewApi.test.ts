import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { generateCharacterVideoPreview, getCharacterVideoPreviewSettings } from '@/utils/api/album'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(), post: vi.fn(),
    isAxiosError: (error: unknown) => !!error && typeof error === 'object' && 'isAxiosError' in error,
  },
}))

const mockedAxios = vi.mocked(axios, true)
beforeEach(() => vi.clearAllMocks())

describe('character video previews', () => {
  it('loads the selected character runtime settings without submitting a job', async () => {
    const settings = { profile_id: 'character-override', settings: { seconds: '6', size: 'provider_default' }, prompt: 'Current scene' }
    mockedAxios.get.mockResolvedValueOnce({ data: settings })
    await expect(getCharacterVideoPreviewSettings('char/1')).resolves.toBe(settings)
    expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/characters/char%2F1/album/video-preview')
    expect(mockedAxios.post).not.toHaveBeenCalled()
  })

  it('downloads an isolated preview with cancellation and a video timeout', async () => {
    const signal = new AbortController().signal
    const blob = new Blob(['clip'], { type: 'video/mp4' })
    mockedAxios.post.mockResolvedValueOnce({ data: blob })
    await expect(generateCharacterVideoPreview('char/1', 'Walking', signal)).resolves.toBe(blob)
    expect(mockedAxios.post).toHaveBeenCalledWith(
      '/api/v1/characters/char%2F1/album/video-preview', { prompt: 'Walking' },
      { responseType: 'blob', timeout: 1_830_000, signal },
    )
  })

  it('renders a JSON API error returned as a blob', async () => {
    mockedAxios.post.mockRejectedValueOnce({
      isAxiosError: true, response: { data: new Blob(['{"detail":"Video unavailable"}']) },
    })
    await expect(generateCharacterVideoPreview('char', 'Walking', new AbortController().signal))
      .rejects.toThrow('Video unavailable')
  })
})
