// «Реактор» (firmware bioreactor-1.0): source + route, raw gas indicator, confirmation before every command, E-STOP
// without confirmation, alarms, AUTO mode, auger, EEPROM thresholds, no link, jury mode.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Reactor, { duration, formatValue } from '../src/pages/Reactor'
import { reactorApi } from '../src/reactorApi'
import { NO_ALARMS, reactorStatus } from './reactorFixtures'

function mockApi(status = reactorStatus()) {
  const statusSpy = vi.spyOn(reactorApi, 'status').mockResolvedValue(status)
  vi.spyOn(reactorApi, 'history').mockResolvedValue({ window: 600, points: [], live: true })
  vi.spyOn(reactorApi, 'journal').mockResolvedValue({ items: [
    { id: 3, ts: '2026-11-18T05:00:20+00:00', kind: 'safety', what: 'auger_off', who: 'pi_safety', result: 'ok', source: 'arduino /dev/ttyUSB0', details: {} },
    { id: 2, ts: '2026-11-18T05:00:10+00:00', kind: 'alarm', what: 'leak', who: 'arduino_safety', result: null, source: 'arduino /dev/ttyUSB0', details: {} },
    { id: 1, ts: '2026-11-18T05:00:00+00:00', kind: 'command', what: 'auger_on', who: 'operator', result: 'ok', source: 'arduino /dev/ttyUSB0', details: {} },
  ], live: true })
  return statusSpy
}

const real = (over = {}) => reactorStatus({ source: { kind: 'pi', mode: 'auto', address: '10.42.0.1:8780', route: 'pi_wifi', arduino_port: '/dev/ttyUSB0', firmware: 'bioreactor-1.0' }, simulator: null, ...over })

