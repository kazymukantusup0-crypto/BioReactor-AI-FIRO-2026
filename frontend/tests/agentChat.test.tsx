// UI fixtures only: the numbers below are test data, not measurements.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentChat, { AnswerView, applyEvent, feedLine, type Turn } from '../src/pages/AgentChat'
import { componentText, parseSSE, pluralRu, speedWarning, type AgentStatus } from '../src/agentV10'

const FACTS = { components: [{ substrate: 'cattle_manure', amount: 200, unit: 'L', state: 'slurry' }], reactor_volume_l: null, insulation: null, ambient_c: null, target_c: null, days: null }
const ANSWER = {
  text: 'TEST', explanation: 'Из 200 литров получится около 4.9 м³ биогаза.', question: 'Какой объём у реактора?',
  numbers: [{ key: 'methane', title: 'Метан', value: '2.9–5.2', unit: 'м³', label: 'literature', badge: 'оценка по литературе' }],
  assumptions: ['температура 37 °C (мезофильный режим)'], sources: [{ id: 's1', title: 'TEST source', year: 2020, url: null }],
  tools: ['estimate_methane'], data: { estimate_methane: { status: 'ok' } }, mode: 'llm', verified: true, language: 'ru',
  model: 'qwen3:8b', timings: { total_ms: 3100, first_answer_token_ms: 2100, prompt_tokens_max: 1500 },
}
const EVENTS = [
  { type: 'understood', t_ms: 1, language: 'ru' },
  { type: 'facts', t_ms: 2, updates: { components: FACTS.components }, facts: FACTS },
  { type: 'llm_step', t_ms: 900, step: 1, decision: 'tool_calls', prompt_tokens: 1400, output_tokens: 20, duration_ms: 890 },
  { type: 'tool_call', t_ms: 901, name: 'estimate_methane', args: {}, by: 'llm' },
  { type: 'tool_result', t_ms: 905, name: 'estimate_methane', ok: true, summary: { methane_m3: [2.9, 5.2] }, duration_ms: 4 },
  { type: 'token', t_ms: 2100, text: 'Из 200 ' },
  { type: 'verification', t_ms: 3000, ok: true, unknown_numbers: [], attempt: 1 },
  { type: 'answer', t_ms: 3050, ...ANSWER },
  { type: 'done', t_ms: 3100, mode: 'llm', total_ms: 3100 },
]
function AnswerHarness({ turn }: { turn: Turn }) { return <AnswerView answer={turn.answer!} jury={false} /> }
const sse = (events: object[]) => events.map(e => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join('')

function streamBody(text: string) {
  const bytes = new TextEncoder().encode(text)
  let sent = false
  return { getReader: () => ({ read: async () => sent ? { done: true, value: undefined } : (sent = true, { done: false, value: bytes }) }) }
}

function stubServer() {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => data })
    if (url === '/api/agent/status') return ok({ model: 'qwen3:8b', llm_available: true, offline: true, mode: 'llm', gpu: { loaded: true, gpu_percent: 100 } })
    if (url === '/api/agent/demo-reactor') return ok({ name: 'Пластиковая бочка 200 л', reactor_volume_l: 200, working_volume_l: 160, insulation: 'none', ambient_c: 5, target_c: 37, days: 30, feedstock: { substrate: 'cattle_manure', state: 'slurry' } })
    if (url.startsWith('/api/agent/conversations/')) return ok({ id: 'x', exists: false, facts: FACTS, messages: [], last_answer: null })
    if (url === '/api/agent/chat') return { ok: true, status: 200, body: streamBody(sse(EVENTS)) }
    return ok({ ok: true })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('agent v10 SSE client', () => {
  it('parses complete events and keeps the unfinished tail', () => {
    const text = 'event: a\r\ndata: {"type":"a","n":1}\r\n\r\nevent: b\ndata: {"type":"b"}\n\nevent: c\ndata: {"ty'
    const { events, rest } = parseSSE(text)
    expect(events.map(e => e.type)).toEqual(['a', 'b'])
    expect(rest).toContain('"ty')
  })
  it('names components in plain Russian', () => {
    expect(componentText({ substrate: 'cattle_manure', amount: 200, unit: 'L', state: 'slurry' })).toBe('навоз КРС: 200 л, жидкий')
    expect(componentText({ substrate: 'swine_manure', amount: 2, unit: 'ведра', value: 20, base_unit: 'L', state: null })).toBe('свиной навоз: 20 л')
  })
})

