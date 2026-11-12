// Execution fixtures only; no scientific values or market prices are invented.
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { api, ApiError, CHAT_SESSION_KEY } from '../src/api'
import { useChatSession } from '../src/useChatSession'
import type { AgentJob, AgentReply, ConversationMemory, Session } from '../src/types'

const memory: ConversationMemory={version:'7',conversation_id:'TEST_SESSION',language:'ru',facts:{},assumptions:{},derived:{},estimates:{},source_verified:{},intents:[],pending_question:null,invalidated:[]}
const snapshot: Session={id:'TEST_SESSION',mode:'no_llm',context:{},turns:[{id:1,question:'TEST question',created_at:'2026-01-01T00:00:00Z',request_id:'TEST_REQUEST',status:'queued',reply:null}],memory,conversation_version:'7',state_version:0}
const job: AgentJob={id:'TEST_JOB',request_id:'TEST_REQUEST',conversation_id:'TEST_SESSION',task_id:'TEST_TASK',status:'RUNNING',current_stage:'understanding',terminal:false,attempt_count:1,error_code:null,result_reference:'/TEST_RESULT',result_available:false,partial_count:0,preview:memory,heartbeat_at:new Date().toISOString(),updated_at:new Date().toISOString(),acknowledged_at:null,cancel_requested:0}
const reply: AgentReply={conversation_version:'7',mode:'TEST_FIXTURE',answer:'TEST durable result',tools:[],missing:[],provider_status:[],memory}

beforeEach(() => {localStorage.clear();localStorage.setItem(CHAT_SESSION_KEY,'TEST_SESSION')})

it('restores execution after remount and automatically receives and acknowledges its result',async () => {
  let completed=false
  vi.spyOn(api,'session').mockImplementation(async () => ({...snapshot,state_version:completed?1:0,turns:snapshot.turns.map(t=>({...t,reply:completed?reply:null}))}))
  vi.spyOn(api,'sessionJobs').mockImplementation(async () => ({jobs:[{...job,status:completed?'COMPLETED':'RUNNING',terminal:completed,result_available:completed}]}))
  const submit=vi.spyOn(api,'submitJob')
  vi.spyOn(api,'jobResult').mockResolvedValue({id:job.id,status:'COMPLETED',terminal:true,reply,error_code:null,partial_results:[]})
  const acknowledge=vi.spyOn(api,'acknowledgeJob').mockResolvedValue({...job,status:'COMPLETED',terminal:true})
  const first=renderHook(useChatSession)
  await waitFor(()=>expect(first.result.current.busy).toBe(true))
  first.unmount();completed=true
  const restored=renderHook(useChatSession)
  await waitFor(()=>expect(restored.result.current.turns[0]?.reply?.answer).toBe('TEST durable result'))
  expect(restored.result.current.busy).toBe(false)
  await waitFor(()=>expect(acknowledge).toHaveBeenCalledWith('TEST_JOB',expect.any(AbortSignal)))
  expect(submit).not.toHaveBeenCalled()
})

it('reuses the original request id when recovering an interrupted delivery',async () => {
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',JSON.stringify({requestId:'TEST_REQUEST',message:'TEST question',expectedVersion:0}))
  const submit=vi.spyOn(api,'submitJob').mockResolvedValue(job)
  vi.spyOn(api,'session').mockResolvedValue(snapshot)
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[]})
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1))
  expect(submit).toHaveBeenCalledWith('TEST_SESSION','TEST question','TEST_REQUEST',0,expect.any(AbortSignal))
  await waitFor(()=>expect(result.current.active?.id).toBe('TEST_JOB'))
  expect(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')).toBeNull()
})

