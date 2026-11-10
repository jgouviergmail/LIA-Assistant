/** Read icon import bindings structurally, including aliases and mixed type imports. */
import { createRequire } from 'node:module';

const require = createRequire(new URL('../../apps/web/package.json', import.meta.url));
const ts = require('typescript');

export function readIconImports(source, fileName) {
  const ast = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest);
  const imports = [];
  for (const statement of ast.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    const module = statement.moduleSpecifier.text;
    if (!['lucide-react', '@/lib/icons'].includes(module)) continue;
    const clause = statement.importClause;
    if (clause?.isTypeOnly || !clause?.namedBindings) continue;
    if (!ts.isNamedImports(clause.namedBindings)) {
      imports.push({ module, name: '*' });
      continue;
    }
    for (const element of clause.namedBindings.elements) {
      if (!element.isTypeOnly) imports.push({ module, name: (element.propertyName ?? element.name).text });
    }
  }
  return imports;
}

export function assertFacadeImports(imports, fileName) {
  const direct = imports.filter(item => item.module === 'lucide-react');
  if (direct.length) throw new Error(`${fileName}: direct Lucide runtime import bypasses the account style`);
}

/** Formatting may change whitespace, but never artwork, exports or PURE annotations. */
export function sourceTokens(source) {
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, ts.LanguageVariant.Standard, source);
  const tokens = [];
  for (let token = scanner.scan(); token !== ts.SyntaxKind.EndOfFileToken; token = scanner.scan()) {
    if (token !== ts.SyntaxKind.WhitespaceTrivia && token !== ts.SyntaxKind.NewLineTrivia) {
      tokens.push(scanner.getTokenText());
    }
  }
  return JSON.stringify(tokens);
}
