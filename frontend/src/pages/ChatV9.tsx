import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Bot, Check, LoaderCircle, MessageSquarePlus, ShieldCheck, Sparkles, User } from 'lucide-react'
import { CHAT_ADVISOR_KEY } from '../api'
import { conversationQuestion } from '../decisionDisplay'
import { JsonDetails, LoadState, Notice, PageTitle, Reply, timestamp } from '../ui'
import ConversationReply from '../ConversationReply'
import ConversationFacts from '../ConversationFacts'
import { useChatSession } from '../useChatSession'
import type { Turn } from '../types'

const stages: Record<string,string> = {
  queued:'Запрос сохранён и ожидает выполнения', recovering:'Восстанавливаю анализ после остановки сервера',
  starting:'Начинаю анализ', parameters:'Проверяю параметры текущей задачи', understanding:'Анализирую вопрос',
  planning:'Выбираю необходимые инструменты', tool_start:'Выполняю научный инструмент', tool_result:'Сохраняю результаты вычислений',
  verifying:'Проверяю расчёты', responding:'Формирую ответ', persisted:'Результат сохранён', cancelling:'Останавливаю выполнение',
}

function ExecutionStatus({ turn, cancel }: {turn: Turn; cancel: () => void}) {
  const job=turn.job
  if (job?.terminal || ['failed','cancelled','timed_out','error'].includes(turn.status.toLowerCase())) {
    const label=job?.status==='CANCELLED' ? 'Запрос отменён.' : job?.status==='TIMED_OUT' || turn.status==='timed_out'
      ? 'Время анализа истекло. Доступные промежуточные результаты сохранены.' : 'Анализ завершился ошибкой; предыдущие данные сохранены.'
    return <div data-testid="job-terminal"><Notice>{label}</Notice><JsonDetails value={turn.execution_result ?? job} title="Диагностика выполнения" /></div>
  }
  const overdue=job?.heartbeat_at && Date.now()-Date.parse(job.heartbeat_at)>45000
  return <div className="generating" role="status" data-testid="job-progress"><LoaderCircle size={16} className="spin" />
    <span>{overdue ? 'Ожидаю восстановления сервера; состояние запроса сохранено.' : stages[job?.current_stage ?? ''] ?? 'Отправляю запрос. Ответ появится автоматически.'}</span>
    {job && <button className="btn btn-secondary" data-testid="cancel-job" disabled={Boolean(job.cancel_requested)} onClick={cancel}>Отменить</button>}
  </div>
}

