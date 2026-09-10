/**
 * An embedded API image asks for its credentials, or it never loads.
 *
 * The app answers `Cross-Origin-Embedder-Policy: credentialless` (measured on
 * production, 2026-09-10). Under that policy a **no-CORS cross-origin
 * subresource** — an `<img src>` with no `crossorigin` attribute — is fetched
 * WITHOUT credentials. The session cookie never reaches the API, it answers
 * 401, and the image is broken.
 *
 * A top-level navigation is not a subresource, so opening the very same URL in
 * a tab shows the image. That asymmetry is what made the defect read as a
 * rendering bug rather than an authentication one, and it is why the report
 * said « the thumbnail is missing but the image displays fine ».
 *
 * It only became reachable when these URLs stopped being relative: a
 * same-origin image always carries its cookies, and every deployment was
 * same-origin until `apiResourceUrl` started resolving against the API origin
 * (v1.43.2). One surface — the browser-screenshot card — had already met the
 * defect and closed it with a literal attribute; three had not.
 *
 * The accepted shape spreads the resolved props, so `src` and `crossOrigin`
 * cannot drift apart:
 *
 *     <img {...apiImageProps(wireUrl)} alt={…} />
 *
 * `src={apiResourceUrl(…)}` on an `<img>` is refused: it resolves the origin
 * and drops the credentials the new origin now requires.
 *
 * **The guard is tested against a known-bad sample on every run** — a guard
 * that cannot fail reports a safety it never checked.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { globSync } from 'tinyglobby';
import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');

/**
 * An `<img>` (or a `new Image()` assignment) whose source is resolved by
 * `apiResourceUrl` rather than `apiImageProps`.
 *
 * Anchored on the opening tag and bounded to the attribute list by a lazy scan
 * that stops at the first `/>` or `>`; JSX attribute values here are single
 * expressions, so no `>` of an arrow function sits between them.
 */
const IMG_WITH_RESOLVED_SRC = /<img\b[\s\S]*?src=\{[^}]*apiResourceUrl\(/g;

/** Files that legitimately name the helper: its own module and its tests. */
const EXEMPT = new Set(['lib/utils/api-resource-url.ts']);

function offenders(files: string[]): string[] {
  const found: string[] = [];
  for (const file of files) {
    const rel = file.replace(/\\/g, '/').split('/src/')[1] ?? file;
    if (EXEMPT.has(rel) || rel.includes('__tests__')) continue;
    const source = readFileSync(file, 'utf8');
    if (IMG_WITH_RESOLVED_SRC.test(source)) found.push(rel);
    IMG_WITH_RESOLVED_SRC.lastIndex = 0;
  }
  return found;
}

describe('embedded API images carry their credentials', () => {
  it('no <img> resolves its src without asking for credentials', () => {
    const files = globSync(['**/*.tsx', '**/*.ts'], { cwd: SRC, absolute: true });

    expect(
      offenders(files),
      'these render an <img> whose src goes through apiResourceUrl: under ' +
        'COEP credentialless the request carries no cookie and the API answers ' +
        '401. Spread apiImageProps(wireUrl) instead, so src and crossOrigin ' +
        'travel together.'
    ).toEqual([]);
  });

  it('detects the shape it exists to refuse', () => {
    // The exact code that shipped broken, so the guard proves it can fail.
    const bad = `
      <img
        src={apiResourceUrl(\`/api/v1/attachments/\${asset.id}\`)}
        alt={label}
      />
    `;
    expect(IMG_WITH_RESOLVED_SRC.test(bad)).toBe(true);
    IMG_WITH_RESOLVED_SRC.lastIndex = 0;

    const good = `<img {...apiImageProps(\`/api/v1/attachments/\${asset.id}\`)} alt={label} />`;
    expect(IMG_WITH_RESOLVED_SRC.test(good)).toBe(false);
    IMG_WITH_RESOLVED_SRC.lastIndex = 0;
  });
});
