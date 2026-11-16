/**
 * Every code the ntfy API can say reads as words, in every language, and a code this build does
 * not know reads as the generic sentence — never as a raw key.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { NTFY_OUTCOMES, NTFY_REFUSALS, outcomeKey, refusalKey } from '../ntfy-labels';

const LANGUAGES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

function locale(language: string): unknown {
  return JSON.parse(
    readFileSync(
      path.join(__dirname, `../../../../../locales/${language}/translation.json`),
      'utf8'
    )
  );
}

function at(tree: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      tree
    );
}

describe('ntfy labels', () => {
  it.each(LANGUAGES)('says every outcome and every refusal in %s', language => {
    const tree = locale(language);
    const keys = [
      ...NTFY_OUTCOMES.map(outcomeKey),
      ...NTFY_REFUSALS.map(refusalKey),
      outcomeKey('unknown'),
      refusalKey(null),
    ];

    const missing = keys.filter(key => {
      const value = at(tree, key);
      return typeof value !== 'string' || value.trim() === '';
    });

    expect(missing).toEqual([]);
  });

  it('reads a code it does not know as the generic sentence', () => {
    expect(outcomeKey('from_a_newer_api')).toBe('settings.notifications.ntfy.outcome.unknown');
    expect(refusalKey('ntfy_from_a_newer_api')).toBe('settings.notifications.ntfy.refusal.unknown');
    expect(refusalKey(null)).toBe('settings.notifications.ntfy.refusal.unknown');
  });
});
