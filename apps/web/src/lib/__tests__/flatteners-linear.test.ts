/**
 * Every text flattener of the browser reads a hostile text in linear time
 * (ADR-326) — the twin of the API's `test_flatteners_are_linear.py`.
 *
 * The guard measures GROWTH, never a wall-clock budget alone: each witness runs
 * at n and at 4n, and a flattener may not take more than eight times longer on
 * four times the text (linear grows ×4, quadratic ×16). A floor absorbs the
 * jitter of a loaded runner; a ceiling catches a pattern that is linear but
 * absurdly slow. Measured before the rewrite: 40 KB of newlines cost 1.3 s in
 * `flattenForVoice`, 120 KB of « [a](http://x » 6.3 s.
 */

import { describe, expect, it } from 'vitest';

import { htmlToPlainText, looksLikeHtml } from '../html-plain-text';
import { flattenForVoice } from '../live/delegation';
import { readAsMarkdown } from '../markdown-references';
import { messageToPlainText } from '../message-clipboard';
import { toPlainPreview } from '../notification-preview';

const SMALL = 8_000;
const FLOOR_MS = 20;
// The small measurement is read as at least this: on a loaded runner a 3 ms
// run is not measurable to a factor of 8 (the API's guard read ×8.2 on a
// flattener whose exponent is 1.01). A quadratic flattener starting from this
// floor takes ×16 of it, twice what the criterion admits — still refused.
const SMALL_FLOOR_MS = FLOOR_MS / 4;
const MAX_GROWTH = 8;
const CEILING_MS = 1_500;

const FLATTENERS: Record<string, (text: string) => unknown> = {
  looksLikeHtml,
  htmlToPlainText,
  readAsMarkdown: text => readAsMarkdown(text),
  flattenForVoice,
  messageToPlainText,
  toPlainPreview: text => toPlainPreview(text, 120),
};

const WITNESSES: Record<string, (n: number) => string> = {
  'unclosed <a then blanks': n => '<a' + ' '.repeat(n),
  'unclosed <a then newlines': n => '<a' + '\n'.repeat(n),
  'a run of blanks': n => ' '.repeat(n),
  'a run of tabs': n => '\t'.repeat(n),
  'a run of newlines': n => '\n'.repeat(n),
  'newline-blank pairs': n => '\n '.repeat(n / 2),
  'blanks then <br>': n => ' '.repeat(n) + '<br>',
  'empty table cells': n => '--' + '| '.repeat(n / 2) + 'x',
  'table cells with tabs': n => '--' + '|\t'.repeat(n / 2) + 'x',
  'unmatched brackets': n => '['.repeat(n),
  'link openers': n => '[a]('.repeat(n / 4),
  'link openers with a scheme': n => '[a](http://x'.repeat(n / 12),
  'italic openers': n => '*a '.repeat(n / 3),
  'bold openers': n => '**a '.repeat(n / 4),
  'strike openers': n => '~~a '.repeat(n / 4),
  'code openers': n => '`a '.repeat(n / 3),
  'a run of backticks': n => '`'.repeat(n),
  'a run of fences': n => '```'.repeat(n / 3),
  'fence lines': n => '```\n'.repeat(n / 4),
  'heading marks then newlines': n => '#\n'.repeat(n / 2),
  'the icon class repeated': n =>
    '<span class="material-symbols-outlined' + ' material-symbols-outlined'.repeat(n / 26),
  'unclosed spans': n => '<span '.repeat(n / 6),
  'unclosed headings': n => '<h1>'.repeat(n / 4),
  'unclosed scripts': n => '<script>'.repeat(n / 8),
  ampersands: n => '&#'.repeat(n / 2),
  'quoted lines': n => '> a\n'.repeat(n / 4),
  // The two witnesses CodeQL named against the API's rewritten patterns (#927,
  // #928), measured linear on both sides: its analysis models neither `\b`
  // inside a lookahead nor a `(?=…)` guard.
  "a link opener then '<a >a' repeated": n => '<a >' + '<a >a'.repeat(n / 5),
  'tab-pipe pairs': n => '\t|'.repeat(n / 2),
};

function milliseconds(flatten: (text: string) => unknown, text: string): number {
  let best = Number.POSITIVE_INFINITY;
  for (let run = 0; run < 3; run += 1) {
    const started = performance.now();
    flatten(text);
    best = Math.min(best, performance.now() - started);
  }
  return best;
}

describe('every flattener grows linearly on a hostile text (ADR-326)', () => {
  for (const [name, flatten] of Object.entries(FLATTENERS)) {
    for (const [witness, make] of Object.entries(WITNESSES)) {
      it(`${name} on ${witness}`, () => {
        const small = milliseconds(flatten, make(SMALL));
        const large = milliseconds(flatten, make(4 * SMALL));
        expect(large, `${large.toFixed(0)} ms at ${4 * SMALL} chars`).toBeLessThan(CEILING_MS);
        if (large < FLOOR_MS) return;
        expect(large, `grows ×${(large / small).toFixed(1)} for ×4 the text`).toBeLessThanOrEqual(
          MAX_GROWTH * Math.max(small, SMALL_FLOOR_MS)
        );
      });
    }
  }

  it('the criterion catches the former bullet rule', () => {
    // `^\s*` crossed the newlines: at every line start it swallowed the rest of
    // a run of empty lines before failing (quadratic, as it shipped).
    const former = (text: string) => text.replace(/^\s*[-*+•]\s+(.+)$/gm, '$1.');
    const make = WITNESSES['a run of newlines'];
    const small = milliseconds(former, make(SMALL));
    const large = milliseconds(former, make(4 * SMALL));
    expect(large).toBeGreaterThanOrEqual(FLOOR_MS);
    expect(large).toBeGreaterThan(MAX_GROWTH * Math.max(small, SMALL_FLOOR_MS));
  });
});
