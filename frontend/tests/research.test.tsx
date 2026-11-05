import { render,screen } from '@testing-library/react'
import { describe,it,expect,vi } from 'vitest'
import ConversationReply from '../src/ConversationReply'
import { api } from '../src/api'
import type { AgentReply } from '../src/types'
describe('Research v7 presentation',()=>{
 it.each(['MEASURED','LITERATURE_ESTIMATE','HYPOTHETICAL_SCENARIO'])('shows explicit result basis %s',basis=>{
  const reply:AgentReply={conversation_version:'7',mode:'deterministic_tools_no_llm',answer:'TEST estimate',tools:[],missing:[],provider_status:[],user_facing_answer:{paragraphs:['TEST estimate'],question:null,sources:[],assumptions:[],modes:[basis]}}
  render(<ConversationReply reply={reply}/>);expect(screen.getByText(basis)).toBeVisible()
 })
 it('requests opt-in v7 and leaves region unconfirmed',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({id:'TEST'})));vi.stubGlobal('fetch',fetch)
  await api.newSession('no_llm','7');const body=JSON.parse(fetch.mock.calls[0][1].body)
  expect(body.conversation_version).toBe('7');expect(body.context).toEqual({})
 })
})