describe('verdicts and ≈ values', () => {
  it('shows the central estimate big and the range small, and the advice as before → after', () => {
    const answer = { ...ANSWER,
      numbers: [{ key: 'methane', title: 'Метан', value: '2.9–5.2', center: '4', range: '2.9–5.2', unit: 'м³', label: 'literature', badge: 'оценка по литературе' }],
      verdicts: [
        { key: 'net', code: 'minus', title: 'Энергобаланс', value: 'минус: ≈−685 (−1040 … −330)', text: 'Чистый энергобаланс отрицательный', tone: 'bad' },
        { key: 'advice', code: 'eps50', title: 'Совет: было → стало', value: '≈−685 → ≈−36 кВт·ч', text: 'Совет: утеплите реактор пенополистиролом 50 мм', tone: 'warn' },
      ] }
    const turn: Turn = { id: 't', user: 'q', events: [], live: '', running: false, answer: answer as never }
    render(<AnswerHarness turn={turn} />)
    expect(screen.getByText('≈4')).toBeInTheDocument()
    expect(screen.getByText('2.9–5.2 м³')).toBeInTheDocument()
    expect(screen.getByText('минус: ≈−685 (−1040 … −330)')).toBeInTheDocument()
    expect(screen.getByText('≈−685 → ≈−36 кВт·ч')).toBeInTheDocument()
    expect(screen.getByText('Совет: утеплите реактор пенополистиролом 50 мм')).toBeInTheDocument()
  })
  it('explains a contradiction with a Python verdict in the feed', () => {
    const line = feedLine({ type: 'verification', ok: false, unknown_numbers: [], contradicts: ['Газа не хватит на подогрев'], attempt: 1 })
    expect(line?.title).toContain('противоречит выводу Python')
  })
})

describe('heat loss card', () => {
  it('shows U, area, UA and the source under the number', () => {
    const answer = { text: '', explanation: '', question: null, assumptions: [], sources: [], verified: true, mode: 'llm', tools: [],
      numbers: [{ key: 'heat_loss', title: 'Теплопотери через стенки', value: '321–972', center: '646', range: '321–972', unit: 'кВт·ч', label: 'assumption', badge: 'допущение',
        details: ['U без утепления: 5.44–11.16 · с пенополистиролом 50 мм: 0.62–0.75 Вт/(м²·К)', 'площадь стенок: 1.89 м² · UA = U × площадь = 10.3–21.1 Вт/К'] }] }
    render(<AnswerView answer={answer as never} jury={false} />)
    expect(screen.getByText(/5.44–11.16/)).toBeTruthy()
    expect(screen.getByText(/UA = U × площадь = 10.3–21.1/)).toBeTruthy()
  })
})

describe('model speed warning', () => {
  const base: AgentStatus = { model: 'qwen3:8b', llm_available: true, offline: true, mode: 'llm', gpu: { loaded: true, gpu_percent: 100, others: [] } }
  it('is silent when the model is fully on the GPU', () => { expect(speedWarning(base)).toBeNull() })
  it('warns about another model, a cold model and a CPU share', () => {
    expect(speedWarning({ ...base, gpu: { loaded: true, gpu_percent: 100, others: ['qwen3:4b-q4_K_M'] } })).toContain('qwen3:4b-q4_K_M')
    expect(speedWarning({ ...base, gpu: { loaded: false } })).toContain('не загружена')
    expect(speedWarning({ ...base, gpu: { loaded: true, gpu_percent: 70 } })).toContain('70%')
    expect(speedWarning({ ...base, llm_available: false })).toBeNull()
  })
})

describe('thinking feed', () => {
  it('streams tokens, resets them and keeps the final answer', () => {
    let turn: Turn = { id: 't', user: 'q', events: [], live: '', running: true }
    turn = applyEvent(turn, { type: 'token', text: 'Hel' })
    turn = applyEvent(turn, { type: 'token', text: 'lo' })
    expect(turn.live).toBe('Hello')
    expect(turn.events).toHaveLength(0)
    turn = applyEvent(turn, { type: 'token_reset', reason: 'regenerate' })
    expect(turn.live).toBe('')
    turn = applyEvent(turn, { type: 'done', total_ms: 5 })
    expect(turn.running).toBe(false)
  })
  it('says who chose the tool and flags foreign numbers', () => {
    expect(feedLine({ type: 'tool_call', name: 'estimate_methane', by: 'llm' })?.title).toBe('Расчёт метана и биогаза · выбрал ИИ')
    expect(feedLine({ type: 'tool_call', name: 'estimate_methane', by: 'python' })?.title).toContain('выбрал Python')
    const bad = feedLine({ type: 'verification', ok: false, unknown_numbers: [11], attempt: 1 })
    expect(bad?.tone).toBe('warn')
    expect(bad?.title).toContain('11')
    expect(feedLine({ type: 'token', text: 'x' })).toBeNull()
  })
})

