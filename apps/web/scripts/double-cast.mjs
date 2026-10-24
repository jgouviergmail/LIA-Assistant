/**
 * Double-assertion counter and ratchet rules (audit AC-037).
 *
 * `x as unknown as T` (or `as any as`) lets code claim any type: a test double
 * built that way can drift from the production contract it stands in for
 * without one compiler error. The counter reads the syntax tree — a comment or a
 * string that merely spells the words is never counted — and the ratchet keeps
 * each file's count from growing. Pure functions; the runner is
 * `check-double-cast-ratchet.mjs`.
 */
import ts from 'typescript';

/** Intermediate types that turn an assertion into an escape hatch. */
const ESCAPE_KINDS = new Set([ts.SyntaxKind.UnknownKeyword, ts.SyntaxKind.AnyKeyword]);

/**
 * Count the double assertions of one source file.
 *
 * @param {string} text - The file's source.
 * @param {string} fileName - Its name; a `.tsx` one is parsed as TSX.
 * @returns {number} How many `as unknown as` / `as any as` it holds.
 */
export function countDoubleCasts(text, fileName) {
  const kind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, false, kind);
  let count = 0;
  /** @param {ts.Node} node */
  const visit = node => {
    if (ts.isAsExpression(node)) {
      let inner = node.expression;
      while (ts.isParenthesizedExpression(inner)) inner = inner.expression;
      if (ts.isAsExpression(inner) && ESCAPE_KINDS.has(inner.type.kind)) count += 1;
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return count;
}

/**
 * Compare a measurement with the frozen baseline.
 *
 * @param {Record<string, number>} current - Counts measured now, by file.
 * @param {Record<string, number>} baseline - Frozen counts, by file.
 * @returns {{ regressions: string[], improved: string[] }} Files over their
 *   frozen count (a new file is frozen at zero), and files under it.
 */
export function compare(current, baseline) {
  const regressions = Object.entries(current)
    .filter(([file, count]) => count > (baseline[file] ?? 0))
    .map(([file, count]) => `${file}: ${count} > ${baseline[file] ?? 0}`)
    .sort();
  const improved = Object.entries(baseline)
    .filter(([file, count]) => (current[file] ?? 0) < count)
    .map(([file]) => file)
    .sort();
  return { regressions, improved };
}

/**
 * The baseline after a fix: each count lowered to the measurement, never raised,
 * and no file added.
 *
 * @param {Record<string, number>} current - Counts measured now, by file.
 * @param {Record<string, number>} baseline - Frozen counts, by file.
 * @returns {Record<string, number>} The lowered baseline, cleared files dropped.
 */
export function shrink(current, baseline) {
  return Object.fromEntries(
    Object.entries(baseline)
      .map(([file, count]) => /** @type {[string, number]} */ ([file, Math.min(count, current[file] ?? 0)]))
      .filter(([, count]) => count > 0)
      .sort(([a], [b]) => a.localeCompare(b))
  );
}
