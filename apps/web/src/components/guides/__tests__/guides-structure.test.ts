/**
 * Structural guard for the three showcase guides (how / why / story × 6 locales).
 *
 * Three drifts have shipped invisibly, each because nothing compared the
 * markdown to the code that renders it:
 *
 *  - **Navigation short by one.** `GuideMarkdown` strips the markdown ToC and
 *    assigns anchor ids to `<h2>` elements POSITIONALLY from the arrays in
 *    `guides-toc.ts`. `HOW_TOC_SECTIONS` held 25 entries for 26 sections, so
 *    §26 (Psyche Engine) rendered with `id={undefined}`, no icon, and no
 *    sidebar row — in all six languages, from the day it was written.
 *  - **Markdown ToC out of sync.** The list humans read on GitHub claimed 25
 *    sections for 26. Cosmetic in the app (it is stripped) but a lie in the repo.
 *  - **Doc-version stamps diverging across locales.** `how.es.md` sat at 3.4
 *    while its five siblings were at 3.5, so a relative bump would have carried
 *    the gap forward forever.
 *
 * The release stamps (`LIA vX.Y.Z`, the header date) are checked too: they are
 * pure copy-paste work at release time, which is precisely what rots.
 */

import fs from 'fs';
import path from 'path';

import { describe, it, expect } from 'vitest';

import pkg from '../../../../package.json';
import en from '../../../../locales/en/translation.json';
import { HOW_TOC_SECTIONS, WHY_TOC_SECTIONS, STORY_TOC_SECTIONS } from '../guides-toc';
import type { GuideTocSection } from '../guides-toc';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;
const GUIDES_DIR = path.join(process.cwd(), 'src', 'data', 'guides');

interface Family {
  readonly name: 'how' | 'why' | 'story';
  readonly sections: readonly GuideTocSection[];
  /** `why`/`how` carry a numbered ToC for GitHub readers; `story` is a narrative. */
  readonly hasMarkdownToc: boolean;
}

const FAMILIES: readonly Family[] = [
  { name: 'how', sections: HOW_TOC_SECTIONS, hasMarkdownToc: true },
  { name: 'why', sections: WHY_TOC_SECTIONS, hasMarkdownToc: true },
  { name: 'story', sections: STORY_TOC_SECTIONS, hasMarkdownToc: false },
];

/** `privacy.*.md` lives in the same directory but carries its own policy date. */
const read = (family: string, lang: string): string =>
  fs.readFileSync(path.join(GUIDES_DIR, `${family}.${lang}.md`), 'utf-8');

const sectionNumbers = (text: string): string[] =>
  [...text.matchAll(/^## (\d+)\. /gm)].map(m => m[1]);

const tocNumbers = (text: string): string[] => [...text.matchAll(/^(\d+)\. \[/gm)].map(m => m[1]);

/** The `**Version**` stamp, whatever the locale calls it (Versión, Versione, 版本). */
const docVersion = (text: string): string | null =>
  text.match(/^\*\*(?:Version|Versione|Versión|版本)\*\*\s*[:：]\s*([0-9][0-9.]*)\s*$/m)?.[1] ?? null;

/** The header date line, whatever the locale calls it (Datum, Fecha, Data, 日期). */
const headerDate = (text: string): string | null =>
  text
    .split('\n')
    .slice(0, 14)
    .map(line => line.match(/^\*\*(?:Date|Datum|Fecha|Data|日期)\*\*\s*[:：]\s*(\d{4}-\d{2}-\d{2})\s*$/))
    .find(Boolean)?.[1] ?? null;

describe.each(FAMILIES)('$name guide', ({ name, sections, hasMarkdownToc }) => {
  it('has one navigation entry per section, in every locale', () => {
    // The array is positional: a mismatch strands the trailing sections with
    // `id={undefined}`, unreachable from the sidebar.
    const mismatched = LANGS.map(lang => ({ lang, count: sectionNumbers(read(name, lang)).length }))
      .filter(({ count }) => count !== sections.length)
      .map(({ lang, count }) => `${name}.${lang}: ${count} sections for ${sections.length} nav entries`);

    expect(mismatched).toEqual([]);
  });

  it('numbers its sections contiguously from 1', () => {
    const expected = sections.map((_, i) => String(i + 1));
    const broken = LANGS.filter(lang => sectionNumbers(read(name, lang)).join(',') !== expected.join(','))
      .map(lang => `${name}.${lang}: ${sectionNumbers(read(name, lang)).join(',')}`);

    expect(broken).toEqual([]);
  });

  it('has a translated sidebar label for every navigation entry', () => {
    // i18n parity across the other five locales is enforced by the pre-commit
    // hook, so the reference locale is enough to catch a missing key.
    const labels = (en as Record<string, { toc?: Record<string, string> }>)[name]?.toc ?? {};
    const missing = sections.map(s => s.id).filter(id => !(id in labels));
    const dangling = Object.keys(labels).filter(id => !sections.some(s => s.id === id));

    expect(missing, `no ${name}.toc label for: ${missing.join(', ')}`).toEqual([]);
    expect(dangling, `${name}.toc labels nothing renders: ${dangling.join(', ')}`).toEqual([]);
  });

  it(
    hasMarkdownToc
      ? 'lists every section in its markdown table of contents'
      : 'deliberately carries no markdown table of contents',
    () => {
      const found = LANGS.map(lang => ({ lang, toc: tocNumbers(read(name, lang)) }));

      if (!hasMarkdownToc) {
        expect(found.filter(({ toc }) => toc.length > 0).map(({ lang }) => lang)).toEqual([]);
        return;
      }

      const expected = sections.map((_, i) => String(i + 1)).join(',');
      const broken = found
        .filter(({ toc }) => toc.join(',') !== expected)
        .map(({ lang, toc }) => `${name}.${lang}: ToC lists ${toc.length}, document has ${sections.length}`);

      expect(broken).toEqual([]);
    }
  );

  it('carries the same doc-version stamp in all six locales', () => {
    const stamps = LANGS.map(lang => [lang, docVersion(read(name, lang))] as const);
    const missing = stamps.filter(([, v]) => v === null).map(([lang]) => lang);
    expect(missing, `no **Version** stamp in: ${missing.join(', ')}`).toEqual([]);

    const distinct = [...new Set(stamps.map(([, v]) => v))];
    expect(
      distinct,
      `doc versions diverge across locales: ${stamps.map(([l, v]) => `${l}=${v}`).join(' ')}`
    ).toHaveLength(1);
  });

  it('stamps the released application version in all six locales', () => {
    const stale = LANGS.filter(lang => !read(name, lang).includes(`LIA v${pkg.version}`));

    expect(stale, `these guides do not stamp LIA v${pkg.version}: ${stale.join(', ')}`).toEqual([]);
  });
});

describe('guide release stamps', () => {
  it('shares one header date across all 18 files', () => {
    // The date tracks the release, not the translation: a locale left behind is
    // the same drift class as a stale version stamp.
    const dates = FAMILIES.flatMap(({ name }) =>
      LANGS.map(lang => [`${name}.${lang}`, headerDate(read(name, lang))] as const)
    );
    const missing = dates.filter(([, d]) => d === null).map(([file]) => file);
    expect(missing, `no header date in: ${missing.join(', ')}`).toEqual([]);

    const distinct = [...new Set(dates.map(([, d]) => d))];
    expect(distinct, `header dates diverge: ${dates.map(([f, d]) => `${f}=${d}`).join(' ')}`).toHaveLength(
      1
    );
  });
});
