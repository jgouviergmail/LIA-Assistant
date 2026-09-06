/**
 * `'use client'` must be the FIRST statement of the module.
 *
 * Next.js reads the directive only in the directive prologue: one statement
 * above it — an import, most plausibly, since that is what an editor or a
 * script inserts — and the file silently stops being a client module. Every
 * hook it calls then runs on the server and the build fails with an
 * "Ecmascript file had an error" whose message names neither the directive
 * nor the cause.
 *
 * Measured 2026-09-06: an `import { useId } from 'react';` landed above the
 * directive in two components. `tsc --noEmit`, `vitest`, ESLint and the three
 * ratchets were ALL green — vitest transforms modules itself and never
 * consults the prologue — and the defect surfaced only when Playwright built
 * the application, three gates later. The whole settings page would have
 * failed to render in production.
 *
 * A comment or a blank line above the directive is fine: neither is a
 * statement, and Next skips both.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';
import { globSync } from 'tinyglobby';

const SRC = join(process.cwd(), 'src');

/** The file's first real statement, comments and blank lines skipped. */
function firstStatement(source: string): string {
  let rest = source.replace(/^\uFEFF/, '');
  for (;;) {
    const trimmed = rest.replace(/^\s+/, '');
    if (trimmed.startsWith('//')) {
      rest = trimmed.slice(trimmed.indexOf('\n') + 1);
      continue;
    }
    if (trimmed.startsWith('/*')) {
      const close = trimmed.indexOf('*/');
      if (close === -1) return '';
      rest = trimmed.slice(close + 2);
      continue;
    }
    return trimmed.split('\n', 1)[0]?.trim() ?? '';
  }
}

describe("the 'use client' directive opens its module", () => {
  it('is the first statement in every file that declares it', () => {
    const files = globSync(['**/*.{ts,tsx}'], {
      cwd: SRC,
      ignore: ['**/__tests__/**', '**/*.test.ts', '**/*.test.tsx'],
    });
    expect(files.length).toBeGreaterThan(100);

    const misplaced = files.filter(relative => {
      const source = readFileSync(join(SRC, relative), 'utf8');
      if (!/^\s*['"]use client['"]/m.test(source)) return false;
      return !/^['"]use client['"]/.test(firstStatement(source));
    });

    expect(misplaced, `'use client' is not the first statement in:\n${misplaced.join('\n')}`).toEqual(
      []
    );
  });

  it('recognises a directive introduced by comments and blank lines', () => {
    expect(firstStatement("// a note\n\n/* block */\n'use client';\nimport x from 'y';")).toBe(
      "'use client';"
    );
  });

  it('rejects a directive pushed down by an import', () => {
    expect(firstStatement("import { useId } from 'react';\n'use client';")).not.toMatch(
      /use client/
    );
  });
});
