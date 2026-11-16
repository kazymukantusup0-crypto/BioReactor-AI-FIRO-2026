import { createContext, useContext, useState, type ReactNode } from 'react'
import { tr } from './i18n'
export type DisplayMode = 'simple' | 'scientific' | 'legacy'
const Context = createContext<{ mode: DisplayMode; setMode: (mode: DisplayMode) => void }>({ mode: 'legacy', setMode: () => {} })
export const useDisplayMode = () => useContext(Context)
export function DisplayModeProvider({ children }: { children: ReactNode }) {
  const [mode, set] = useState<DisplayMode>(() => { try { return localStorage.getItem('bioreactor-display-mode') === 'scientific' ? 'scientific' : 'simple' } catch { return 'simple' } })
  const setMode = (next: DisplayMode) => { set(next); try { localStorage.setItem('bioreactor-display-mode', next) } catch { /* display preference is optional */ } }
  return <Context.Provider value={{ mode, setMode }}>{children}</Context.Provider>
}
export function DisplayModeToggle() {
  const { mode, setMode } = useDisplayMode()
  return <div className="display-mode" role="group" aria-label={tr('displayMode.1')}><button aria-pressed={mode !== 'scientific'} onClick={() => setMode('simple')}>{tr('displayMode.2')}</button><button aria-pressed={mode === 'scientific'} onClick={() => setMode('scientific')}>{tr('displayMode.3')}</button></div>
}
