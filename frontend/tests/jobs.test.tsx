// Execution fixtures only; no scientific values or market prices are invented.
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { api, CHAT_SESSION_KEY } from '../src/api'
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
  expect(acknowledge).toHaveBeenCalledWith('TEST_JOB')
  expect(submit).not.toHaveBeenCalled()
})

it('reuses the original request id when recovering an interrupted delivery',async () => {
  localStorage.setItem('bioreactor-pending-delivery:TEST_SESSION',JSON.stringify({requestId:'TEST_REQUEST',message:'TEST question',expectedVersion:0}))
  const submit=vi.spyOn(api,'submitJob').mockResolvedValue(job)
  vi.spyOn(api,'session').mockResolvedValue(snapshot)
  vi.spyOn(api,'sessionJobs').mockResolvedValue({jobs:[job]})
  const {result}=renderHook(useChatSession)
  await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1))
  expect(submit).toHaveBeenCalledWith('TEST_SESSION','TEST question','TEST_REQUEST',0)
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
