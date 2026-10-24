/**
 * Decision points and hook calls of one source file (audit AC-040).
 *
 * What a coverage tool counts as a branch — an `if`, a ternary, a short-circuit
 * (`&&`, `||`, `??`), an optional chain, a `switch` case, a loop, a `catch`, a
 * default value — read from the syntax tree, plus the hooks a component calls.
 * A file with neither has no logic of its own, which is the only reason a file
 * may stay out of the coverage measure (`coverage-exclusions.mjs`).
 */
import ts from 'typescript';

const SHORT_CIRCUITS = new Set([
  ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.BarBarToken,
  ts.SyntaxKind.QuestionQuestionToken,
]);

/**
 * @param {ts.Node} node
 * @returns {string | null} The decision this node is, or null.
 */
function decisionOf(node) {
  if (ts.isIfStatement(node)) return 'if';
  if (ts.isConditionalExpression(node)) return '?:';
  if (ts.isBinaryExpression(node) && SHORT_CIRCUITS.has(node.operatorToken.kind)) {
    return ts.tokenToString(node.operatorToken.kind) ?? 'short-circuit';
  }
  if (ts.isCaseClause(node)) return 'case';
  if (ts.isCatchClause(node)) return 'catch';
  if (ts.isIterationStatement(node, false)) return 'loop';
  if (
    (ts.isPropertyAccessExpression(node) ||
      ts.isElementAccessExpression(node) ||
      ts.isCallExpression(node)) &&
    node.questionDotToken
  ) {
    return '?.';
  }
  if ((ts.isParameter(node) || ts.isBindingElement(node)) && node.initializer) return 'default';
  return null;
}

/**
 * @param {ts.Node} node
 * @returns {string | null} The hook this node calls, or null.
 */
function hookOf(node) {
  if (!ts.isCallExpression(node)) return null;
  const callee = node.expression;
  const name = ts.isIdentifier(callee)
    ? callee.text
    : ts.isPropertyAccessExpression(callee)
      ? callee.name.text
      : '';
  return /^use[A-Z]/.test(name) ? name : null;
}

/**
 * List the decision points and hook calls of one source file.
 *
 * @param {string} text - The file's source.
 * @param {string} fileName - Its name; a `.tsx` one is parsed as TSX.
 * @returns {{ decisions: string[], hooks: string[] }} Each entry is `kind@line`.
 */
export function decisionPoints(text, fileName) {
  const kind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, kind);
  /** @type {string[]} */
  const decisions = [];
  /** @type {string[]} */
  const hooks = [];
  /** @param {ts.Node} node */
  const visit = node => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
    const decision = decisionOf(node);
    if (decision) decisions.push(`${decision}@${line}`);
    const hook = hookOf(node);
    if (hook) hooks.push(`${hook}@${line}`);
    ts.forEachChild(node, visit);
  };
  visit(source);
  return { decisions, hooks };
}
