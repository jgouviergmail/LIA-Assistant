/**
 * Every route that runs a reader of a route-scoped subtree in the BROWSER
 * scopes that subtree.
 *
 * The root layout leaves `ROUTE_SCOPED_TRANSLATIONS` out of the catalogue it
 * hands the browser (`i18n/scoped-translations.ts`). A client component that
 * reads one of them on a route without `<ScopedTranslations>` renders the raw
 * key — `faq.sections.chat.title` on screen — and nothing else would notice:
 * the server still holds the whole catalogue, so a server component, a
 * snapshot or a test with the echoing i18n stub all look right.
 *
 * So this walks the real import graph of `src/`:
 *
 * 1. a module READS a subtree when its code (not its comments) holds a key
 *    literal under it (`'faq.sections.'`, `` `blog.${slug}` ``) — a key
 *    BUILDER such as `lib/changelog.ts` counts, and so does every module that
 *    imports it, through the walk below;
 * 2. it runs in the browser on a route when a chain of runtime imports from
 *    that route's file to it passes through a `'use client'` module (a server
 *    component resolving the key itself sends the browser a string, not a key);
 * 3. that route's file must render `<ScopedTranslations scopes={...}>` naming
 *    the subtree.
 *
 * Measured when written (2026-10-28): the public FAQ and the dashboard FAQ are
 * the only two routes it requires to scope anything, and `blog` has no client
 * reader at all.
 *
 * Its blind spot, stated: a server component handing a client component a
 * scoped KEY as a string prop (`labelKey="blog.…"`) holds the literal on the
 * server side of the boundary, so no chain marks it. Resolve such a key on the
 * server and pass the text, as the landing's changelog band does.
 */

import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { isCommentLine, readSources } from '@/__tests__/source-scan';
import { ROUTE_SCOPED_TRANSLATIONS } from '../scoped-translations';

/** Every module of `src/`, tests aside — read at collection (`source-scan.ts`). */
const MODULES = readSources(
  file => /\.(ts|tsx)$/.test(file.relative) && !file.isTest && !/\.test\.tsx?$/.test(file.relative)
);
const TEXT = new Map(MODULES.map(file => [file.relative, file.text]));

/** A Next.js file convention under `app/`: what a request enters through. */
const ROUTE_FILE =
  /^app\/(?:.*\/)?(?:page|layout|template|not-found|error|global-error|loading|default)\.tsx$/;

