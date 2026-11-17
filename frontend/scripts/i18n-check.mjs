// Translation check (also run as a vitest test, tests/i18n.test.ts):
//  1. every key of ru.json exists in kk.json and en.json and is not empty, no extra keys;
//  2. en.json has no Cyrillic, kk.json is not a copy of the Russian text (except names, units, numbers);
//  3. every tr('key') in the code exists in ru.json;
//  4. no Cyrillic string is left in the translated files, and no tr() runs at module level (it would freeze the
//     language at import time).
//
//   node scripts/i18n-check.mjs        -> prints problems, exit code 1 if any
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import { pathToFileURL } from 'node:url'

export const TRANSLATED_FILES = [
  'src/App.tsx', 'src/ui.tsx', 'src/DisplayMode.tsx', 'src/api.ts', 'src/hooks.ts', 'src/pages/Overview.tsx',
  'src/pages/SubstrateAdvisorV81.tsx', 'src/ScenarioControls.tsx', 'src/FunctionalResults.tsx', 'src/CompactAdvisorResults.tsx',
  'src/AdvisorResults.tsx', 'src/MaterialPropertiesFields.tsx', 'src/advisorApi.ts', 'src/pages/AgentChat.tsx', 'src/agentV10.ts',
  'src/pages/Reactor.tsx', 'src/pages/Market.tsx', 'src/MarketChart.tsx', 'src/pages/Science.tsx', 'src/pages/System.tsx',
  'src/pages/Demo.tsx', 'src/pages/FiroDemoMvp.tsx', 'src/firoDemo.ts', 'src/demoScenarios.ts', 'src/LanguageSwitch.tsx',
  'src/pages/FarmerCalculator.tsx', 'src/substratesApi.ts',
]
// Example questions that show the agent understands Kazakh: they stay in Kazakh in every interface language.
const KEEP_KAZAKH = new Set(['agentChat.5', 'scenario.kazakh.message.1'])
const CYR = /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/
// International words written the same in Kazakh and Russian (checked by hand, docs/kk_terms_review.md).
const LOANWORDS = new Set(['экономика', 'когенерация', 'дигестат', 'температура', 'датчик', 'агент', 'оператор', 'диалог',
  'режим', 'сценарий', 'демо-партия', 'демо-реактор', 'файл', 'промпт', 'ток', 'с', 'мл', 'г', 'л', 'реактор',
  'диагностика', 'биометан', 'компост', 'карбамид', 'аммофос', 'алматы', 'тариф', 'метан'])
const KAZAKH_LETTERS = /[әғқңөұүһі]/i
// Strings that may stay the same in Kazakh as in Russian: units, abbreviations, names, formulas, numbers.
const SAME_OK = /^[\s\d.,:;·×÷=+−–—\-/()%°≈~<>|«»"'?!A-Za-z₀-₉³²µ]*$|^(?:л|кг|т|м³|кВт·ч|°C|КРС|МРС|pH|CH₄|ч|сут|мм|см)$/

export function check(root = '.') {
  const read = lang => JSON.parse(fs.readFileSync(path.join(root, 'src/i18n', `${lang}.json`), 'utf8'))
  const ru = read('ru'), kk = read('kk'), en = read('en')
  const problems = []
  for (const [name, dict] of [['kk', kk], ['en', en]]) {
    for (const key of Object.keys(ru)) if (!(key in dict) || !String(dict[key]).trim()) problems.push(`${name}.json: no key ${key}`)
    for (const key of Object.keys(dict)) if (!(key in ru)) problems.push(`${name}.json: extra key ${key}`)
  }
  for (const [key, value] of Object.entries(en)) {
    if (CYR.test(value) && !KEEP_KAZAKH.has(key)) problems.push(`en.json: Cyrillic in ${key}: ${value}`)
  }
  for (const [key, value] of Object.entries(kk)) {
    const words = value.toLowerCase().match(/[а-яёәғқңөұүһі-]+/g) ?? []
    const loanwordsOnly = words.every(word => LOANWORDS.has(word))
    if (value === ru[key] && !SAME_OK.test(value) && !KAZAKH_LETTERS.test(value) && !loanwordsOnly) {
      problems.push(`kk.json: same as Russian in ${key}: ${value}`)
    }
  }
  for (const file of TRANSLATED_FILES) {
    const full = path.join(root, file)
    if (!fs.existsSync(full)) continue
    const source = fs.readFileSync(full, 'utf8')
    const sf = ts.createSourceFile(full, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const where = node => `${file}:${sf.getLineAndCharacterOfPosition(node.getStart()).line + 1}`
    const visit = node => {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'tr') {
        const first = node.arguments[0]
        if (first && ts.isStringLiteral(first) && !(first.text in ru)) problems.push(`${where(node)}: unknown key ${first.text}`)
        let inside = false
        for (let p = node.parent; p; p = p.parent) if (ts.isFunctionLike(p)) { inside = true; break }
        if (!inside) problems.push(`${where(node)}: tr() at module level`)
      }
      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) && CYR.test(node.text)) {
        problems.push(`${where(node)}: Cyrillic left in code: ${node.text.trim().slice(0, 60)}`)
      }
      if (ts.isTemplateExpression(node) && [node.head, ...node.templateSpans.map(s => s.literal)].some(p => CYR.test(p.text))) {
        problems.push(`${where(node)}: Cyrillic left in a template`)
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
  return problems
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const problems = check()
  console.log(problems.join('\n') || 'i18n: OK')
  console.log(`${problems.length} problems`)
  process.exit(problems.length ? 1 : 0)
}
