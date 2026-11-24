import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import Overview from '../src/pages/Overview'
import Reactor from '../src/pages/Reactor'
import System from '../src/pages/System'
import { agentApi } from '../src/agentV10'
import { api } from '../src/api'
import { reactorApi } from '../src/reactorApi'
import { reactorStatus } from './reactorFixtures'

describe('dashboard polish: first screen, reactor, system', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear() })

  it('Overview shows the live status and three big buttons; «Режим жюри» opens the chat in jury view', async () => {
    vi.spyOn(agentApi, 'status').mockResolvedValue({ model: 'qwen3:8b', llm_available: true, offline: true, mode: 'llm',
      gpu: { loaded: true, gpu_percent: 100 }, version: { commit: 'abc1234', started_at: '2026-11-17T23:01:01+05:00', stale: false } } as never)
    const navigate = vi.fn()
    render(<Overview navigate={navigate} />)
    expect(await screen.findByText('qwen3:8b на видеокарте (100 %)')).toBeInTheDocument()
    expect(screen.getByTestId('home-status-server').textContent).toBe('версия abc1234, запущен в 23:01')
    expect(screen.getByTestId('home-status-offline').textContent).toMatch(/не нужен/)
    fireEvent.click(screen.getByTestId('home-jury'))
    expect(localStorage.getItem('bioreactor-agent-v10-jury')).toBe('1')
    expect(navigate).toHaveBeenCalledWith('chat')
    fireEvent.click(screen.getByTestId('home-calc'))
    expect(navigate).toHaveBeenCalledWith('substrates')
  })

  it('Overview says honestly when the server is stale', async () => {
    vi.spyOn(agentApi, 'status').mockResolvedValue({ model: 'qwen3:8b', llm_available: false, offline: true, mode: 'no_llm', gpu: { loaded: false },
      version: { commit: 'abc1234', stale: true } } as never)
    render(<Overview navigate={vi.fn()} />)
    expect(await screen.findByText(/устарел/)).toBeInTheDocument()
    expect(screen.getByTestId('home-status-model').textContent).toMatch(/не запущена/)
  })

  it('Reactor: the source of the readings is always visible, never presented as real when simulated', async () => {
    vi.spyOn(reactorApi, 'status').mockResolvedValue(reactorStatus() as never)
    vi.spyOn(reactorApi, 'history').mockResolvedValue({ window: 600, points: [], live: true })
    vi.spyOn(reactorApi, 'journal').mockResolvedValue({ items: [], live: true })
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: СИМУЛЯТОР')).toBeInTheDocument()
    expect(screen.getByText('ИИ-агент')).toBeInTheDocument()
  })

  it('System shows a skeleton, not a long spinner, while the first check runs', () => {
    vi.spyOn(api, 'status').mockReturnValue(new Promise(() => {}))
    render(<System />)
    expect(screen.getByTestId('system-skeleton').children).toHaveLength(6)
  })
})
