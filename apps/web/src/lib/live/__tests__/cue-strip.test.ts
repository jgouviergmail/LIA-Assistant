/**
 * The browser strips a `cues` session's tags exactly as the server does (ADR-373).
 *
 * `stripTranscriptCues` exists here for the captions and the rows the browser
 * shows, and in Python for the archive and the phone's transcript
 * (`apps/api/src/domains/voice/expressive_cues.py`). ONE corpus pins the two:
 * this test reads the SAME file pytest reads
 * (`apps/api/tests/unit/domains/voice/cue_strip_corpus.json`), so a rule that
 * drifts on one side fails the other's build.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { heardText, stripTranscriptCues } from '../cue-strip';

interface StripCase {
  id: string;
  input: string;
  expected: string;
  tags: string[];
}

const CORPUS = join(
  process.cwd(),
  '..',
  'api',
  'tests',
  'unit',
  'domains',
  'voice',
  'cue_strip_corpus.json'
);

const corpus = JSON.parse(readFileSync(CORPUS, 'utf8')) as { strip: StripCase[] };

describe('cue stripping corpus (shared with the API)', () => {
  it.each(corpus.strip)('strips $id as the server does', ({ input, expected, tags }) => {
    expect(stripTranscriptCues(input)).toEqual({ text: expected, tags });
    expect(heardText(input)).toBe(expected);
  });

  it('reads a hostile run of brackets in linear time', () => {
    // A pattern that rescanned the rest of the text per opening mark froze the
    // tab on a long caption (ADR-326); bounded, this is milliseconds.
    const hostile = '['.repeat(200_000) + ' a'.repeat(50_000);
    const started = performance.now();
    stripTranscriptCues(hostile);
    expect(performance.now() - started).toBeLessThan(2_000);
  });
});