it('ignores a late response from a different conversation',async () => {
  let resolveOld:(value:Session)=>void=()=>{}
  const old=new Promise<Session>(resolve=>{resolveOld=resolve})
  vi.spyOn(api,'session').mockImplementation(async id => id==='TEST_SESSION'?old:{...snapshot,id:'TEST_NEW',state_version:7})
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[]})
  vi.spyOn(api,'newSession').mockResolvedValue({...snapshot,id:'TEST_NEW',turns:[],state_version:7})
  const {result}=renderHook(useChatSession)
  await act(async()=>{await result.current.newSession('no_llm')})
  await waitFor(()=>expect(result.current.session?.id).toBe('TEST_NEW'))
  await act(async()=>{resolveOld(snapshot);await Promise.resolve()})
  expect(result.current.session?.id).toBe('TEST_NEW')
  expect(result.current.session?.state_version).toBe(7)
})

it.each(['{broken JSON', JSON.stringify({requestId:'TEST_BAD_SCHEMA',message:42})])('recovers a corrupt outbox without blocking history or submitting forever: %s',async saved => {
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',saved)
  const submit=vi.spyOn(api,'submitJob')
  vi.spyOn(api,'session').mockResolvedValue({...snapshot,turns:[{...snapshot.turns[0],reply}]})
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[]})
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.turns[0]?.reply?.answer).toBe(reply.answer))
  expect(result.current.busy).toBe(false)
  expect(result.current.error).toMatch(/поврежд|восстанов/i)
  expect(submit).not.toHaveBeenCalled()
})

it.each(['result','ack'])('an old terminal %s failure does not hide available history or the current job',async failing => {
  const terminal={...job,id:'TEST_OLD',request_id:'TEST_OLD_REQUEST',status:'COMPLETED',terminal:true}
  vi.spyOn(api,'session').mockResolvedValue({...snapshot,turns:[{...snapshot.turns[0],reply}]})
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[terminal,job]})
  vi.spyOn(api,'jobResult').mockImplementation(async()=>{if(failing==='result')throw new ApiError('TEST old result unavailable',404);return {id:terminal.id,status:'COMPLETED',terminal:true,reply,error_code:null,partial_results:[]}})
  vi.spyOn(api,'acknowledgeJob').mockRejectedValue(new ApiError('TEST acknowledgement unavailable',503))
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.turns[0]?.reply?.answer).toBe(reply.answer))
  expect(result.current.active?.id).toBe(job.id)
})

it.each([408,429])('keeps retryable HTTP %s delivery with its original UUID and message',async status => {
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',JSON.stringify({requestId:'TEST_REQUEST',message:'TEST retained text',expectedVersion:0}))
  vi.spyOn(api,'submitJob').mockRejectedValue(new ApiError('TEST transient delivery failure',status))
  vi.spyOn(api,'session').mockResolvedValue(snapshot)
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[]})
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.error).not.toBe(''))
  expect(JSON.parse(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')!)).toMatchObject({requestId:'TEST_REQUEST',message:'TEST retained text'})
})

it('uses the session snapshot jobs rather than mixing two logical snapshots',async () => {
  vi.spyOn(api,'session').mockResolvedValue({...snapshot,state_version:7,jobs:[job]} as Session)
  const separate=vi.spyOn(api,'sessionJobs').mockRejectedValue(new Error('TEST separate snapshot must not be requested'))
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.session?.state_version).toBe(7))
  expect(result.current.active?.id).toBe(job.id)
  expect(separate).not.toHaveBeenCalled()
})

it('ignores a late submission after another tab switches the conversation',async () => {
  const raw=JSON.stringify({requestId:'TEST_REQUEST',message:'TEST pending text',expectedVersion:0})
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',raw)
  let resolveSubmit:(value:AgentJob)=>void=()=>{}
  const submit=vi.spyOn(api,'submitJob').mockImplementation(()=>new Promise(resolve=>{resolveSubmit=resolve}))
  vi.spyOn(api,'session').mockImplementation(async id=>({...snapshot,id,jobs:[],turns:[]}))
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1))
  await act(async()=>{
    localStorage.setItem(CHAT_SESSION_KEY,'TEST_NEW')
    window.dispatchEvent(new StorageEvent('storage',{key:CHAT_SESSION_KEY,newValue:'TEST_NEW'}))
  })
  await waitFor(()=>expect(result.current.session?.id).toBe('TEST_NEW'))
  await act(async()=>{resolveSubmit(job);await Promise.resolve()})
  expect(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')).toBe(raw)
  expect(submit.mock.calls[0][4]?.aborted).toBe(true)
  expect(result.current.active).toBeUndefined()
  expect(result.current.busy).toBe(false)
})

