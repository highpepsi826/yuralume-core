import axios from 'axios'

/** Long-running preview requests share binary success and JSON error handling. */
export async function postVideoPreview(url: string, body: unknown, signal: AbortSignal): Promise<Blob> {
  try {
    const { data } = await axios.post<Blob>(url, body, {
      responseType: 'blob', timeout: 1_830_000, signal,
    })
    return data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      const text = await error.response.data.text()
      let detail: unknown
      try {
        detail = JSON.parse(text).detail
      } catch {
        // Gateways can return HTML errors instead of API JSON.
      }
      if (typeof detail === 'string') throw new Error(detail)
    }
    throw error
  }
}
