/**
 * Neutral-line guard — one colour for every panel edge and separator.
 *
 * The authenticated screens drew their neutral lines at SEVEN strengths, from
 * `border-border/20` to `/80` (313 occurrences in 177 files, measured
 * 2026-10-21). A panel at `/50` or `/40` read as having no border at all next
 * to one at `/70`, and a list split by `/50` hairlines looked unlike one split
 * by `/60`: the owner saw « some panels have a border and others not ». The
 * rule is now one line colour — the default `border` (`--color-border`), the
 * one the `Card` and `Separator` primitives draw — for panel edges and
 * separators alike, so a screen cannot drift from its neighbour again.
 *
 * Scope: the authenticated screens. The public site keeps its own identity,
 * the chat its bubbles and floating pills, the debug instrument its density —
 * none is inspected. Within the scope, a string that draws a CHIP
 * (`rounded-full`) or a DASHED outline is not a panel nor a separator and is
 * left alone.
 */

import { describe, it, expect } from 'vitest';

import { readSources } from './source-scan';

/** The authenticated screens, by their place in `src/`. */
const SCOPE: readonly RegExp[] = [
  /^components\/(settings|dashboard|relations|workboard|psyche|notifications|meetings|onboarding|telephony|spaces|sms|shortcuts|recurrence|radio|commitments|activity|effects)\//,
  /^components\/capabilities\/CapabilityList\.tsx$/,
  /^components\/ui\/(disclosure|timeline-group|heading-rule)\.tsx$/,
  /^app\/\[lng\]\/dashboard\//,
];

/** The chat route keeps the chat's own visual language. */
const OUT_OF_SCOPE: readonly string[] = ['app/[lng]/dashboard/chat/page.tsx'];

const SOURCES = readSources(
  file =>
    file.relative.endsWith('.tsx') &&
    !file.isTest &&
    SCOPE.some(scope => scope.test(file.relative)) &&
    !OUT_OF_SCOPE.includes(file.relative)
);

/** A reduced-alpha neutral line: `border-border/50`, `hover:divide-border/60`, `border-b-border/40`. */
const DIMMED_LINE =
  /(?<![\w/-])(?:[a-z0-9[\]&_=:-]+:)*(?:border|divide)(?:-[tblrxy])?-border\/\d{1,3}(?![\w/.\]-])/g;
/** Every string literal of a file — where class lists live. */
const LITERAL = /'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g;

describe('neutral-line guard', () => {
  const offenders: string[] = [];

  for (const { relative, text } of SOURCES) {
    for (const literal of text.match(LITERAL) ?? []) {
      if (literal.includes('rounded-full') || literal.includes('border-dashed')) continue;
      for (const match of literal.match(DIMMED_LINE) ?? []) offenders.push(`${relative}: ${match}`);
    }
  }

  it('reads the authenticated screens', () => {
    // A scope that matched nothing would make the guard pass vacuously.
    expect(SOURCES.length).toBeGreaterThan(100);
  });

  it('recognises a dimmed line in every shape it takes, and only those', () => {
    const sample =
      'rounded-xl border border-border/50 divide-y divide-border/60 border-b-border/40 hover:border-border/30';
    expect(sample.match(DIMMED_LINE)).toEqual([
      'border-border/50',
      'divide-border/60',
      'border-b-border/40',
      'hover:border-border/30',
    ]);
    expect('rounded-xl border border-border divide-y divide-border'.match(DIMMED_LINE)).toBeNull();
    expect('border-primary/20 border-amber-500/25'.match(DIMMED_LINE)).toBeNull();
  });

  it('draws every panel edge and separator in the one neutral line colour', () => {
    expect(
      offenders,
      'use the default line (`border`, `border-border`, `divide-border`), never a dimmed one:\n' +
        offenders.map(o => `  ${o}`).join('\n')
    ).toEqual([]);
  });
});
