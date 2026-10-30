/**
 * JSON written the way the repository's Prettier writes it (`.prettierrc`,
 * printWidth 100), so a generator run with nothing new leaves no diff and
 * `pnpm format` has nothing to rewrite after one.
 *
 * Prettier is not a dependency the scripts can import (the formatter runs from
 * the developer's toolchain), and the shapes generators write are small:
 * objects one key per line, an array of scalars on one line when it fits.
 */

const PRINT_WIDTH = 100;

const isScalar = value => value === null || typeof value !== 'object';

function lines(value, indent, lead, trail) {
  if (isScalar(value)) return [`${indent}${lead}${JSON.stringify(value)}${trail}`];
  const inner = `${indent}  `;
  if (Array.isArray(value)) {
    if (value.every(isScalar)) {
      const flat = `${indent}${lead}[${value.map(item => JSON.stringify(item)).join(', ')}]${trail}`;
      if (flat.length <= PRINT_WIDTH) return [flat];
    }
    return [
      `${indent}${lead}[`,
      ...value.flatMap((item, i) => lines(item, inner, '', i < value.length - 1 ? ',' : '')),
      `${indent}]${trail}`,
    ];
  }
  const entries = Object.entries(value);
  if (entries.length === 0) return [`${indent}${lead}{}${trail}`];
  return [
    `${indent}${lead}{`,
    ...entries.flatMap(([key, item], i) =>
      lines(item, inner, `${JSON.stringify(key)}: `, i < entries.length - 1 ? ',' : '')
    ),
    `${indent}}${trail}`,
  ];
}

/**
 * Serialise a value as a Prettier-formatted JSON document.
 *
 * @param {unknown} value - A JSON value.
 * @returns {string} The document, with its final newline.
 */
export function formatJson(value) {
  return `${lines(value, '', '', '').join('\n')}\n`;
}
