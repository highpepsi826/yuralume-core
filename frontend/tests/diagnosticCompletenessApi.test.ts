import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { downloadDiagnosticExport, getDiagnosticStatus } from '@/utils/api/observability'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
const mockedAxios = vi.mocked(axios, true)
beforeEach(() => vi.clearAllMocks())

describe('diagnostic completeness metadata', () => {
  it('keeps the server filename and exposes partial coverage with missing sources', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: new Blob(['archive']),
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''diagnostic%20bundle.zip",
        'x-diagnostic-collection': 'complete',
        'x-diagnostic-coverage': 'partial',
        'x-diagnostic-manifest-version': '1',
        'x-diagnostic-missing-sources': encodeURIComponent(JSON.stringify(['previous_process_logs', 'config_history'])),
      },
    })
    const result = await downloadDiagnosticExport({ characterId: 'character-1' })
    expect(result.filename).toBe('diagnostic bundle.zip')
    expect(result.diagnostics).toEqual({
      collection: 'complete', coverage: 'partial', manifestVersion: '1',
      missingSources: ['previous_process_logs', 'config_history'],
    })
    expect(mockedAxios.get.mock.calls[0]?.[1]?.params).toMatchObject({
      include_prompt: undefined, include_messages: undefined,
    })
  })

  it('does not fail the download for malformed optional metadata', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: new Blob(),
      headers: { 'x-diagnostic-collection': 'partial', 'x-diagnostic-missing-sources': '%bad-json' },
    })
    const result = await downloadDiagnosticExport({ characterId: 'character-1' })
    expect(result.diagnostics).toEqual({ collection: 'partial', coverage: 'unknown', manifestVersion: null, missingSources: [] })
  })

  it('fetches read-only status without a character or export scope', async () => {
    const status = { status: 'unavailable', logical_bytes: null, host_disk: { status: 'unknown' } }
    mockedAxios.get.mockResolvedValueOnce({ data: status })
    await expect(getDiagnosticStatus()).resolves.toEqual(status)
    expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/admin/observability/diagnostic-status')
  })
})
