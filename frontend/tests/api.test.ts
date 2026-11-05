// All mocked numeric bodies are TEST fixtures; no market data is produced here.
import { describe, expect, it, vi } from 'vitest'
import { ApiError, request } from '../src/api'

describe('HTTP contract', () => {
  it('retries a failed safe GET and returns the actual response', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError('TEST disconnected')).mockResolvedValueOnce(new Response(JSON.stringify({ status: 'TEST_OK' })))
    vi.stubGlobal('fetch', fetch)
    expect(await request('/TEST')).toEqual({ status: 'TEST_OK' }); expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('does not retry a chat or economic POST after an ambiguous failure', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('TEST disconnected')); vi.stubGlobal('fetch', fetch)
    await expect(request('/TEST', { method: 'POST', body: { message: 'TEST' } })).rejects.toThrow('Нет соединения')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('retains backend validation status and details without retrying', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'TEST missing measured VS' }), { status: 422 })); vi.stubGlobal('fetch', fetch)
    try { await request('/TEST'); throw new Error('Expected rejection') } catch (error) { expect(error).toBeInstanceOf(ApiError); expect((error as ApiError).status).toBe(422); expect((error as Error).message).toContain('VS') }
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('aborts a timed out POST with an explicit warning about replay', async () => {
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('TEST aborted', 'AbortError'))))))
    await expect(request('/TEST', { method: 'POST', timeout: 5 })).rejects.toThrow('Проверьте историю')
  })
  it('does not hide component cancellation as a server error', async () => {
    const controller = new AbortController()
    const fetch = vi.fn((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('TEST aborted', 'AbortError')))))
    vi.stubGlobal('fetch', fetch); const promise = request('/TEST', { signal: controller.signal }); controller.abort()
    await expect(promise).rejects.toThrow('TEST aborted'); expect(fetch).toHaveBeenCalledTimes(1)
  })
})
