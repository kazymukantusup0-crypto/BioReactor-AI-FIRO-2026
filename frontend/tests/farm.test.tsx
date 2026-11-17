import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import FarmerCalculator, { amountError, range } from '../src/pages/FarmerCalculator'
import { askAgentQuestion, CHAT_PREFILL_KEY, substratesApi, type EstimateResult } from '../src/substratesApi'
import { advisorApi, type AdvisorCatalog } from '../src/advisorApi'

const r = (low: number, high: number) => ({ low, high })
const catalog = { materials: [
  { id: 'cattle_manure', name: { ru: 'Навоз КРС', kk: 'Сиыр көңі', en: 'Cattle manure' }, form_states: [{ value: 'unknown' }, { value: 'slurry' }, { value: 'fresh_solid' }] },
  { id: 'food_waste', name: { ru: 'Пищевые отходы', kk: 'Тағам қалдықтары', en: 'Food waste' }, form_states: [{ value: 'unknown' }] },
  { id: 'other_organic', name: { ru: 'Другое органическое сырьё', kk: 'Басқа', en: 'Other organic' }, form_states: [{ value: 'unknown' }] },
] } as unknown as AdvisorCatalog
const mixture: EstimateResult = {
  ok: true, status: 'ok', question: null, assumptions: ['VS и BMP — литература'], sources: [{ id: 's1', title: 'KTBL 2025' }],
  data: { status: 'ok', regime_name: 'мезофильный', temperature_c: 37, days: r(25, 35), methane_m3: r(2.47, 5.14), biogas_m3: r(3.99, 9.34),
    energy_kwh: r(24.6, 51.2), methane_potential_m3: r(3.29, 5.71), methane_share: r(.55, .6), wet_mass_kg: r(120, 120),
    components: [
      { substrate: 'cattle_manure', name: 'Навоз КРС', state: 'slurry', amount: 100, unit: 'kg', wet_mass_kg: r(100, 100), methane_m3: r(1.45, 2.57), biogas_m3: r(2.4, 4.7), methane_potential_m3: r(1.9, 2.9), share_of_methane: .53 },
      { substrate: 'food_waste', name: 'Пищевые отходы', state: 'fresh_solid', amount: 20, unit: 'kg', wet_mass_kg: r(20, 20), methane_m3: r(1.02, 2.57), biogas_m3: r(1.6, 4.6), methane_potential_m3: r(1.4, 2.9), share_of_methane: .47 },
    ] },
}

describe('«Сырьё и смеси» farmer calculator', () => {
  beforeEach(() => {
    vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear()
    vi.spyOn(advisorApi, 'catalog').mockResolvedValue(catalog)
    vi.spyOn(substratesApi, 'materials').mockResolvedValue({ with_data: ['cattle_manure', 'food_waste'] })
  })

  it('explains a bad amount next to the field instead of a server error', () => {
    expect(amountError('')).toBe('Введите количество.')
    expect(amountError('-5')).toBe('Количество должно быть больше нуля.')
    expect(amountError('0')).toBe('Количество должно быть больше нуля.')
    expect(amountError('1e12')).toMatch(/Слишком большое/)
    expect(amountError('abc')).toMatch(/нужно число/)
    expect(amountError('2,5')).toBeNull()
  })

  it('builds the chat question the agent understands (same text as the Python test)', () => {
    const names: Record<string, string> = { cattle_manure: 'Навоз КРС', food_waste: 'Пищевые отходы', straw: 'Солома' }
    expect(askAgentQuestion([{ material: 'cattle_manure', quantity: 200, unit: 'L', state: 'slurry' }], 'ru', id => names[id]))
      .toBe('У меня 200 л жидкий навоз крс. Сколько будет газа?')
    expect(askAgentQuestion([{ material: 'cattle_manure', quantity: 100, unit: 'kg' }, { material: 'food_waste', quantity: 20, unit: 'kg' },
      { material: 'straw', quantity: 5000, unit: 'g' }], 'ru', id => names[id]))
      .toBe('У меня 100 кг навоз крс, 20 кг пищевые отходы и 5 кг солома. Сколько будет газа?')
  })

  it('shows four cards with ≈ and a range, the contribution chart, and asks the AI with the mixture', async () => {
    const estimate = vi.spyOn(substratesApi, 'estimate').mockResolvedValue(mixture)
    render(<FarmerCalculator scientific={false} />)
    await screen.findByText('Навоз КРС')
    fireEvent.click(screen.getByTestId('farm-add'))
    await waitFor(() => expect(estimate).toHaveBeenCalled())
    const methane = await screen.findByTestId('farm-card-methane')
    expect(methane.textContent).toContain('≈ 3,8')
    expect(methane.textContent).toContain('2,5–5,1')
    expect(methane.textContent).toContain('потенциал в лаборатории до 5,7')
    expect(screen.getByTestId('farm-card-days').textContent).toContain('25–35')
    expect(screen.getByTestId('farm-chart').textContent).toContain('53 %')
    expect(screen.queryByText(/нет данных/)).toBeNull()  // only materials the agent has data for in the simple view
    fireEvent.click(screen.getByTestId('farm-ask'))
    expect(sessionStorage.getItem(CHAT_PREFILL_KEY)).toBe('У меня 200 л навоз крс и 20 кг пищевые отходы. Сколько будет газа?')
    expect(window.location.hash).toBe('#/chat')
  })

  it('does not call the server with an empty amount and says why', async () => {
    const estimate = vi.spyOn(substratesApi, 'estimate').mockResolvedValue(mixture)
    render(<FarmerCalculator scientific={false} />)
    await screen.findByText('Навоз КРС')
    fireEvent.change(screen.getByTestId('farm-amount-0'), { target: { value: '' } })
    expect(screen.getByRole('alert').textContent).toBe('Введите количество.')
    expect(screen.getByTestId('farm-ask')).toBeDisabled()
    await new Promise(resolve => setTimeout(resolve, 500))
    expect(estimate).not.toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ quantity: 0 })]), expect.anything(), expect.anything())
  })

  it('formats ranges with two significant digits like the chat', () => {
    expect(range(r(0.725535, 1.287))).toBe('0,73–1,3')
    expect(range(r(25, 25))).toBe('25')
  })
})
