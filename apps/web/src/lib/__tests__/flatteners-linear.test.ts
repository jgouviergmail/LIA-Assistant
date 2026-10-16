/**
 * Every text flattener of the browser reads a hostile text in linear time
 * (ADR-326) — the twin of the API's `test_flatteners_are_linear.py`.
 *
 * The guard measures CPU GROWTH, never a wall-clock budget alone: each witness runs
 * at n and at 4n, and a flattener may not take more than eight times longer on
 * four times the text (linear grows ×4, quadratic ×16). Thread CPU excludes
 * descheduling and other workers; the original wall-time ceiling remains.
 * https://nodejs.org/docs/latest-v24.x/api/process.html#processthreadcpuusagepreviousvalue
 * A floor absorbs the
 * jitter of a loaded runner; a ceiling catches a pattern that is linear but
 * absurdly slow. Measured before the rewrite: 40 KB of newlines cost 1.3 s in
 * `flattenForVoice`, 120 KB of « [a](http://x » 6.3 s.
 *
 * Measured like the API twin: a thread clock may tick coarsely — Windows reads it
 * at the scheduler's 15.6 ms, and one call read 0 ms at n and 46 ms (three ticks)
 * at 4n, ×Infinity on a loaded suite (2026-10-14) — so a call's CPU is read over a
 * BATCH of calls spanning several ticks, the sizes alternate, and the median
 * paired growth decides. A call's thread CPU cannot exceed its wall time, so a
 * first call faster than the floor passes before any batch, as it always did.
 * Probed at that very size (a flattener of about 9 ms at n): the single call read
 * 0 ms at n in five rounds of eight, the batch 7.8-11.1 ms → 31-46.5 ms, ×3.2-×5.0.
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
// A batch reads the thread clock once it spans four of its coarsest ticks
// (Windows: 15.6 ms), within the API twin's sixteen calls: a call judged at 4n
// costs at least FLOOR_MS, so its linear n-sized twin fills the span within them.
const RESOLUTION_MS = 64;
const MAX_BATCH_CALLS = 16;
const SAMPLES = 3;

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

type Flatten = (text: string) => unknown;

function cpuMsSince(started: NodeJS.CpuUsage): number {
  const cpu = process.threadCpuUsage(started);
  return (cpu.user + cpu.system) / 1000;
}

/** The thread CPU and the wall time of ONE call. */
function oneCall(flatten: Flatten, text: string) {
  const cpuStarted = process.threadCpuUsage();
  const started = performance.now();
  flatten(text);
  return { cpuMs: cpuMsSince(cpuStarted), wallMs: performance.now() - started };
}

/** The fastest of three single calls: the ceiling, and the door to the growth test. */
function fastestWallMs(flatten: Flatten, text: string): number {
  let wallMs = Number.POSITIVE_INFINITY;
  for (let run = 0; run < 3; run += 1) {
    wallMs = Math.min(wallMs, oneCall(flatten, text).wallMs);
  }
  return wallMs;
}

/** One call's thread CPU, read over as many calls as the clock needs to tick. */
function perCallCpuMs(flatten: Flatten, text: string): number {
  const started = process.threadCpuUsage();
  let calls = 0;
  let spentMs = 0;
  do {
    flatten(text);
    calls += 1;
    spentMs = cpuMsSince(started);
  } while (spentMs < RESOLUTION_MS && calls < MAX_BATCH_CALLS);
  return spentMs / calls;
}

type Growth = { smallMs: number; largeMs: number };

const ratio = (growth: Growth) => growth.largeMs / Math.max(growth.smallMs, SMALL_FLOOR_MS);

/** The median paired growth, the two sizes alternating so a change of load is no curve. */
function medianGrowth(flatten: Flatten, smallText: string, largeText: string): Growth {
  const samples: Growth[] = [];
  for (let sample = 0; sample < SAMPLES; sample += 1) {
    samples.push({
      smallMs: perCallCpuMs(flatten, smallText),
      largeMs: perCallCpuMs(flatten, largeText),
    });
  }
  samples.sort((left, right) => ratio(left) - ratio(right));
  return samples[Math.floor(SAMPLES / 2)];
}

describe('every flattener grows linearly on a hostile text (ADR-326)', () => {
  for (const [name, flatten] of Object.entries(FLATTENERS)) {
    for (const [witness, make] of Object.entries(WITNESSES)) {
      it(`${name} on ${witness}`, () => {
        const largeText = make(4 * SMALL);
        const wallMs = fastestWallMs(flatten, largeText);
        expect(wallMs, `${wallMs.toFixed(0)} ms at ${4 * SMALL} chars`).toBeLessThan(CEILING_MS);
        // Its thread CPU is at most its wall time: under the floor, nothing to judge.
        if (wallMs < FLOOR_MS) return;
        const growth = medianGrowth(flatten, make(SMALL), largeText);
        if (growth.largeMs < FLOOR_MS) return;
        expect(
          growth.largeMs,
          `CPU grows ×${ratio(growth).toFixed(1)} for ×4 the text ` +
            `(${growth.smallMs.toFixed(1)} ms → ${growth.largeMs.toFixed(1)} ms per call)`
        ).toBeLessThanOrEqual(MAX_GROWTH * Math.max(growth.smallMs, SMALL_FLOOR_MS));
      });
    }
  }

  it('the criterion catches the former bullet rule', () => {
    // `^\s*` crossed the newlines: at every line start it swallowed the rest of
    // a run of empty lines before failing (quadratic, as it shipped).
    const former = (text: string) => text.replace(/^\s*[-*+•]\s+(.+)$/gm, '$1.');
    const make = WITNESSES['a run of newlines'];
    const growth = medianGrowth(former, make(SMALL), make(4 * SMALL));
    expect(growth.largeMs).toBeGreaterThanOrEqual(FLOOR_MS);
    expect(growth.largeMs).toBeGreaterThan(MAX_GROWTH * Math.max(growth.smallMs, SMALL_FLOOR_MS));
  });

  it('distinguishes a descheduled thread from CPU work without discarding wall time', () => {
    const sleeper = new Int32Array(new SharedArrayBuffer(4));
    // A 10 ms pause is shorter than the measured Windows CPU tick (16 ms):
    // prior work can be credited during it. Span the clock's established
    // measurement window twice; retain the same CPU/wall criterion.
    const measured = oneCall(() => Atomics.wait(sleeper, 0, 0, 2 * RESOLUTION_MS), '');
    expect(measured.wallMs).toBeGreaterThanOrEqual(RESOLUTION_MS);
    expect(measured.cpuMs).toBeLessThan(measured.wallMs / 2);
  });
});
