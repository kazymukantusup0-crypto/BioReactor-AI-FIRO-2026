// design-v2: every colour comes from the tokens in design.css :root, so one theme repaints the whole dashboard.
import { describe, expect, it } from 'vitest'

// Files are read from disk (vitest hands CSS ?raw imports over as empty strings). Typed by hand: no @types/node here.
type Fs = { readFileSync(path: string, enc: 'utf8'): string; readdirSync(path: string, opts: { recursive: true }): string[] }
const fs = await import(/* @vite-ignore */ 'node:fs' as string) as Fs
const srcDir = 'src/'  // vitest runs in frontend/
const all = fs.readdirSync(srcDir, { recursive: true }).map(f => f.split('\\').join('/'))
const read = (list: string[]) => Object.fromEntries(list.map(f => [f, fs.readFileSync(srcDir + f, 'utf8')]))
const css = read(all.filter(f => f.endsWith('.css')))
const code = read(all.filter(f => /\.tsx?$/.test(f)))
const COLOUR = /#[0-9a-fA-F]{3,8}\b|rgba?\(/g

describe('design tokens', () => {
  it('finds the source files', () => {
    expect(Object.keys(css).length).toBeGreaterThan(5)
    expect(Object.keys(code).length).toBeGreaterThan(20)
  })
  it('no literal colours in CSS outside the :root token block', () => {
    for (const [file, raw] of Object.entries(css)) {
      const text = file.endsWith('design.css') ? raw.slice(raw.indexOf('}', raw.indexOf(':root')) + 1) : raw
      expect(text.match(COLOUR) ?? [], file).toEqual([])
    }
  })
  it('no literal colours in TS/TSX (charts read tokens via theme.ts)', () => {
    for (const [file, raw] of Object.entries(code)) {
      const text = raw.replace(/\/\/.*$/gm, '')
      expect(text.match(/['"`]#[0-9a-fA-F]{3,8}['"`]|rgba?\(/g) ?? [], file).toEqual([])
    }
  })
  it('status colours are separate tokens: ok / warn / danger / offline', () => {
    const root = Object.entries(css).find(([file]) => file.endsWith('design.css'))![1]
    for (const token of ['--ok:', '--warn:', '--danger:', '--offline:']) expect(root).toContain(token)
  })
})
