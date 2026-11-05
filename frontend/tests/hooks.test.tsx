import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, it } from 'vitest'
import { useQuery } from '../src/hooks'

it('retains the last server response during a refresh without mixing different region keys', async () => {
  const { result, rerender } = renderHook(({ key }) => useQuery(key, async () => ({ region: key, kind: 'TEST fixture' })), { initialProps: { key: 'TEST_REGION_A' } })
  await waitFor(() => expect(result.current.data?.region).toBe('TEST_REGION_A'))
  act(() => result.current.refresh())
  expect(result.current.data?.region).toBe('TEST_REGION_A')
  rerender({ key: 'TEST_REGION_B' })
  expect(result.current.data).toBeUndefined()
  await waitFor(() => expect(result.current.data?.region).toBe('TEST_REGION_B'))
})

it('reports an unavailable backend without inventing a replacement response', async () => {
  const { result } = renderHook(() => useQuery('TEST_ERROR', async () => { throw new Error('TEST backend unavailable') }))
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.data).toBeUndefined()
  expect(result.current.error).toBe('TEST backend unavailable')
})
