/**
 * The browser's voice projection agrees with the server's, case by case (ADR-301).
 *
 * `flattenForVoice`, `boundToTokens` and `estimateTokens` exist here for the
 * browser bridge and in Python for the phone's server bridge
 * (`apps/api/src/domains/voice_sessions/projection.py`). ONE corpus pins the
 * two: this test reads the SAME file pytest reads
 * (`apps/api/tests/unit/domains/voice_sessions/voice_projection_corpus.json`),
 * so a rule that drifts on one side fails the other's build.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { boundToTokens, estimateTokens, flattenForVoice } from '../delegation';

interface FlattenCase {
  id: string;
  input: string;
  expected: string;
}
interface BoundCase extends FlattenCase {
  max_tokens: number;
  cut_line: string;
}
interface TokensCase {
  id: string;
  input: string;
  expected: number;
}
interface Corpus {
  flatten: FlattenCase[];
  bound: BoundCase[];
  tokens: TokensCase[];
}

const CORPUS = join(
  process.cwd(),
  '..',
  'api',
  'tests',
  'unit',
  'domains',
  'voice_sessions',
  'voice_projection_corpus.json'
);

const corpus = JSON.parse(readFileSync(CORPUS, 'utf8')) as Corpus;

describe('voice projection corpus (shared with the API)', () => {
  it.each(corpus.flatten)('flattens $id as the server does', ({ input, expected }) => {
    expect(flattenForVoice(input)).toBe(expected);
  });

  it.each(corpus.bound)('bounds $id as the server does', ({ input, max_tokens, cut_line, expected }) => {
    expect(boundToTokens(input, max_tokens, cut_line)).toBe(expected);
  });

  it.each(corpus.tokens)('estimates $id as the server does', ({ input, expected }) => {
    expect(estimateTokens(input)).toBe(expected);
  });

  it('is not trivial', () => {
    expect(corpus.flatten.length).toBeGreaterThanOrEqual(8);
    expect(corpus.bound.length).toBeGreaterThanOrEqual(4);
  });
});
