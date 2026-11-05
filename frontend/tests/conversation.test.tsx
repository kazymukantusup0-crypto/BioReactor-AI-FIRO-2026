// Explicit UI fixtures only. No data here is a production measurement/price.
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConversationReply from '../src/ConversationReply'
import ConversationFacts from '../src/ConversationFacts'
import type { AgentReply, ConversationMemory, DialogueFact } from '../src/types'
import { api } from '../src/api'

const fact = (value: string | number, unit: string | null = null, provenance: DialogueFact['provenance'] = 'USER_CONFIRMED'): DialogueFact => ({ value, unit, provenance, evidence: 'FICTITIOUS TEST user statement', recorded_at: '2020-01-01T00:00:00Z', dependencies: [] })
const memory: ConversationMemory = { version: '5.6', conversation_id: 'TEST', language: 'ru', facts: { material: fact('cattle_manure'), quantity: fact(800, 'L'), unit: fact('L') }, assumptions: { density_kg_l: fact(1, 'kg/L', 'ASSUMED_FOR_SCENARIO') }, derived: {}, estimates: {}, source_verified: {}, intents: [], pending_question: null, invalidated: [] }
const reply: AgentReply = { conversation_version: '5.6', mode: 'deterministic_tools_no_llm', answer: 'TEST readable answer', tools: [{ tool: 'analyze_substrate', status: 'ok', result: { status: 'ok', message: 'TEST technical result' } }], missing: ['vs_mass_kg'], provider_status: [], memory,
  technical_metadata: { missing_parameters: ['vs_mass_kg'], validation_errors: [] },
  user_facing_answer: { paragraphs: ['TEST readable scientific explanation'], modes: ['literature_guidance'], assumptions: [], sources: [{ title: 'FICTITIOUS TEST source', url: 'https://example.invalid/TEST' }], question: { id: 'manure_subtype', text: 'Какой навоз?', options: ['Коровий', 'Свиной'], fields: ['material'], reason: 'TEST' } } }

describe('Conversational presentation', () => {
  it('keeps the ordinary answer separate from closed technical diagnostics', () => {
    const { container } = render(<ConversationReply reply={reply} />)
    expect(screen.getByText('TEST readable scientific explanation')).toBeVisible()
    expect(container.querySelector('.conversation-prose')).not.toHaveTextContent('vs_mass_kg')
    expect(container.querySelector('.conversation-technical')).not.toHaveAttribute('open')
    expect(screen.getByText('Литературная справка')).toBeVisible()
  })
  it('sends the selected clarification as a real user reply', () => {
    const onAnswer = vi.fn(); render(<ConversationReply reply={reply} onAnswer={onAnswer} />)
    fireEvent.click(screen.getByRole('button', { name: 'Коровий' }))
    expect(onAnswer).toHaveBeenCalledTimes(1); expect(onAnswer).toHaveBeenCalledWith('Коровий')
  })
  it('blocks clarification submission while the backend is busy', () => {
    render(<ConversationReply reply={reply} onAnswer={vi.fn()} disabled />)
    expect(screen.getByRole('button', { name: 'Коровий' })).toBeDisabled()
  })
  it('shows source attribution from the user-facing backend response', () => {
    render(<ConversationReply reply={reply} />)
    expect(screen.getByRole('link', { name: 'FICTITIOUS TEST source' })).toHaveAttribute('href', 'https://example.invalid/TEST')
  })
  it('does not display scenario assumptions as confirmed measured facts', () => {
    const { container } = render(<ConversationFacts memory={memory} onCorrection={vi.fn()} disabled={false} />)
    expect(screen.getByText('Коровий навоз')).toBeVisible()
    expect(container.querySelector('.assumed-facts')).toHaveTextContent('Плотность')
    expect(container.querySelector('.assumed-facts')).toHaveTextContent('Допущение, не измерение')
    expect(container.querySelector('dl:not(.assumed-facts)')).not.toHaveTextContent('Плотность')
  })
  it('offers an explicit material and quantity correction in the same dialogue', () => {
    const correction = vi.fn(); render(<ConversationFacts memory={memory} onCorrection={correction} disabled={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'Исправить материал и количество' }))
    fireEvent.change(screen.getByLabelText('Исправленный материал'), { target: { value: 'swine_manure' } })
    fireEvent.change(screen.getByLabelText('Исправленное количество'), { target: { value: '600' } })
    fireEvent.click(screen.getByRole('button', { name: 'Применить исправление' }))
    expect(correction).toHaveBeenCalledTimes(1)
    expect(correction.mock.calls[0][0]).toContain('свиной навоз'); expect(correction.mock.calls[0][0]).toContain('600 литров')
  })
  it('requests v5.6 without falsely confirming the default market region', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'TEST' })))
    vi.stubGlobal('fetch', fetch); await api.newSession('no_llm')
    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.conversation_version).toBe('5.6'); expect(body.context).toEqual({})
  })
})
