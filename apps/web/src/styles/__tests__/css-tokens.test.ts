/**
 * A `--lia-*` token read with no fallback exists.
 *
 * `var(--missing)` raises nothing: the declaration silently falls back to the
 * property's inherited or initial value. Measured on 2026-11-05: a focus ring
 * that was never drawn, widgets without corners or background, text sized by
 * its parent, all behind twelve names that had never been defined.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SOURCE_ROOT = join(__dirname, '..', '..');
const SOURCE_FILE = /\.(css|ts|tsx)$/;

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    if (entry.name === '__tests__') return [];
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return SOURCE_FILE.test(entry.name) ? [path] : [];
  });
}

/** The tokens a text reads with no fallback, and those it defines. */
function tokensOf(text: string): { read: string[]; defined: string[] } {
  return {
    read: [...text.matchAll(/var\(\s*(--lia-[\w-]+)\s*\)/g)].map(match => match[1]),
    defined: [
      ...text.matchAll(/(?<![\w-])(--lia-[\w-]+)\s*:/g),
      // Set from the code, through a name a string holds.
      ...text.matchAll(/['"`](--lia-[\w-]+)['"`]/g),
    ].map(match => match[1]),
  };
}

/** The tokens read with no fallback that nothing defines, sorted. */
function undefinedTokens(texts: string[]): string[] {
  const tokens = texts.map(tokensOf);
  const defined = new Set(tokens.flatMap(token => token.defined));
  return [...new Set(tokens.flatMap(token => token.read))].filter(name => !defined.has(name)).sort();
}

describe('CSS tokens', () => {
  it('refuses a token read with no fallback and defined nowhere', () => {
    expect(undefinedTokens(['a { color: var(--lia-nope); }'])).toEqual(['--lia-nope']);
  });

  it('accepts a token defined in another file', () => {
    const texts = [':root { --lia-known: red; }', 'a { color: var(--lia-known); }'];

    expect(undefinedTokens(texts)).toEqual([]);
  });

  it('accepts a token the code sets', () => {
    const texts = ["const NAME = '--lia-set';", 'a { color: var(--lia-set); }'];

    expect(undefinedTokens(texts)).toEqual([]);
  });

  it('accepts a token read with a fallback, which is the reader declaring its absence', () => {
    expect(undefinedTokens(['a { font-size: calc(1px * var(--lia-scale, 1)); }'])).toEqual([]);
  });

  // Reads every source file: measured at 9 s on a container's mounted volume.
  it('holds for the whole application', { timeout: 60_000 }, () => {
    const files = sourceFiles(SOURCE_ROOT);

    expect(files.length).toBeGreaterThan(100);
    expect(undefinedTokens(files.map(path => readFileSync(path, 'utf-8')))).toEqual([]);
  });
});