describe('Reactor page', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear() })

  it('shows SIMULATOR, four readings with levels and the honest raw gas caption', async () => {
    mockApi()
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: СИМУЛЯТОР')).toBeInTheDocument()
    const temp = screen.getByTestId('rx-reading-temp_c')
    expect(temp.textContent).toContain('31.2')
    expect(temp.textContent).toContain('внимание')
    expect(temp.textContent).toMatch(/норма 35–38 °C/)
    const gas = screen.getByTestId('rx-reading-gas_in').textContent
    expect(gas).toMatch(/индикатор \(сырое значение 0–1023\)/)
    expect(gas).toMatch(/не ppm и не % метана/)
    expect(screen.getByTestId('rx-reading-gas_out').textContent).toMatch(/выше 400 — тревога утечки/)
    expect(screen.queryByTestId('rx-reading-p_kpa')).toBeNull()
    expect(screen.getByTestId('rx-simulator')).toBeInTheDocument()
    expect(await screen.findByText('Тревога: утечка газа')).toBeInTheDocument()
    expect(screen.getByText('защита Raspberry Pi')).toBeInTheDocument()
  })

  it('real chain: Pi address, the route (Wi-Fi of the Pi / cable) and no simulator panel', async () => {
    mockApi(real())
    render(<Reactor />)
    expect(await screen.findByText(/ДАТЧИКИ: RASPBERRY PI → ARDUINO \(10\.42\.0\.1:8780\)/)).toBeInTheDocument()
    expect(screen.getByTestId('rx-route')).toHaveTextContent('через Wi-Fi Pi')
    expect(screen.queryByTestId('rx-simulator')).toBeNull()
  })

  it('cable route', async () => {
    mockApi(real({ source: { kind: 'pi', mode: 'auto', address: '192.168.50.2:8780', route: 'cable', arduino_port: '/dev/ttyUSB0', firmware: 'bioreactor-1.0' } }))
    render(<Reactor />)
    expect(await screen.findByTestId('rx-route')).toHaveTextContent('через кабель')
  })

  it('says the Arduino is virtual when the real Pi runs with --simulate', async () => {
    mockApi(reactorStatus({ source: { kind: 'pi', address: '172.20.10.3:8780', arduino_port: 'virtual', firmware: 'bioreactor-1.0-virtual' }, simulator: null }))
    render(<Reactor />)
    expect(await screen.findByText('ДАТЧИКИ: RASPBERRY PI (172.20.10.3:8780) → ВИРТУАЛЬНЫЙ ARDUINO')).toBeInTheDocument()
  })

  it('four relays incl. the auger; asks for confirmation; cancel sends nothing', async () => {
    mockApi()
    const relay = vi.spyOn(reactorApi, 'relay').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    expect(await screen.findByTestId('rx-relay-auger')).toHaveTextContent('Шнек (мотор)')
    fireEvent.click(screen.getByTestId('rx-relay-button-auger'))
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Включить: Шнек \(мотор\)\?.*нет рук/)
    fireEvent.click(screen.getByText('Отмена'))
    expect(relay).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('rx-relay-button-heat'))
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(relay).toHaveBeenCalledWith('heat', true))
    expect(await screen.findByTestId('rx-message')).toHaveTextContent('Подогрев: включено')
  })

  it('shows who switched a relay on: the laptop or the Arduino', async () => {
    mockApi(reactorStatus({ auto: true }, { heat: { on: true, remote: false }, auger: { on: true, remote: true } }))
    render(<Reactor />)
    expect(await screen.findByTestId('rx-relay-who-heat')).toHaveTextContent('включено на Arduino')
    expect(screen.getByTestId('rx-relay-who-auger')).toHaveTextContent('включено с ноутбука')
  })

  it('shows the refusal reason (the Arduino error code)', async () => {
    mockApi()
    vi.spyOn(reactorApi, 'relay').mockResolvedValue({ ok: false, reason: 'interlock' })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-relay-button-cool'))
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    expect(await screen.findByTestId('rx-message')).toHaveTextContent('Команда отклонена: нельзя: подогрев и охлаждение одновременно')
  })

  it('interlock: the heater button is disabled while the cooling is on, with the reason', async () => {
    mockApi(reactorStatus({}, { cool: { on: true, on_for_s: 75, total_s: 75 }, heat: { on_blocked: 'interlock' } }))
    render(<Reactor />)
    expect(await screen.findByTestId('rx-relay-button-heat')).toBeDisabled()
    expect(screen.getByTestId('rx-relay-blocked-heat').textContent).toMatch(/одновременно/)
    expect(screen.getByTestId('rx-relay-cool').textContent).toMatch(/работает 1 мин 15 с/)
    expect(screen.getByTestId('rx-relay-button-cool')).toHaveTextContent('Выключить')
  })

  it('AUTO mode: state and switch with confirmation', async () => {
    mockApi(reactorStatus({ auto: true }))
    const auto = vi.spyOn(reactorApi, 'auto').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    expect(await screen.findByTestId('rx-mode-state')).toHaveTextContent('АВТО')
    fireEvent.click(screen.getByTestId('rx-mode-button'))
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Выключить автоматику\?/)
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(auto).toHaveBeenCalledWith(false))
  })

  it('E-STOP: one click, no confirmation', async () => {
    mockApi()
    const estop = vi.spyOn(reactorApi, 'estop').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-estop'))
    await waitFor(() => expect(estop).toHaveBeenCalled())
    expect(screen.queryByTestId('rx-confirm')).toBeNull()
    expect(await screen.findByTestId('rx-message')).toHaveTextContent('АВАРИЙНАЯ ОСТАНОВКА')
  })

  it('E-STOP active: big alarm, reset after a confirmation', async () => {
    mockApi(reactorStatus({ alarms: [{ code: 'estop', level: 'danger', needs_reset: true, since: 5 }], arduino_alarms: { ...NO_ALARMS, estop: true } },
      { heat: { on_blocked: 'estop' }, auger: { on_blocked: 'estop' } }))
    const reset = vi.spyOn(reactorApi, 'resetAlarms').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    const alarm = await screen.findByTestId('rx-estop-alarm')
    expect(alarm.textContent).toMatch(/АВАРИЙНАЯ ОСТАНОВКА/)
    expect(screen.getByTestId('rx-mode-button')).toBeDisabled()
    fireEvent.click(screen.getByTestId('rx-alarm-reset'))
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Сбросить тревоги\?/)
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(reset).toHaveBeenCalled())
  })

  it('leak: full-screen alarm, everything locked, reset disabled while the gas is still there', async () => {
    mockApi(reactorStatus({
      readings: { ...reactorStatus().readings, gas_out: { value: 612, last: 612, level: 'danger' } },
      alarms: [{ code: 'leak', level: 'danger', needs_reset: true, still_leaking: true, since: 1 }], arduino_alarms: { ...NO_ALARMS, leak: true },
    }, { heat: { on_blocked: 'leak' }, pump: { on_blocked: 'leak' } }))
    const reset = vi.spyOn(reactorApi, 'resetAlarms').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    const alarm = await screen.findByTestId('rx-leak-alarm')
    expect(alarm.textContent).toMatch(/УТЕЧКА ГАЗА/)
    expect(alarm.textContent).toMatch(/Arduino выключила все реле и автоматику/)
    expect(alarm.textContent).toMatch(/612 \(сырое значение\) при пороге 400/)
    expect(screen.getByTestId('rx-alarm-reset')).toBeDisabled()
    expect(screen.getByTestId('rx-relay-button-heat')).toBeDisabled()
    expect(reset).not.toHaveBeenCalled()
  })

  it('every Arduino alarm is shown in the list', async () => {
    const codes = ['overheat', 'no_temp', 'link_lost', 'auger_timeout', 'warmup', 'laptop_lost']
    mockApi(reactorStatus({ alarms: codes.map(code => ({ code, level: code === 'warmup' || code === 'auger_timeout' ? 'warn' as const : 'danger' as const })) }))
    render(<Reactor />)
    for (const code of codes) expect(await screen.findByTestId(`rx-alarm-${code}`)).toBeInTheDocument()
    expect(screen.getByTestId('rx-alarm-overheat')).toHaveTextContent('ПЕРЕГРЕВ')
    expect(screen.getByTestId('rx-alarm-auger_timeout')).toHaveTextContent('дольше 10 минут')
    expect(screen.getByTestId('rx-alarm-no_temp')).toHaveAttribute('role', 'alert')
  })

  it('thresholds: five EEPROM limits, a change needs a confirmation', async () => {
    mockApi()
    const limit = vi.spyOn(reactorApi, 'limit').mockResolvedValue({ ok: true, reason: null })
    render(<Reactor />)
    for (const name of ['temp_min', 'temp_max', 'temp_hard_max', 'gas_out_limit', 'gas_in_limit']) expect(await screen.findByTestId(`rx-limit-${name}`)).toBeInTheDocument()
    const save = screen.getByTestId('rx-limit-save-temp_min')
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByTestId('rx-limit-input-temp_min'), { target: { value: '36.5' } })
    fireEvent.click(save)
    expect(screen.getByTestId('rx-confirm').textContent).toMatch(/Было 35\.0 °C, станет 36\.5 °C/)
    expect(limit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('rx-confirm-yes'))
    await waitFor(() => expect(limit).toHaveBeenCalledWith('temp_min', 36.5))
    fireEvent.change(screen.getByTestId('rx-limit-input-gas_out_limit'), { target: { value: '5000' } })
    expect(screen.getByTestId('rx-limit-save-gas_out_limit')).toBeDisabled()
  })

  it('no link with the Arduino: banner, every button disabled, values not shown as current', async () => {
    const lost = reactorStatus({ link: { ok: false, level: 'arduino', network_ok: true, arduino_ok: false, seconds_since_pi: 0.5, error: null }, controls_enabled: false,
      readings: { temp_c: { value: null, last: 36.1, level: 'unknown' }, rh_pct: { value: null, last: 80, level: 'unknown' }, gas_in: { value: null, last: 400, level: 'unknown' },
        gas_out: { value: null, last: 70, level: 'unknown' } },
      alarms: [{ code: 'arduino_lost', level: 'danger' }] }, { heat: { on_blocked: 'no_link' }, cool: { on_blocked: 'no_link' }, pump: { on_blocked: 'no_link' }, auger: { on_blocked: 'no_link' } })
    mockApi(lost)
    render(<Reactor />)
    expect(await screen.findByText('НЕТ СВЯЗИ С ARDUINO')).toBeInTheDocument()
    for (const relay of ['heat', 'cool', 'pump', 'auger']) expect(screen.getByTestId(`rx-relay-button-${relay}`)).toBeDisabled()
    expect(screen.getByTestId('rx-mode-button')).toBeDisabled()
    expect(screen.getByTestId('rx-reading-temp_c').textContent).toMatch(/последнее известное: 36.1 °C \(устарело\)/)
    expect(screen.getByTestId('rx-reading-temp_c').querySelector('.rx-reading-value')?.textContent).toMatch(/^—/)
    expect(screen.getByTestId('rx-estop')).not.toBeDisabled()
  })

  it('Arduino starting after the port opened', async () => {
    mockApi(reactorStatus({ link: { ok: false, level: 'arduino', network_ok: true, arduino_ok: false, seconds_since_pi: 0.2, error: null }, controls_enabled: false,
      alarms: [{ code: 'arduino_starting', level: 'danger' }] }))
    render(<Reactor />)
    expect(await screen.findByText('ARDUINO ЗАПУСКАЕТСЯ')).toBeInTheDocument()
  })

  it('no link with the Pi: E-STOP disabled too (it cannot reach the Arduino)', async () => {
    mockApi(reactorStatus({ link: { ok: false, level: 'pi', network_ok: false, arduino_ok: false, seconds_since_pi: 9, error: 'timed out' }, controls_enabled: false, estop_enabled: false, alarms: [{ code: 'pi_lost', level: 'danger' }] }))
    render(<Reactor />)
    expect(await screen.findByText('НЕТ СВЯЗИ С RASPBERRY PI')).toBeInTheDocument()
    expect(screen.getByTestId('rx-estop')).toBeDisabled()
  })

  it('«Проверить связь» shows the route, the answer time and the Arduino port', async () => {
    mockApi(real())
    vi.spyOn(reactorApi, 'check').mockResolvedValue({ ok: true, url: 'http://10.42.0.1:8780', mode: 'auto', route: 'pi_wifi', latency_ms: 4, arduino_ok: true, port: '/dev/ttyUSB0' })
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-check'))
    expect(await screen.findByTestId('rx-check-result')).toHaveTextContent('Связь есть (через Wi-Fi Pi): 4 мс, Arduino на связи: да, порт /dev/ttyUSB0')
  })

  it('jury mode: big panel with readings and relay states, remembered', async () => {
    mockApi(reactorStatus({}, { pump: { on: true, on_for_s: 30 } }))
    render(<Reactor />)
    fireEvent.click(await screen.findByTestId('rx-jury'))
    const panel = screen.getByTestId('rx-jury-panel')
    expect(panel.textContent).toContain('ДАТЧИКИ: СИМУЛЯТОР')
    expect(screen.getByTestId('rx-relay-state-pump')).toHaveTextContent('ВКЛ')
    expect(screen.queryByTestId('rx-relay-button-pump')).toBeNull()
    expect(screen.getByTestId('rx-estop')).toBeInTheDocument()
    expect(localStorage.getItem('bioreactor-reactor-jury')).toBe('1')
  })

  it('formats values and durations', () => {
    expect(formatValue('temp_c', 36.26)).toBe('36.3')
    expect(formatValue('gas_in', 431.6)).toBe('432')
    expect(formatValue('temp_c', null)).toBe('—')
    expect(duration(42)).toBe('42 с')
    expect(duration(3725)).toBe('1 ч 2 мин')
  })
})