/** The file's first real statement, comments and blank lines skipped. */
function isClientModule(text: string): boolean {
  let rest = text.replace(/^﻿/, '');
  for (;;) {
    rest = rest.replace(/^\s+/, '');
    if (rest.startsWith('//')) rest = rest.slice(rest.indexOf('\n') + 1);
    else if (rest.startsWith('/*')) rest = rest.slice(rest.indexOf('*/') + 2);
    else return /^['"]use client['"]/.test(rest);
  }
}

const IMPORT_FROM = /^\s*(?:import|export)\s+(type\s+)?[^'";]*?from\s+['"]([^'"]+)['"]/gm;
const SIDE_EFFECT_IMPORT = /^\s*import\s+['"]([^'"]+)['"]/gm;
const DYNAMIC_IMPORT = /import\(\s*['"]([^'"]+)['"]\s*\)/g;

/** A specifier resolved to a module of `src/`, or null (a package, an asset). */
function resolveSpecifier(from: string, specifier: string): string | null {
  let base: string;
  if (specifier.startsWith('@/')) base = specifier.slice(2);
  else if (specifier.startsWith('.')) base = path.posix.join(path.posix.dirname(from), specifier);
  else return null;
  const candidates = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`];
  return candidates.find(candidate => TEXT.has(candidate)) ?? null;
}

/** Runtime imports only: a type-only import puts no code in the browser. */
function runtimeImports(relative: string, text: string): string[] {
  const specifiers = [
    ...[...text.matchAll(IMPORT_FROM)].filter(m => !m[1]).map(m => m[2]),
    ...[...text.matchAll(SIDE_EFFECT_IMPORT)].map(m => m[1]),
    ...[...text.matchAll(DYNAMIC_IMPORT)].map(m => m[1]),
  ];
  return specifiers
    .map(specifier => resolveSpecifier(relative, specifier))
    .filter((target): target is string => target !== null);
}

/** Who imports each module, at run time. */
const IMPORTS = new Map<string, string[]>();
const IMPORTERS = new Map<string, string[]>();
for (const [relative, text] of TEXT) {
  const targets = runtimeImports(relative, text);
  IMPORTS.set(relative, targets);
  for (const target of targets) {
    IMPORTERS.set(target, [...(IMPORTERS.get(target) ?? []), relative]);
  }
}

/** Every module a `'use client'` module puts in the browser. */
function browserModules(): Set<string> {
  const reached = new Set<string>();
  const stack = [...TEXT.keys()].filter(file => isClientModule(TEXT.get(file) ?? ''));
  while (stack.length > 0) {
    const file = stack.pop() as string;
    if (reached.has(file)) continue;
    reached.add(file);
    stack.push(...(IMPORTS.get(file) ?? []));
  }
  return reached;
}

/** The module that DECLARES the subtrees names them without reading any key. */
const DECLARATION = 'i18n/scoped-translations.ts';

/** Whether a module's code holds a key literal under a subtree. */
function readsSubtree(text: string, subtree: string): boolean {
  const escaped = subtree.replace(/\./g, '\\.');
  // A one-segment subtree (`blog`) is also a route segment: only a key UNDER it counts.
  const exact = subtree.includes('.') ? `|['"\`]${escaped}['"\`]` : '';
  const key = new RegExp(`['"\`]${escaped}\\.${exact}`);
  return text.split('\n').some(line => !isCommentLine(line) && key.test(line));
}

/**
 * Routes that run `start` in the browser: each route file reached by walking
 * importers upward along a chain that holds a `'use client'` module.
 */
function browserRoutes(start: string): Set<string> {
  const routes = new Set<string>();
  const seen = new Set<string>();
  const stack: Array<[string, boolean]> = [[start, false]];
  while (stack.length > 0) {
    const [file, clientBelow] = stack.pop() as [string, boolean];
    const client = clientBelow || isClientModule(TEXT.get(file) ?? '');
    const state = `${file}#${client}`;
    if (seen.has(state)) continue;
    seen.add(state);
    if (ROUTE_FILE.test(file) && client) routes.add(file);
    for (const importer of IMPORTERS.get(file) ?? []) stack.push([importer, client]);
  }
  return routes;
}

/** The subtrees a route file's `<ScopedTranslations scopes={...}>` names. */
function scopedBy(text: string): Set<string> {
  const scoped = new Set<string>();
  for (const match of text.matchAll(/<ScopedTranslations\b[\s\S]*?scopes=\{([\s\S]*?)\}\s*>/g)) {
    for (const subtree of ROUTE_SCOPED_TRANSLATIONS) {
      if (match[1].includes(`'${subtree}'`)) scoped.add(subtree);
    }
  }
  return scoped;
}

describe('route-scoped translations reach every browser reader', () => {
  it('reads the source tree and its import graph', () => {
    // A silent miss would make the guard pass by measuring nothing.
    expect(MODULES.length).toBeGreaterThan(500);
    expect(IMPORTERS.get('components/faq/FAQContent.tsx')).toEqual([
      'components/faq/FAQPageClient.tsx',
    ]);
    expect(browserRoutes('components/faq/FAQContent.tsx')).toEqual(
      new Set(['app/[lng]/dashboard/faq/page.tsx'])
    );
  });

  it.each(ROUTE_SCOPED_TRANSLATIONS)('every route reading %s in the browser scopes it', subtree => {
    const unscoped: string[] = [];
    for (const [relative, text] of TEXT) {
      if (relative === DECLARATION || !readsSubtree(text, subtree)) continue;
      for (const route of browserRoutes(relative)) {
        if (!scopedBy(TEXT.get(route) ?? '').has(subtree)) unscoped.push(`${route} ← ${relative}`);
      }
    }
    expect(
      unscoped,
      `wrap the reader in <ScopedTranslations scopes={['${subtree}']}> on these routes`
    ).toEqual([]);
  });

  it('has the root layout leave the route-scoped subtrees out', () => {
    const layout = TEXT.get('app/[lng]/layout.tsx') ?? '';
    expect(layout).toContain('omitTranslations(translationBundle(lng), ROUTE_SCOPED_TRANSLATIONS)');
  });

  it('keeps the six whole catalogues out of every browser bundle', () => {
    // `i18n/index.ts` imports the six locale files and `ScopedTranslations`
    // reads it: either one reached from a client module would ship them all.
    const browser = browserModules();
    expect(browser.has('components/TranslationScope.tsx')).toBe(true);
    expect([...browser].filter(file => /^i18n\/index\.ts$|ScopedTranslations/.test(file))).toEqual(
      []
    );
  });
});
