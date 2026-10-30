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
import { PUBLIC_FAQ_SECTIONS } from '../../faq/faq-sections';
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

/**
 * Every `<h2>` `GuideMarkdown` will render, in its order.
 *
 * The renderer strips everything before the first `## N.` and then numbers the
 * REMAINING `h2` elements positionally — so an *unnumbered* heading in the body
 * consumes an id. `how` carried `## Conclusion` as its 30th heading with eleven
 * sections after it: the conclusion took §30's anchor and icon, sections 30-39
 * each wore their predecessor's, and §40 rendered with `id={undefined}`. Every
 * check above counts `^## \d+\.` headings only, so all of them stayed green.
 */
const renderedHeadings = (text: string): string[] => {
  const first = text.match(/\n## \d+\./);
  const body = first?.index != null ? text.substring(first.index) : text;
  return [...body.matchAll(/^## (.*)$/gm)].map(m => m[1]);
};

const tocNumbers = (text: string): string[] => [...text.matchAll(/^(\d+)\. \[/gm)].map(m => m[1]);

/**
 * Lines that CommonMark turns into a SETEXT heading: a paragraph line directly
 * above `---` (or `===`) is a heading, not a paragraph followed by a rule.
 * It renders as one more `<h2>` that `renderedHeadings` cannot see — every
 * anchor after it shifts by one. The last paragraph of §19.6 sat right above
 * the rule closing §19 in the six `how` guides. A list item, a table row, a
 * heading or a quote above the rule is not a paragraph, so it is not counted.
 */
const setextHeadings = (text: string): string[] => {
  const lines = text.split('\n');
  const found: string[] = [];
  let fenced = false;
  lines.forEach((line, i) => {
    if (line.startsWith('```')) fenced = !fenced;
    if (fenced || i === 0 || !/^(-{3,}|={3,})\s*$/.test(line)) return;
    const above = lines[i - 1];
    if (above.trim() && !/^\s*([-*+>|#]|\d+\.\s)/.test(above)) {
      found.push(`line ${i}: ${above.slice(0, 60)}`);
    }
  });
  return found;
};

/** The `**Version**` stamp, whatever the locale calls it (Versión, Versione, 版本). */
const docVersion = (text: string): string | null =>
  text.match(/^\*\*(?:Version|Versione|Versión|版本)\*\*\s*[:：]\s*([0-9][0-9.]*)\s*$/m)?.[1] ??
  null;

/** The header date line, whatever the locale calls it (Datum, Fecha, Data, 日期). */
const headerDate = (text: string): string | null =>
  text
    .split('\n')
    .slice(0, 14)
    .map(line =>
      line.match(/^\*\*(?:Date|Datum|Fecha|Data|日期)\*\*\s*[:：]\s*(\d{4}-\d{2}-\d{2})\s*$/)
    )
    .find(Boolean)?.[1] ?? null;

/** Every markdown link target that stays on the site (starts with `/`). */
const onSiteLinks = (text: string): string[] =>
  [...text.matchAll(/\]\((\/[^)\s]*)\)/g)].map(m => m[1]);

const PAGE_ANCHORS: Record<string, readonly string[]> = {
  '/how': HOW_TOC_SECTIONS.map(s => s.id),
  '/why': WHY_TOC_SECTIONS.map(s => s.id),
  '/story': STORY_TOC_SECTIONS.map(s => s.id),
  '/faq': PUBLIC_FAQ_SECTIONS.map(s => `faq-${s}`),
};
const BARE_PAGES = new Set(['/how', '/why', '/story', '/faq', '/maps', '/privacy', '/terms']);

/**
 * Why an on-site link would land nowhere, or `null` when it resolves.
 *
 * Guide anchors are assigned positionally from the TOC arrays and the public
 * FAQ exposes only `PUBLIC_FAQ_SECTIONS`, so an anchor that reads right in the
 * markdown can silently scroll to the top of the page after a rename. A link
 * carries its guide's locale prefix (`/en/story`), none for French, the
 * unprefixed default locale — otherwise it reaches the reader in another
 * language.
 */
const unresolvedLink = (target: string, lang: (typeof LANGS)[number] = 'fr'): string | null => {
  const prefix = lang === 'fr' ? '' : `/${lang}`;
  const localized = prefix === '' || target === prefix || target.startsWith(`${prefix}/`);
  if (!localized || /^\/(en|fr|de|es|it|zh)(\/|#|$)/.test(target.slice(prefix.length))) {
    return `${target}: a ${lang} guide links with the "${prefix || '(none)'}" locale prefix`;
  }
  const [page, anchor] = (target.slice(prefix.length) || '/').split('#');
  if (anchor === undefined) {
    return BARE_PAGES.has(page) ? null : `${target}: no such page`;
  }
  const anchors = PAGE_ANCHORS[page];
  if (!anchors) return `${target}: no anchors on ${page}`;
  return anchors.includes(anchor) ? null : `${target}: no anchor "${anchor}" on ${page}`;
};

/** Every `href` of a blog article body that stays on the site. */
const blogOnSiteLinks = (html: string): string[] =>
  [...html.matchAll(/href="(\/[^"]*)"/g)].map(m => m[1]);

/** The blog articles of a locale (their bodies are HTML kept in the translation file). */
const blogArticles = (lang: (typeof LANGS)[number]): Record<string, { body: string }> =>
  (
    JSON.parse(
      fs.readFileSync(path.join(process.cwd(), 'locales', lang, 'translation.json'), 'utf-8')
    ) as { blog: { articles: Record<string, { body: string }> } }
  ).blog.articles;

const REPO_HOME = 'https://github.com/jgouviergmail/LIA-Assistant';
const REPO_BLOB = `${REPO_HOME}/blob/main/`;
const REPO_ROOT = path.join(process.cwd(), '..', '..');

/** Every markdown link target that points at GitHub. */
const repoLinks = (text: string): string[] =>
  [...text.matchAll(/\]\((https:\/\/github\.com\/[^)\s]*)\)/g)].map(m => m[1]);

/**
 * Why a GitHub link of a guide would 404, or `null` when the document exists.
 *
 * The guides point at repository documents (ADRs, technical docs) rather than
 * restating them, in six languages at once; a renamed ADR would otherwise leave
 * every locale linking to nothing, and `doc_audit` does not follow http links.
 */
const missingRepoDoc = (url: string): string | null => {
  if (url === REPO_HOME) return null;
  if (!url.startsWith(REPO_BLOB)) return `${url}: not a document of ${REPO_HOME} on main`;
  const relative = url.slice(REPO_BLOB.length).split('#')[0];
  return fs.existsSync(path.join(REPO_ROOT, relative))
    ? null
    : `${url}: ${relative} does not exist`;
};

describe.each(FAMILIES)('$name guide', ({ name, sections, hasMarkdownToc }) => {
  it('has one navigation entry per section, in every locale', () => {
    // The array is positional: a mismatch strands the trailing sections with
    // `id={undefined}`, unreachable from the sidebar.
    const mismatched = LANGS.map(lang => ({ lang, count: sectionNumbers(read(name, lang)).length }))
      .filter(({ count }) => count !== sections.length)
      .map(
        ({ lang, count }) => `${name}.${lang}: ${count} sections for ${sections.length} nav entries`
      );

    expect(mismatched).toEqual([]);
  });

  it('renders no heading the navigation cannot name', () => {
    // The renderer counts every `<h2>`, not only the numbered ones: one extra
    // heading in the body shifts every anchor after it by one and strands the
    // last section with no id at all.
    const stray = LANGS.flatMap(lang =>
      renderedHeadings(read(name, lang))
        .filter(heading => !/^\d+\. /.test(heading))
        .map(heading => `${name}.${lang}: unnumbered heading "## ${heading}"`)
    );

    expect(stray).toEqual([]);

    const miscounted = LANGS.map(lang => ({
      lang,
      count: renderedHeadings(read(name, lang)).length,
    }))
      .filter(({ count }) => count !== sections.length)
      .map(
        ({ lang, count }) =>
          `${name}.${lang}: ${count} rendered <h2> for ${sections.length} nav entries`
      );

    expect(miscounted).toEqual([]);
  });

  it('never glues a paragraph to a rule (a setext heading the navigation cannot see)', () => {
    const glued = LANGS.flatMap(lang =>
      setextHeadings(read(name, lang)).map(where => `${name}.${lang} ${where}`)
    );

    expect(glued).toEqual([]);
  });

  it('numbers its sections contiguously from 1', () => {
    const expected = sections.map((_, i) => String(i + 1));
    const broken = LANGS.filter(
      lang => sectionNumbers(read(name, lang)).join(',') !== expected.join(',')
    ).map(lang => `${name}.${lang}: ${sectionNumbers(read(name, lang)).join(',')}`);

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
        .map(
          ({ lang, toc }) =>
            `${name}.${lang}: ToC lists ${toc.length}, document has ${sections.length}`
        );

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

describe('guide on-site links', () => {
  it('resolves known targets', () => {
    expect(unresolvedLink('/how#ddd')).toBeNull();
    expect(unresolvedLink(`/faq#faq-${PUBLIC_FAQ_SECTIONS[0]}`)).toBeNull();
    expect(unresolvedLink('/maps')).toBeNull();
  });

  it('rejects unknown targets', () => {
    expect(unresolvedLink('/how#nope')).not.toBeNull();
    expect(unresolvedLink('/faq#faq-nope')).not.toBeNull();
    expect(unresolvedLink('/nowhere')).not.toBeNull();
  });

  it('requires the guide locale prefix', () => {
    expect(unresolvedLink('/en/how#ddd', 'en')).toBeNull();
    expect(unresolvedLink('/how#ddd', 'en')).not.toBeNull();
    expect(unresolvedLink('/en/how#ddd', 'fr')).not.toBeNull();
  });

  it('extracts on-site links only', () => {
    expect(onSiteLinks('[a](/story) [b](https://x.y/z) [c](#local)')).toEqual(['/story']);
  });

  it.each(FAMILIES.flatMap(({ name }) => LANGS.map(lang => [name, lang] as const)))(
    'every on-site link of %s.%s resolves',
    (name, lang) => {
      const broken = onSiteLinks(read(name, lang))
        .map(target => unresolvedLink(target, lang))
        .filter(Boolean);

      expect(broken).toEqual([]);
    }
  );
});

describe('blog article on-site links', () => {
  it('extracts on-site hrefs only', () => {
    expect(blogOnSiteLinks('<a href="/how#ddd">a</a> <a href="https://x.y">b</a>')).toEqual([
      '/how#ddd',
    ]);
  });

  it.each(LANGS)('every on-site link of the %s blog resolves', lang => {
    const broken = Object.entries(blogArticles(lang)).flatMap(([slug, article]) =>
      blogOnSiteLinks(article.body)
        .map(target => unresolvedLink(target, lang))
        .filter(Boolean)
        .map(reason => `${slug}: ${reason}`)
    );

    expect(broken).toEqual([]);
  });
});

describe('guide repository links', () => {
  it('resolves a document of the repository', () => {
    expect(missingRepoDoc(`${REPO_BLOB}docs/ARCHITECTURE.md`)).toBeNull();
    expect(missingRepoDoc(`${REPO_BLOB}docs/ARCHITECTURE.md#anchor`)).toBeNull();
    expect(missingRepoDoc(REPO_HOME)).toBeNull();
  });

  it('rejects a missing document and another repository', () => {
    expect(missingRepoDoc(`${REPO_BLOB}docs/nope.md`)).not.toBeNull();
    expect(
      missingRepoDoc('https://github.com/jgouviergmail/LIA/blob/main/docs/ARCHITECTURE.md')
    ).not.toBeNull();
  });

  it.each(FAMILIES.flatMap(({ name }) => LANGS.map(lang => [name, lang] as const)))(
    'every repository link of %s.%s exists on main',
    (name, lang) => {
      const broken = repoLinks(read(name, lang))
        .map(url => missingRepoDoc(url))
        .filter(Boolean);

      expect(broken).toEqual([]);
    }
  );
});

/**
 * `why`, `how` and `story` are summaries, and their size is a ratchet.
 *
 * Releases used to append a paragraph per feature: by 2026-10-28 `why` held about
 * 15,000 French words and `how` about 53,000 — an hour and four hours of reading
 * for pages meant to be understood in broad strokes. They were rewritten
 * (2026-10-29) and these ceilings are the measured size of that rewrite plus 10 %.
 * SHRINK-ONLY: lower a ceiling when a page shrinks, never raise one to absorb a
 * release — a feature changes a sentence; what does not fit belongs to the FAQ or
 * `docs/`. Words for the five alphabetic locales, non-whitespace characters for
 * zh; link targets are not prose, so they are not counted.
 */
const GUIDE_BUDGETS: Record<'why' | 'how' | 'story', Record<(typeof LANGS)[number], number>> = {
  why: { en: 3886, fr: 4012, de: 3889, es: 4047, it: 3898, zh: 8185 },
  how: { en: 5630, fr: 6173, de: 5644, es: 6349, it: 5942, zh: 13169 },
  // `story` joined on 2026-10-29, rewritten in the author's voice the same day:
  // measured size of that rewrite plus 10 %, same rule as above.
  story: { en: 3666, fr: 3893, de: 3581, es: 3957, it: 3748, zh: 7404 },
};

const guideSize = (text: string, lang: (typeof LANGS)[number]): number => {
  const prose = text.replace(/\]\([^)]*\)/g, ']');
  return lang === 'zh'
    ? prose.replace(/\s/g, '').length
    : prose.split(/\s+/).filter(Boolean).length;
};

describe('guide length budget', () => {
  it.each(
    (['why', 'how', 'story'] as const).flatMap(name => LANGS.map(lang => [name, lang] as const))
  )('%s.%s stays within its length budget', (name, lang) => {
    expect(guideSize(read(name, lang), lang)).toBeLessThanOrEqual(GUIDE_BUDGETS[name][lang]);
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
    expect(
      distinct,
      `header dates diverge: ${dates.map(([f, d]) => `${f}=${d}`).join(' ')}`
    ).toHaveLength(1);
  });
});
