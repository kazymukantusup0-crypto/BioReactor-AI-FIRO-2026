// «Реактор»: source label, levels, confirmation before every command, leak alarm, interlock, no link, jury mode.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Reactor, { duration, formatValue } from '../src/pages/Reactor'
import { reactorApi } from '../src/reactorApi'
import { reactorStatus } from './reactorFixtures'

function mockApi(status = reactorStatus()) {
  const statusSpy = vi.spyOn(reactorApi, 'status').mockResolvedValue(status)
  vi.spyOn(reactorApi, 'history').mockResolvedValue({ window: 600, points: [], live: true })
  vi.spyOn(reactorApi, 'journal').mockResolvedValue({ items: [
    { id: 2, ts: '2026-11-18T05:00:10+00:00', kind: 'alarm', what: 'leak', who: 'pi_safety', result: 'heater_off_and_locked', source: 'virtual', details: {} },
    { id: 1, ts: '2026-11-18T05:00:00+00:00', kind: 'command', what: 'heat_on', who: 'operator', result: 'ok', source: 'virtual', details: {} },
  ], live: true })
  return statusSpy
}

describe('Reactor page', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear() })

  it('shows SIMULATOR, readings with levels and the honest MQ caption', async () => {
    mockApi()
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: СИМУЛЯТОР')).toBeInTheDocument()
    const temp = screen.getByTestId('rx-reading-temp_c')
    expect(temp.textContent).toContain('31.2')
    expect(temp.textContent).toContain('внимание')
    expect(screen.getByTestId('rx-reading-gas_in').textContent).toMatch(/НЕ «% метана»/)
    expect(screen.getByTestId('rx-reading-p_kpa').textContent).toMatch(/откачивать пока рано/)
    expect(screen.getByTestId('rx-simulator')).toBeInTheDocument()
    expect(await screen.findByText('Тревога: утечка газа')).toBeInTheDocument()
    expect(screen.getByText('защита Raspberry Pi')).toBeInTheDocument()
  })

  it('shows the Raspberry Pi address when the real chain is used', async () => {
    mockApi(reactorStatus({ source: { kind: 'pi', address: '192.168.50.2:8780', arduino_port: '/dev/ttyACM0', firmware: '0.1' }, simulator: null }))
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: RASPBERRY PI → ARDUINO (192.168.50.2:8780)')).toBeInTheDocument()
    expect(screen.queryByTestId('rx-simulator')).toBeNull()
  })

  it('says the Arduino is virtual when the real Pi runs with --simulate', async () => {
    mockApi(reactorStatus({ source: { kind: 'pi', address: '172.20.10.3:8780', arduino_port: 'virtual', firmware: 'virtual-0.1' }, simulator: null }))
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: RASPBERRY PI (172.20.10.3:8780) → ВИРТУАЛЬНЫЙ ARDUINO')).toBeInTheDocument()
  })

  it('asks for confirmation before switching a relay; cancel sends nothing', async () => {
    mockApi()
    const relay = vi.spyOn(reactorApi, 'relay').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-relay-button-heat'))
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Включить: Подогрев\?/)
    fireEvent.click(screen.getByText('Отмена'))
    expect(relay).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('rx-relay-button-heat'))
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(relay).toHaveBeenCalledWith('heat', true))
    expect(await screen.findByTestId('rx-message')).toHaveTextContent('Подогрев: включено')
  })

  it('shows the refusal reason from the Pi', async () => {
    mockApi()
    vi.spyOn(reactorApi, 'relay').mockResolvedValue({ ok: false, reason: 'interlock' })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-relay-button-cool'))
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    expect(await screen.findByTestId('rx-message')).toHaveTextContent('Команда отклонена: нельзя: подогрев и охлаждение одновременно не включаются')
  })

  it('interlock: the heater button is disabled while the cooling is on, with the reason', async () => {
    mockApi(reactorStatus({}, { cool: { on: true, on_for_s: 75, total_s: 75 }, heat: { on_blocked: 'interlock' } }))
    render(<Reactor />)
    expect(await screen.findByTestId('rx-relay-button-heat')).toBeDisabled()
    expect(screen.getByTestId('rx-relay-blocked-heat').textContent).toMatch(/одновременно/)
    expect(screen.getByTestId('rx-relay-cool').textContent).toMatch(/работает 1 мин 15 с/)
    expect(screen.getByTestId('rx-relay-button-cool')).toHaveTextContent('Выключить')
  })

  it('leak: full-screen alarm, heater locked, reset disabled while the gas is still there', async () => {
    mockApi(reactorStatus({
      readings: { ...reactorStatus().readings, gas_out: { value: 612, last: 612, level: 'danger' } },
      alarms: [{ code: 'leak', level: 'danger', needs_reset: true, still_leaking: true, since: 1 }], leak_latched: true,
    }, { heat: { on_blocked: 'leak_lock' } }))
    const reset = vi.spyOn(reactorApi, 'resetLeak').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    const alarm = await screen.findByTestId('rx-leak-alarm')
    expect(alarm.textContent).toMatch(/УТЕЧКА ГАЗА/)
    expect(alarm.textContent).toMatch(/Подогрев выключен автоматически и заблокирован/)
    expect(screen.getByTestId('rx-leak-reset')).toBeDisabled()
    expect(screen.getByTestId('rx-relay-button-heat')).toBeDisabled()
    expect(reset).not.toHaveBeenCalled()
  })

  it('leak gone: a person resets the alarm after a confirmation', async () => {
    mockApi(reactorStatus({ alarms: [{ code: 'leak', level: 'danger', needs_reset: true, still_leaking: false, since: 1 }], leak_latched: true }, { heat: { on_blocked: 'leak_lock' } }))
    const reset = vi.spyOn(reactorApi, 'resetLeak').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-leak-reset'))
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Сбросить тревогу утечки\?/)
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(reset).toHaveBeenCalled())
  })

  it('no link with the Arduino: banner, every button disabled, values not shown as current', async () => {
    const lost = reactorStatus({ link: { ok: false, level: 'arduino', network_ok: true, arduino_ok: false, seconds_since_pi: 0.5, error: null }, controls_enabled: false,
      readings: { temp_c: { value: null, last: 36.1, level: 'unknown' }, rh_pct: { value: null, last: 80, level: 'unknown' }, gas_in: { value: null, last: 400, level: 'unknown' },
        gas_out: { value: null, last: 70, level: 'unknown' }, p_kpa: { value: null, last: 1.1, level: 'unknown', fill_share: null } },
      alarms: [{ code: 'arduino_lost', level: 'danger' }] }, { heat: { on_blocked: 'no_link' }, cool: { on_blocked: 'no_link' }, pump: { on_blocked: 'no_link' } })
    mockApi(lost)
    render(<Reactor />)
    expect(await screen.findByText('НЕТ СВЯЗИ С ARDUINO')).toBeInTheDocument()
    for (const relay of ['heat', 'cool', 'pump']) expect(screen.getByTestId(`rx-relay-button-${relay}`)).toBeDisabled()
    expect(screen.getByTestId('rx-reading-temp_c').textContent).toMatch(/последнее известное: 36.1 °C \(устарело\)/)
    expect(screen.getByTestId('rx-reading-temp_c').querySelector('.rx-reading-value')?.textContent).toMatch(/^—/)
  })

  it('no link with the Pi', async () => {
    mockApi(reactorStatus({ link: { ok: false, level: 'pi', network_ok: false, arduino_ok: false, seconds_since_pi: 9, error: 'timed out' }, controls_enabled: false, alarms: [{ code: 'pi_lost', level: 'danger' }] }))
    render(<Reactor />)
    expect(await screen.findByText('НЕТ СВЯЗИ С RASPBERRY PI')).toBeInTheDocument()
  })

  it('«Проверить связь» shows the answer time and the Arduino port', async () => {
    mockApi()
    vi.spyOn(reactorApi, 'check').mockResolvedValue({ ok: true, url: 'http://127.0.0.1:1', mode: 'simulator', latency_ms: 4, arduino_ok: true, port: 'virtual' })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-check'))
    expect(await screen.findByTestId('rx-check-result')).toHaveTextContent('Связь есть: 4 мс, Arduino на связи: да, порт virtual')
  })

  it('jury mode: big panel with readings and relay states, remembered', async () => {
    mockApi(reactorStatus({}, { pump: { on: true, on_for_s: 30 } }))
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-jury'))
    const panel = screen.getByTestId('rx-jury-panel')
    expect(panel.textContent).toContain('ДАТЧИКИ: СИМУЛЯТОР')
    expect(screen.getByTestId('rx-relay-state-pump')).toHaveTextContent('ВКЛ')
    expect(screen.queryByTestId('rx-relay-button-pump')).toBeNull()
    expect(localStorage.getItem('bioreactor-reactor-jury')).toBe('1')
  })

  it('formats values and durations', () => {
    expect(formatValue('p_kpa', 1.256)).toBe('1.26')
    expect(formatValue('gas_in', 431.6)).toBe('432')
    expect(formatValue('temp_c', null)).toBe('—')
    expect(duration(42)).toBe('42 с')
    expect(duration(3725)).toBe('1 ч 2 мин')
  })
})