it('does not select a late newly created session over a different tab selection',async () => {
  let resolveNew:(value:Session)=>void=()=>{}
  vi.spyOn(api,'newSession').mockImplementation(()=>new Promise(resolve=>{resolveNew=resolve}))
  vi.spyOn(api,'session').mockImplementation(async id=>({...snapshot,id,jobs:[],turns:[]}))
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.loading).toBe(false))
  let pending:Promise<void>
  act(()=>{pending=result.current.newSession('no_llm')})
  await act(async()=>{
    localStorage.setItem(CHAT_SESSION_KEY,'TEST_SELECTED')
    window.dispatchEvent(new StorageEvent('storage',{key:CHAT_SESSION_KEY,newValue:'TEST_SELECTED'}))
  })
  await waitFor(()=>expect(result.current.session?.id).toBe('TEST_SELECTED'))
  await act(async()=>{resolveNew({...snapshot,id:'TEST_LATE_NEW'});await pending!})
  expect(localStorage.getItem(CHAT_SESSION_KEY)).toBe('TEST_SELECTED')
  expect(result.current.session?.id).toBe('TEST_SELECTED')
})

it('archives rejected delivery and restores editable text while keeping history readable',async () => {
  const raw=JSON.stringify({requestId:'TEST_REQUEST',message:'TEST version conflict',expectedVersion:0})
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',raw)
  vi.spyOn(api,'submitJob').mockRejectedValue(new ApiError('TEST stale scientific version',409))
  vi.spyOn(api,'session').mockResolvedValue({...snapshot,state_version:2,jobs:[],turns:[]})
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(result.current.rejectedMessage).toBe('TEST version conflict'))
  expect(result.current.session?.state_version).toBe(2)
  expect(result.current.busy).toBe(false)
  expect(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')).toBeNull()
  expect(Object.keys(localStorage).some(key=>key.includes(':rejected:')&&localStorage.getItem(key)===raw)).toBe(true)
})

it('bounds automatic delivery retries while polling history and preserving original input',async () => {
  vi.useFakeTimers()
  try {
    const raw=JSON.stringify({requestId:'TEST_REQUEST',message:'TEST retained retry text',expectedVersion:0})
    localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',raw)
    const submit=vi.spyOn(api,'submitJob').mockRejectedValue(new ApiError('TEST offline'))
    const read=vi.spyOn(api,'session').mockResolvedValue({...snapshot,jobs:[],turns:[]})
    const {result}=renderHook(useChatSession)
    await act(async()=>{await vi.advanceTimersByTimeAsync(60000)})
    expect(submit).toHaveBeenCalledTimes(5)
    expect(read.mock.calls.length).toBeGreaterThan(5)
    expect(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')).toBe(raw)
    expect(result.current.error).toContain('5 попыток')
    await act(async()=>{result.current.reload();await Promise.resolve()})
    expect(submit).toHaveBeenCalledTimes(6)
    expect(submit.mock.calls.every(call=>call[2]==='TEST_REQUEST')).toBe(true)
  } finally {vi.useRealTimers()}
})

it('discovers an accepted job after its POST response was lost without resubmitting',async () => {
  vi.useFakeTimers()
  try {
    let accepted=false
    localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',JSON.stringify({requestId:'TEST_REQUEST',message:'TEST question',expectedVersion:0}))
    const submit=vi.spyOn(api,'submitJob').mockImplementation(async()=>{accepted=true;throw new ApiError('TEST lost response')})
    vi.spyOn(api,'session').mockImplementation(async()=>({...snapshot,jobs:accepted?[job]:[]}))
    const {result}=renderHook(useChatSession)
    await act(async()=>{await vi.advanceTimersByTimeAsync(1500)})
    expect(submit).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('bioreactor-pending-delivery:TEST_SESSION')).toBeNull()
    expect(result.current.active?.id).toBe(job.id)
  } finally {vi.useRealTimers()}
})
