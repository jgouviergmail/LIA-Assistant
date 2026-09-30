/**
 * A library refusal is the sentence the API named, with the facts it sent (ADR-327).
 *
 * What it must hold: every code the API sends has a sentence in the six
 * locales; a fact beside the code reaches the sentence; a refusal whose fact
 * is missing says its plain sentence, never a figure nobody sent; anything the
 * API did not name is left to the caller's generic sentence.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { LIBRARY_REFUSAL_KEYS, libraryRefusalOf } from '../errors';

/** The shape `api-client` throws: the parsed body on `.data`. */
function refused(detail: Record<string, unknown>): { status: number; data: unknown } {
  return { status: 409, data: { detail } };
}

describe('a named refusal', () => {
  it('is told in its own words', () => {
    expect(libraryRefusalOf(refused({ code: 'skill_library_name_taken' }), 'en')).toEqual({
      key: 'settings.skills.library.errors.skill_library_name_taken',
    });
  });

  it('quotes the audit risk it was refused on', () => {
    const refusal = libraryRefusalOf(
      refused({ code: 'skill_library_audit_blocked', risk: 'critical' }),
      'en'
    );
    expect(refusal).toEqual({
      key: 'settings.skills.library.errors.skill_library_audit_blocked',
      risk: 'critical',
    });
  });

  it('says which bound a too large skill passed', () => {
    expect(
      libraryRefusalOf(refused({ code: 'skill_library_too_large', max_files: 64 }), 'en')
    ).toEqual({
      key: 'settings.skills.library.errors.skill_library_too_large_files',
      values: { max: 64 },
    });
    expect(
      libraryRefusalOf(refused({ code: 'skill_library_too_large', max_kb: 2048 }), 'en')?.key
    ).toBe('settings.skills.library.errors.skill_library_too_large_kb');
  });

  it('writes when GitHub comes back as a clock time', () => {
    const refusal = libraryRefusalOf(
      refused({ code: 'skill_library_rate_limited', reset_at: 1_900_000_000 }),
      'en'
    );
    expect(refusal?.key).toBe('settings.skills.library.errors.skill_library_rate_limited');
    expect(String(refusal?.values?.time)).toMatch(/\d{1,2}:\d{2}/);
  });

  it.each([
    [
      { code: 'skill_library_audit_blocked', risk: 'catastrophic' },
      'skill_library_audit_blocked_plain',
    ],
    [{ code: 'skill_library_rate_limited' }, 'skill_library_rate_limited_plain'],
    [{ code: 'skill_library_renamed' }, 'skill_library_renamed_plain'],
    [{ code: 'skill_library_query_invalid' }, 'skill_library_query_invalid_plain'],
  ])('without its fact, says its plain sentence (%o)', (detail, key) => {
    expect(libraryRefusalOf(refused(detail), 'en')?.key).toBe(
      `settings.skills.library.errors.${key}`
    );
  });

  it('leaves an unnamed failure to the caller', () => {
    expect(libraryRefusalOf(refused({ code: 'something_else' }), 'en')).toBeNull();
    expect(libraryRefusalOf(new Error('network'), 'en')).toBeNull();
    expect(libraryRefusalOf({ status: 500, data: { detail: 'boom' } }, 'en')).toBeNull();
  });
});

describe('every sentence', () => {
  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])('exists in %s', lng => {
    const raw = readFileSync(
      join(__dirname, '../../../../locales', lng, 'translation.json'),
      'utf8'
    );
    const tree: unknown = JSON.parse(raw);
    const missing = LIBRARY_REFUSAL_KEYS.filter(key => {
      let node: unknown = tree;
      for (const part of key.split('.')) {
        node =
          typeof node === 'object' && node !== null
            ? (node as Record<string, unknown>)[part]
            : undefined;
      }
      return typeof node !== 'string' || node.trim() === '';
    });
    expect(missing).toEqual([]);
  });
});