describe('AgentChat page', () => {
  it('restores an earlier dialog with its number cards after a reload', async () => {
    localStorage.setItem('bioreactor-agent-v10-conversation', 'saved-conversation')
    const fetchMock = stubServer()
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => url.startsWith('/api/agent/conversations/')
      ? { ok: true, status: 200, json: async () => ({ id: 'saved-conversation', exists: true, facts: FACTS, last_answer: null, messages: [
          { role: 'user', content: 'Сколько газа из 200 л?' },
          { role: 'assistant', content: 'Около 4.9 м³ биогаза.', numbers: ANSWER.numbers, question: null, verified: true, mode: 'llm' }] }) }
      : base(url, init))
    render(<AgentChat />)
    expect(await screen.findByText('Около 4.9 м³ биогаза.')).toBeInTheDocument()
    expect(screen.getByText('2.9–5.2')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(call => call[0] === '/api/agent/conversations/saved-conversation')).toBe(true)
  })

  it('sends a question and shows the feed, number cards, question and facts', async () => {
    localStorage.clear()
    const fetchMock = stubServer()
    render(<AgentChat />)
    fireEvent.click(screen.getByRole('button', { name: 'У меня 200 литров коровьего навоза, сколько будет газа?' }))
    expect(await screen.findByText('Из 200 литров получится около 4.9 м³ биогаза.')).toBeInTheDocument()
    expect(screen.getByText('2.9–5.2')).toBeInTheDocument()
    expect(screen.getByText('❓ Какой объём у реактора?')).toBeInTheDocument()
    expect(screen.getByText('Числа сверены с расчётами')).toBeInTheDocument()
    expect(screen.getByText('навоз КРС: 200 л, жидкий')).toBeInTheDocument()
    const chatCall = fetchMock.mock.calls.find(call => call[0] === '/api/agent/chat')!
    expect(JSON.parse((chatCall[1] as RequestInit).body as string)).toMatchObject({ message: 'У меня 200 литров коровьего навоза, сколько будет газа?', use_llm: true })
    // Farmer view: the feed is folded; jury view shows every step with details.
    expect(screen.getByText(/Как агент получил ответ/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Режим жюри/ }))
    expect(screen.getByText('Расчёт метана и биогаза · выбрал ИИ')).toBeVisible()
    expect(screen.getByText('Сырые данные инструментов (JSON)')).toBeInTheDocument()
    expect(screen.getByText(/промпт ≤ 1500 ток/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Как агент получает ответ' })).toBeInTheDocument()
  })

  it('sends use_llm=false in the no-LLM mode and shows demo defaults for unknown facts', async () => {
    localStorage.clear()
    const fetchMock = stubServer()
    render(<AgentChat />)
    expect(await screen.findByText('не указано → 200 л')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Без ИИ-модели'))
    fireEvent.change(screen.getByLabelText('Сообщение агенту'), { target: { value: 'Сколько газа?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(call => call[0] === '/api/agent/chat')).toBe(true))
    const chatCall = fetchMock.mock.calls.find(call => call[0] === '/api/agent/chat')!
    expect(JSON.parse((chatCall[1] as RequestInit).body as string).use_llm).toBe(false)
  })

  it('runs a jury scenario: new dialog, then the messages in order in the same conversation', async () => {
    localStorage.clear()
    const fetchMock = stubServer()
    render(<AgentChat />)
    fireEvent.click(screen.getByRole('button', { name: /Режим жюри/ }))
    fireEvent.click(screen.getByRole('button', { name: /Сколько газа из вёдер/ }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(call => call[0] === '/api/agent/chat')).toHaveLength(2))
    const bodies = fetchMock.mock.calls.filter(call => call[0] === '/api/agent/chat').map(call => JSON.parse((call[1] as RequestInit).body as string))
    expect(bodies.map(b => b.message)).toEqual(['У меня 5 вёдер коровьего навоза, сколько будет газа?', 'Жидкий.'])
    expect(bodies[0].conversation_id).toBe(bodies[1].conversation_id)
    expect(fetchMock.mock.calls.some(call => call[0] === '/api/agent/reset')).toBe(true)
  })
})


describe('pluralRu', () => {
  it('declines «расчёт» by the number', () => {
    const forms: [string, string, string] = ['расчёт', 'расчёта', 'расчётов']
    expect([1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111].map(n => `${n} ${pluralRu(n, forms)}`)).toEqual([
      '1 расчёт', '2 расчёта', '4 расчёта', '5 расчётов', '11 расчётов', '12 расчётов', '14 расчётов',
      '21 расчёт', '22 расчёта', '25 расчётов', '101 расчёт', '111 расчётов',
    ])
  })
})
