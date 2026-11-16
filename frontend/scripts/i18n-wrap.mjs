// One-time tool (kept for the record): a module-level constant that contains tr('key') would be translated only once,
// at import time. This wraps its initializer: const LABELS = localized(() => ({...})) — rebuilt when the language changes.
//   node scripts/i18n-wrap.mjs src/App.tsx ...
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const hasTr = node => {
  let found = false
  const visit = n => {
    if (found) return
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'tr') { found = true; return }
    if (ts.isFunctionLike(n)) return  // already lazy
    ts.forEachChild(n, visit)
  }
  visit(node)
  return found
}

for (const file of process.argv.slice(2)) {
  const source = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const edits = []
  for (const statement of sf.statements) {
    if (!ts.isVariableStatement(statement)) {
      if (hasTr(statement)) console.log(`${file}:${sf.getLineAndCharacterOfPosition(statement.getStart()).line + 1} MANUAL: ${statement.getText().slice(0, 70)}`)
      continue
    }
    for (const declaration of statement.declarationList.declarations) {
      const init = declaration.initializer
      if (!init || !hasTr(init)) continue
      let inner = init
      while (ts.isAsExpression(inner) || ts.isSatisfiesExpression?.(inner) || ts.isParenthesizedExpression(inner)) inner = inner.expression
      if (!ts.isObjectLiteralExpression(inner) && !ts.isArrayLiteralExpression(inner)) {
        console.log(`${file}:${sf.getLineAndCharacterOfPosition(init.getStart()).line + 1} MANUAL (not an object/array): ${declaration.name.getText()}`)
        continue
      }
      edits.push({ start: init.getStart(), end: init.getEnd(), text: `localized(() => (${init.getText()}))` })
    }
  }
  if (!edits.length) continue
  let output = source
  for (const edit of edits.sort((a, b) => b.start - a.start)) output = output.slice(0, edit.start) + edit.text + output.slice(edit.end)
  output = output.replace(/import \{ tr \} from '([^']*i18n)'/, "import { localized, tr } from '$1'")
  fs.writeFileSync(file, output)
  console.log(`${file}: wrapped ${edits.length}`)
}
