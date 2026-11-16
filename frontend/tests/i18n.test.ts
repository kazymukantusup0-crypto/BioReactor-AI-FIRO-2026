// Interface translations RU / ҚАЗ / EN: no missing keys, no Cyrillic in en.json, no untranslated strings left in the
// code, no tr() at module level (scripts/i18n-check.mjs), and the language switch works without a reload.
import { describe, expect, it } from 'vitest'
// @ts-expect-error — a plain .mjs script shared with the command line
import { check } from '../scripts/i18n-check.mjs'
import { getLang, localized, setLangForTests, tr } from '../src/i18n'

describe('translations', () => {
  it('have every key in ru/kk/en, no Cyrillic in English and no string left in the code', () => {
    expect(check('.')).toEqual([])
  })

  it('switch the language of tr() and of localized tables at once', () => {
    const table = localized(() => ({ title: tr('app.1') }))
    const list = localized(() => [tr('app.1'), tr('app.4')])
    try {
      setLangForTests('ru')
      expect(table.title).toBe('Обзор')
      setLangForTests('kk')
      expect(table.title).toBe('Шолу')
      expect(list.map(item => item)).toEqual(['Шолу', 'Реактор'])
      setLangForTests('en')
      expect(tr('app.1')).toBe('Overview')
      expect(Object.keys(table)).toEqual(['title'])
      expect(list.length).toBe(2)
    } finally {
      setLangForTests('ru')
    }
    expect(getLang()).toBe('ru')
  })

  it('fills placeholders', () => {
    expect(tr('agentChat.13', { v0: 2, v1: 'x' })).toBe('Шаг 2: модель решила — x')
  })
})
