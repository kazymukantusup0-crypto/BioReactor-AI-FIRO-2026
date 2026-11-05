// Explicit TEST fixtures: no prices or measurements are persisted by these tests.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compactValues, processApi } from '../src/processApi'
import type { ProcessCandidate } from '../src/processApi'
import { ProcessResults, processMetricRows } from '../src/pages/ProcessOptimizer'
import ProcessOptimizer from '../src/pages/ProcessOptimizer'
import ExperimentLab, { measurementChartRows } from '../src/pages/ExperimentLab'
import { ResultValue } from '../src/ProcessComponents'

afterEach(() => vi.restoreAllMocks())
const candidate = (outputs: Record<string, unknown> = {}): ProcessCandidate => ({ scenario_id: 'TEST_ONLY', label: 'TEST 35 °C', feasibility_status: 'INSUFFICIENT_DATA', input_parameters: { temperature_c: 35 }, assumptions: [], scientific_sources: [], constraints: [], predicted_outputs: outputs, uncertainty_status: 'not_quantified', warnings: ['TEST: VS is unknown'] })

describe('Process science presentation', () => {
  it('omits unknown values and preserves explicit zeroes', () => {
    expect(compactValues({ mass_kg: '', auxiliary_energy_kwh: '0', material: 'cattle_manure' }, ['material'])).toEqual({ auxiliary_energy_kwh: 0, material: 'cattle_manure' })
  })
  it('never transforms unknown or nonfinite outputs into zero', () => {
    const row = processMetricRows([candidate({ energy: { initial_heating_kwh: 1, total_energy_kwh: null }, methane: {} })])[0]
    expect(row.initial).toBe(1); expect(row.total).toBeUndefined(); expect(row.methane).toBeUndefined()
    render(<ResultValue value={Infinity} />); expect(screen.getByText('Недостаточно данных')).toBeInTheDocument()
  })
  it('does not render energy or methane charts when inputs are incomplete', () => {
    const { container } = render(<ProcessResults result={{ scenarios: [candidate()] }} />)
    expect(container.querySelector('[data-testid="process-energy-chart"]')).toBeNull()
    expect(container.querySelector('[data-testid="process-methane-chart"]')).toBeNull()
    expect(screen.getAllByText('INSUFFICIENT_DATA')).toHaveLength(2)
    expect(screen.getByText(/Температура сама по себе не меняет BMP/)).toBeInTheDocument()
  })
  it('sends two explicitly selected temperatures and no invented density or mass', async () => {
    vi.spyOn(processApi, 'scenarios').mockResolvedValue({ scenarios: [] })
    const call = vi.spyOn(processApi, 'optimize').mockResolvedValue({ scenarios: [candidate()] })
    render(<ProcessOptimizer />)
    fireEvent.change(screen.getByLabelText('Объём всей партии'), { target: { value: '800' } })
    fireEvent.change(screen.getByLabelText('Полный объём реактора'), { target: { value: '90' } })
    fireEvent.change(screen.getByLabelText('Температура сценария 1'), { target: { value: '35' } })
    fireEvent.change(screen.getByLabelText('Температура сценария 2'), { target: { value: '38' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить и сохранить' }))
    await waitFor(() => expect(call).toHaveBeenCalledTimes(1))
    const body = call.mock.calls[0][0]
    expect(body.feedstock_volume_l).toBe(800); expect(body.reactor_total_volume_l).toBe(90)
    expect(body).not.toHaveProperty('mass_kg'); expect(body).not.toHaveProperty('density_kg_l')
    expect(body.objectives).toEqual([])
    expect((body.candidates as { overrides: { temperature_c: number } }[]).map(c => c.overrides.temperature_c)).toEqual([35, 38])
  })
  it('keeps missing measurements as gaps, without methane from biogas alone', () => {
    expect(measurementChartRows([{ observed_at: 'TEST', gas_volume_m3: 0.002 }])).toEqual([{ name: 'TEST', temperature: null, gas: 0.002 }])
  })
  it('requires explicit experiment origin and keeps optional measurements unknown', async () => {
    vi.spyOn(processApi, 'experiments').mockResolvedValue({ experiments: [] })
    const create = vi.spyOn(processApi, 'createExperiment').mockResolvedValue({ id: 'TEST_1', name: 'TEST_ONLY', origin: 'user' })
    vi.spyOn(processApi, 'measurements').mockResolvedValue({ measurements: [] })
    vi.spyOn(processApi, 'experimentComparison').mockResolvedValue({ status: 'INSUFFICIENT_DATA', reasons: ['TEST: no gas fraction'] })
    render(<ExperimentLab />)
    const save = screen.getByRole('button', { name: 'Сохранить эксперимент' })
    fireEvent.change(screen.getByLabelText('Название эксперимента'), { target: { value: 'TEST_ONLY' } })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Происхождение измерений'), { target: { value: 'user' } })
    expect(save).toBeEnabled(); fireEvent.click(save)
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    const body = create.mock.calls[0][0]
    expect(body).not.toHaveProperty('gas_volume_m3'); expect(body).not.toHaveProperty('methane_fraction'); expect(body).not.toHaveProperty('vs_mass_kg')
    expect(body.quantitative_method_confirmed).toBe(false)
  })
})
