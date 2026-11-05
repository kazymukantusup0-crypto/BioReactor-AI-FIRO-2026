// Explicitly fictitious UI fixtures, never persisted in the working database.
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Badge, PriceStatus, Reply, ToolTrace } from '../src/ui'
import { MarketChart } from '../src/MarketChart'
import System from '../src/pages/System'
import { api } from '../src/api'
import type { AgentReply, Price, SystemStatus, ToolCall } from '../src/types'

describe('Scientific truth in presentation', () => {
  it('renders only actually returned tool names', () => {
    const tools: ToolCall[] = [{ tool: 'analyze_substrate', status: 'ok', result: { status: 'ok', message: 'TEST analysis' } }, { tool: 'predict_bmp', status: 'unsupported', result: { status: 'unsupported', message: 'TEST no model applicability' } }]
    const { container } = render(<ToolTrace tools={tools} />)
    expect([...container.querySelectorAll('.trace-chain code')].map(c => c.textContent)).toEqual(['analyze_substrate', 'predict_bmp'])
    expect(screen.queryByText('calculate_profitability')).not.toBeInTheDocument()
  })
  it('does not mark current statistical reference as a trading quote', () => {
    render(<PriceStatus price={{ validation_status: 'VERIFIED_CURRENT', price_type: 'reference' } as Price} />)
    expect(screen.getByText('Свежая статистика')).toBeInTheDocument()
    expect(screen.queryByText('Проверено · свежая')).not.toBeInTheDocument()
  })
  it('shows a failed source as unavailable', () => {
    render(<PriceStatus price={{ validation_status: 'UNAVAILABLE', price_type: 'tariff' } as Price} />)
    expect(screen.getByText('Источник недоступен')).toBeInTheDocument()
  })
  it('does not draw made up history for an empty series', () => {
    const { container } = render(<MarketChart prices={[]} />)
    expect(screen.getByText('Недостаточно истории')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="market-chart"]')).toBeNull()
  })
  it('discloses deterministic fallback, missing inputs and real tool sources', () => {
    const reply: AgentReply = { mode: 'deterministic_tools_no_llm', answer: 'TEST request needs measurements', missing: ['vs_mass_kg'], provider_status: [], tools: [{ tool: 'analyze_substrate', status: 'ok', result: { status: 'ok', message: 'TEST', sources: [{ title: 'TEST source, not live', url: 'https://example.invalid/TEST' }] } }] }
    render(<Reply reply={reply} />)
    expect(screen.getByText('Расчётный режим · без LLM-генерации')).toBeInTheDocument()
    expect(screen.getByText('vs_mass_kg')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'TEST source, not live' })).toHaveAttribute('href', 'https://example.invalid/TEST')
  })
  it('renders unavailable Ollama without claiming a successful generation', async () => {
    const status = { checked_at: '2020-01-01T00:00:00Z', fastapi: { status: 'ok' }, sqlite: { status: 'ok', observations: 0, test_observations: 0 }, ollama: { available: false, service_available: false, model: 'TEST_MODEL', generation_checked: false }, models: [], sensors: { connected: false, message: 'TEST no sensors' }, market: { status: 'available', source_states: [], last_success_at: null, validation_counts: {} }, network_mode: 'local', internet_connection: 'not_probed', online_provider_configured: false, actuator_access: false } as unknown as SystemStatus
    vi.spyOn(api, 'status').mockResolvedValue(status)
    render(<System />)
    expect(await screen.findByText('Модель или сервис недоступны')).toBeInTheDocument()
    expect(screen.getByText('NO LIVE SENSOR DATA')).toBeInTheDocument()
    expect(screen.queryByText('Сервис и модель доступны')).not.toBeInTheDocument()
  })
})