export default function Chat() {
  const chat=useChatSession()
  const {session,turns,active,busy,loading,error}=chat
  const [text,setText]=useState(() => sessionStorage.getItem('bioreactor_demo_question') ?? '')
  const [mode,setMode]=useState('offline')
  const end=useRef<HTMLDivElement>(null)
  const memory=active ? active.preview ?? undefined : session?.memory ?? undefined
  const transferable=Boolean(memory && (memory.mixture_components?.length || memory.facts.material && (memory.facts.quantity || memory.facts.mass_kg)))
  useEffect(() => { sessionStorage.removeItem('bioreactor_demo_question') },[])
  useEffect(() => { if(chat.rejectedMessage)setText(chat.rejectedMessage) },[chat.rejectedMessage])
  useEffect(() => { if(session) setMode(session.mode) },[session?.id,session?.mode])
  useEffect(() => { end.current?.scrollIntoView({behavior:'smooth',block:'nearest'}) },[turns.length,busy])
  const send=async (override?: string) => { if(await chat.send(override ?? text,mode)) setText('') }
  const openCalculator=() => {
    if(!memory || !transferable || busy)return
    sessionStorage.setItem(CHAT_ADVISOR_KEY,JSON.stringify({...memory,state_version:session?.state_version}))
    window.location.hash='/substrates'
  }
  return <>
    <PageTitle eyebrow="AI RESEARCH ASSISTANT" title="Диалог с системой" description="Вопросы на русском языке. Расчёты выполняет Python; LLM выбирает инструменты."
      action={<button className="btn btn-secondary" disabled={busy || loading} onClick={() => chat.newSession(mode)}><MessageSquarePlus size={16}/>Новый диалог</button>}/>
    <div className="conversation-workspace"><div className="chat-layout">
      <div className="chat-header"><div><span className="status-dot"/><strong>Локальный научный агент</strong><span className="muted">qwen3:8b</span></div>
        <label>Режим<select aria-label="Режим агента" value={mode} disabled={busy || loading} onChange={e => chat.newSession(e.target.value)}>
          <option value="offline">Локальная модель</option><option value="no_llm">Расчёт без языковой модели</option>
        </select></label></div>
      <div className="chat-thread" aria-live="polite" data-testid="chat-thread"><LoadState loading={loading} error={error} retry={chat.reload}/>
        {!loading && turns.length===0 && <div className="chat-welcome"><div className="welcome-icon"><Bot size={33}/></div><span className="eyebrow">SCIENCE, WITH CONTEXT</span>
          <h2>С чего начнём исследование?</h2><p>Опишите сырьё или задайте вопрос о модели.<br/>Если информации недостаточно, агент объяснит, чего не хватает.</p>
          <div className="prompt-grid">{['У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить?',
            'Какие сейчас цены на газ в Караганде?','Какая точность у модели BMP и в чём её ограничения?'].map(prompt =>
            <button key={prompt} onClick={() => setText(prompt)}><Sparkles size={16}/><span>{prompt}</span></button>)}</div>
          <div className="chat-assurance"><ShieldCheck size={15}/>Факты, литературные оценки и допущения разделены</div></div>}
        {turns.map(turn => <div key={turn.request_id} className="chat-turn" data-testid="chat-turn" data-request-id={turn.request_id}>
          <div className="message-user"><span className="avatar user-avatar"><User size={17}/></span><div><div className="message-meta">Вы <time>{timestamp(turn.created_at)}</time></div><p>{conversationQuestion(turn.question)}</p></div></div>
          <div className="message-assistant"><span className="avatar ai-avatar"><Bot size={18}/></span><div className="assistant-content"><div className="message-meta">BioReactor AI</div>
            {turn.reply ? <div data-testid="chat-result">{['5.6','7'].includes(turn.reply.conversation_version ?? '')
              ? <ConversationReply reply={turn.reply} onAnswer={turn===turns[turns.length-1] ? send : undefined} disabled={busy}/>
              : <Reply reply={turn.reply}/>}</div> : <ExecutionStatus turn={turn} cancel={() => { void chat.cancel() }}/>}</div></div>
        </div>)}<div ref={end}/></div>
      <div className="chat-composer"><label className="sr-only" htmlFor="chat-input">Сообщение агенту</label>
        <textarea id="chat-input" data-testid="chat-input" placeholder="Опишите сырьё, задайте вопрос или передайте измерения JSON…" value={text}
          onChange={e => setText(e.target.value)} maxLength={12000} rows={2} disabled={busy}
          onKeyDown={e => { if(e.key==='Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault();void send() } }}/>
        <div className="composer-bottom"><span><Check size={13}/>Локальная обработка</span><button className="send-button" aria-label="Отправить сообщение" data-testid="send-chat"
          disabled={busy || loading || !text.trim()} onClick={() => { void send() }}>{busy ? <LoaderCircle size={18} className="spin"/> : <ArrowUp size={19}/>}</button></div></div>
      <div className="chat-bottom-note"><span>Ответ и состояние выполнения восстанавливаются автоматически</span>
        <button data-testid="open-calculator" onClick={openCalculator} disabled={busy || loading || !transferable}>Открыть в калькуляторе</button></div>
    </div><div data-testid="active-scientific-state">{active && <Notice tone="muted">Распознанные параметры текущего запроса; анализ продолжается.</Notice>}
      <ConversationFacts memory={memory} onCorrection={send} disabled={busy || loading}/></div></div>
  </>
}
