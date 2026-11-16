// One-time tool (kept for the record): moves Russian UI strings of the given files into src/i18n/ru.json and
// replaces them with tr('key'). Uses the TypeScript AST, not regexes, so JSX text, JSX attributes, template
// strings and existing text('ru','en','kk') triples are told apart. Prints what needs a manual look:
// module-level strings (evaluated once at import), strings compared in logic, object keys.
//
//   node scripts/i18n-extract.mjs src/App.tsx src/pages/Overview.tsx ...
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const CYR = /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/
const I18N = path.resolve('src/i18n')
const dicts = Object.fromEntries(['ru', 'kk', 'en'].map(lang => {
  const file = path.join(I18N, `${lang}.json`)
  return [lang, fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {}]
}))
const report = []

function prefixOf(file) {
  return path.basename(file).replace(/\.(tsx|ts)$/, '').replace(/^[A-Z]/, c => c.toLowerCase())
}

function insideFunction(node) {
  for (let p = node.parent; p; p = p.parent) if (ts.isFunctionLike(p)) return true
  return false
}

function literalText(node) {
  return node.text
}

for (const file of process.argv.slice(2)) {
  const source = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const prefix = prefixOf(file)
  const byText = new Map(Object.entries(dicts.ru).filter(([k]) => k.startsWith(prefix + '.')).map(([k, v]) => [v, k]))
  let counter = Object.keys(dicts.ru).filter(k => k.startsWith(prefix + '.')).length
  const edits = []

  const keyFor = (ru, en, kk) => {
    if (!en && byText.has(ru)) return byText.get(ru)
    const key = `${prefix}.${++counter}`
    dicts.ru[key] = ru
    if (en) dicts.en[key] = en
    if (kk) dicts.kk[key] = kk
    byText.set(ru, key)
    return key
  }
  const note = (node, why) => report.push(`${file}:${sf.getLineAndCharacterOfPosition(node.getStart()).line + 1} ${why}: ${node.getText().slice(0, 80)}`)

  const visit = node => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) return
    // text('ru', 'en', 'kk') -> tr('key') with all three translations
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'text'
        && node.arguments.length === 3 && node.arguments.every(a => ts.isStringLiteral(a))) {
      const [ru, en, kk] = node.arguments.map(literalText)
      edits.push({ start: node.getStart(), end: node.getEnd(), text: `tr('${keyFor(ru, en, kk)}')` })
      return
    }
    if (ts.isJsxText(node) && CYR.test(node.text)) {
      const raw = node.getFullText()
      const trimmed = raw.trim()
      const lead = raw.indexOf(trimmed)
      const start = node.getFullStart() + lead
      edits.push({ start, end: start + trimmed.length, text: `{tr('${keyFor(trimmed.replace(/\s+/g, ' '))}')}` })
      return
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && CYR.test(node.text)) {
      const parent = node.parent
      if (ts.isPropertyAssignment(parent) && parent.name === node) { note(node, 'OBJECT KEY'); return }
      if (ts.isLiteralTypeNode(parent)) return
      if (ts.isCaseClause(parent)) { note(node, 'CASE'); return }
      if (ts.isBinaryExpression(parent) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken,
        ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(parent.operatorToken.kind)) {
        note(node, 'COMPARED'); return
      }
      if (ts.isNewExpression(parent) && parent.expression.getText() === 'RegExp') { note(node, 'REGEXP'); return }
      const key = keyFor(node.text)
      const jsxAttribute = ts.isJsxAttribute(parent)
      if (!insideFunction(node)) note(node, 'MODULE LEVEL')
      edits.push({ start: node.getStart(), end: node.getEnd(), text: jsxAttribute ? `{tr('${key}')}` : `tr('${key}')` })
      return
    }
    if (ts.isTemplateExpression(node)) {
      const parts = [node.head.text, ...node.templateSpans.map(s => s.literal.text)]
      if (parts.some(p => CYR.test(p))) {
        let ru = node.head.text
        const vars = []
        node.templateSpans.forEach((span, i) => {
          ru += `{v${i}}` + span.literal.text
          vars.push(`v${i}: ${span.expression.getText()}`)
        })
        const key = keyFor(ru)
        if (!insideFunction(node)) note(node, 'MODULE LEVEL')
        const call = `tr('${key}', { ${vars.join(', ')} })`
        edits.push({ start: node.getStart(), end: node.getEnd(), text: ts.isJsxAttribute(node.parent) ? `{${call}}` : call })
        return
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  if (!edits.length) continue
  let output = source
  for (const edit of edits.sort((a, b) => b.start - a.start)) output = output.slice(0, edit.start) + edit.text + output.slice(edit.end)
  let relative = path.relative(path.dirname(path.resolve(file)), I18N).replace(/\\/g, '/')
  if (!relative.startsWith('.')) relative = './' + relative
  if (!/import \{[^}]*\btr\b[^}]*\} from '[^']*i18n'/.test(output)) {
    const imports = [...output.matchAll(/^import .*$/gm)]
    const at = imports.length ? imports[imports.length - 1].index + imports[imports.length - 1][0].length : 0
    output = output.slice(0, at) + `\nimport { tr } from '${relative}'` + output.slice(at)
  }
  fs.writeFileSync(file, output)
  console.log(`${file}: ${edits.length} strings`)
}

for (const lang of ['ru', 'kk', 'en']) {
  fs.writeFileSync(path.join(I18N, `${lang}.json`), JSON.stringify(dicts[lang], null, 1) + '\n')
}
console.log(report.join('\n'))
