import { LANG_LABELS, LANGS, tr, useI18n } from './i18n'

/** Three-position slider RU | ҚАЗ | EN in the header; the choice is remembered (localStorage) and applies at once. */
export function LanguageSwitch() {
  const { lang, setLang } = useI18n()
  const index = LANGS.indexOf(lang)
  const move = (step: number) => setLang(LANGS[(index + step + LANGS.length) % LANGS.length])
  return <div className="language-switch" role="radiogroup" aria-label={tr('language.switch')}
    onKeyDown={event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') { event.preventDefault(); move(1) }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') { event.preventDefault(); move(-1) }
    }}>
    <span className="language-thumb" style={{ transform: `translateX(${index * 100}%)` }} aria-hidden="true" />
    {LANGS.map(code => <button key={code} type="button" role="radio" aria-checked={code === lang} tabIndex={code === lang ? 0 : -1}
      lang={code} title={tr(`language.${code}`)} data-testid={`lang-${code}`} onClick={() => setLang(code)}>{LANG_LABELS[code]}</button>)}
  </div>
}
