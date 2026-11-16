/**
 * Interface language RU / ҚАЗ / EN.
 *
 * Every visible string lives in ru.json, kk.json and en.json (flat keys "file.n"); code calls tr("key").
 * tr() reads the current language from this module, so it also works outside components. The provider keeps the
 * language in React state: the shell (Workspace) uses useI18n(), so a switch re-renders the whole page at once,
 * without a reload and without losing what the user typed.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import en from './en.json'
import kk from './kk.json'
import ru from './ru.json'

export type Lang = 'ru' | 'kk' | 'en'
export const LANGS: Lang[] = ['ru', 'kk', 'en']
// Self-names of the languages: the same in every interface language, so they are not in the dictionaries.
export const LANG_LABELS: Record<Lang, string> = { ru: 'RU', kk: 'ҚАЗ', en: 'EN' }
const DICTS: Record<Lang, Record<string, string>> = { ru, kk, en }
const STORAGE_KEY = 'bioreactor.language'

function stored(): Lang {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'kk' || value === 'en' || value === 'ru' ? value : 'ru'
  } catch {
    return 'ru'  // private window or blocked storage: Russian
  }
}

let current: Lang = typeof window === 'undefined' ? 'ru' : stored()

export function getLang(): Lang {
  return current
}

/** Text of a key in the current language; {name} placeholders are filled from vars. Russian if a key is missing. */
export function tr(key: string, vars?: Record<string, unknown>): string {
  const text = DICTS[current][key] ?? DICTS.ru[key] ?? key
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name] ?? '') : whole))
}

/** Label of a list option that the server sends in Russian (catalog units, states, animals…), by its code. */
export function optionLabel(group: string, value: string, fallback: string): string {
  const key = `catalog.${group}.${value}`
  return key in DICTS.ru ? tr(key) : fallback
}

/**
 * A fixed Russian notice sent by the server (reactor contract, evaluation notice…). Translated only while the server
 * text is exactly the known one (ru.json[key]); a changed server text is shown as it is, never a stale translation.
 */
export function serverText(text: string | null | undefined, key: string): string {
  if (!text) return ''
  return DICTS.ru[key] === text ? tr(key) : text
}

/** A name the server already sends in three languages: {ru, en, kk}. */
export function materialName(name: Partial<Record<Lang, string>> | string | undefined | null): string {
  if (!name) return ''
  return typeof name === 'string' ? name : name[current] ?? name.ru ?? Object.values(name)[0] ?? ''
}

/** Locale for numbers and dates in the current language. */
export function locale(): string {
  return { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' }[current]
}

/**
 * A module-level object or array with translated strings (menu items, label tables). The value is built again when
 * the language changes (cached per language), so code keeps using it like a plain constant: LABELS[key], pages.map().
 */
export function localized<T extends object>(build: () => T): T {
  const cache: Partial<Record<Lang, T>> = {}
  const value = () => (cache[current] ??= build())
  const first = build() as object
  return new Proxy(first, {
    get: (_target, prop) => {
      const target = value() as Record<PropertyKey, unknown>
      const item = Reflect.get(target, prop)
      return typeof item === 'function' && Array.isArray(target) ? (item as (...args: unknown[]) => unknown).bind(target) : item
    },
    has: (_target, prop) => Reflect.has(value(), prop),
    ownKeys: () => Reflect.ownKeys(value()),
    getOwnPropertyDescriptor: (target, prop) => {
      const descriptor = Reflect.getOwnPropertyDescriptor(value(), prop)
      if (!descriptor) return undefined
      // Proxy rule: a non-configurable property of the target (array "length") must stay non-configurable.
      const own = Reflect.getOwnPropertyDescriptor(target, prop)
      return { ...descriptor, configurable: own ? own.configurable : true }
    },
  }) as T
}

type I18n ={ lang: Lang; setLang: (lang: Lang) => void; tr: typeof tr }
const Context = createContext<I18n>({ lang: 'ru', setLang: () => undefined, tr })

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>(current)
  const setLang = useCallback((next: Lang) => {
    current = next
    try { window.localStorage.setItem(STORAGE_KEY, next) } catch { /* the choice just is not remembered */ }
    document.documentElement.lang = next
    setState(next)
  }, [])
  const value = useMemo(() => ({ lang, setLang, tr }), [lang, setLang])
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useI18n(): I18n {
  return useContext(Context)
}

/** For tests: switch the language without the provider. */
export function setLangForTests(lang: Lang) {
  current = lang
}
