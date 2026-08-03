/**
 * Rendering a routine's upcoming runs.
 *
 * The instants come from the backend scheduler; this module only presents
 * them. What it must get right is the pair the backend cannot decide for it:
 * WHICH clock the hours are read against, and whether that clock changes
 * between two runs.
 */

import { describe, it, expect } from 'vitest';

import { renderOccurrences } from '../occurrences';

const PARIS = 'Europe/Paris';

describe('renderOccurrences — the routine’s clock, not the reader’s', () => {
  it('renders every instant in the routine timezone', () => {
    // 06:00 UTC in August is 08:00 in Paris.
    const rendered = renderOccurrences(['2026-08-03T06:00:00Z'], PARIS, 'fr');

    expect(rendered).toHaveLength(1);
    expect(rendered[0].label).toMatch(/08:00/);
    expect(rendered[0].iso).toBe('2026-08-03T06:00:00Z');
  });

  it('names the zone each run happens in', () => {
    const rendered = renderOccurrences(['2026-08-03T06:00:00Z'], PARIS, 'en');

    expect(rendered[0].zone).toBeTruthy();
  });

  it('does not follow the reader — a Tokyo browser still reads Paris hours', () => {
    // No timezone mocking needed: passing the zone explicitly is precisely
    // what makes the output independent of the runtime's own.
    const paris = renderOccurrences(['2026-08-03T06:00:00Z'], PARIS, 'fr')[0];
    const tokyo = renderOccurrences(['2026-08-03T06:00:00Z'], 'Asia/Tokyo', 'fr')[0];

    expect(paris.label).not.toBe(tokyo.label);
    expect(paris.label).toMatch(/08:00/);
    expect(tokyo.label).toMatch(/15:00/);
  });
});

describe('renderOccurrences — the clocks changing in between', () => {
  it('flags the run where summer time ends', () => {
    // 24 Oct 06:00Z = 08:00 CEST; 26 Oct 07:00Z = 08:00 CET. Same wall clock,
    // different instant — invisible unless said.
    const rendered = renderOccurrences(
      ['2026-10-24T06:00:00Z', '2026-10-26T07:00:00Z'],
      PARIS,
      'en'
    );

    expect(rendered[0].clockChange).toBe(false);
    expect(rendered[1].clockChange).toBe(true);
    expect(rendered[0].zone).not.toBe(rendered[1].zone);
  });

  it('never flags the first run — there is nothing to compare it to', () => {
    const rendered = renderOccurrences(['2026-10-26T07:00:00Z'], PARIS, 'en');

    expect(rendered[0].clockChange).toBe(false);
  });

  it('stays quiet when no transition occurs', () => {
    const rendered = renderOccurrences(
      ['2026-08-03T06:00:00Z', '2026-08-04T06:00:00Z', '2026-08-05T06:00:00Z'],
      PARIS,
      'en'
    );

    expect(rendered.every(run => !run.clockChange)).toBe(true);
  });

  it('flags a zone WITHOUT daylight saving never at all', () => {
    const rendered = renderOccurrences(
      ['2026-01-05T06:00:00Z', '2026-07-06T06:00:00Z'],
      'UTC',
      'en'
    );

    expect(rendered.every(run => !run.clockChange)).toBe(true);
  });
});

describe('renderOccurrences — degrading without lying', () => {
  it('drops an unparseable instant instead of rendering "Invalid Date"', () => {
    const rendered = renderOccurrences(['not-a-date', '2026-08-03T06:00:00Z'], PARIS, 'fr');

    expect(rendered).toHaveLength(1);
    expect(rendered[0].iso).toBe('2026-08-03T06:00:00Z');
  });

  it('still lists the runs when the zone is unknown to the runtime', () => {
    // A stale zone name must blank the hour, not the whole list.
    const rendered = renderOccurrences(['2026-08-03T06:00:00Z'], 'Mars/Olympus_Mons', 'fr');

    expect(rendered).toHaveLength(1);
    expect(rendered[0].label).toBeTruthy();
  });

  it('returns nothing for an empty input', () => {
    expect(renderOccurrences([], PARIS, 'fr')).toEqual([]);
  });
});

describe('renderOccurrences — the formatter cache never mixes two callers', () => {
  // `Intl.DateTimeFormat` is expensive to build and identical between renders,
  // so formatters are cached. The risk a cache introduces is serving one
  // caller's formatter to another: these pin that it cannot happen.
  const INSTANT = ['2026-08-03T06:00:00Z'];

  it('keeps two zones apart', () => {
    const paris = renderOccurrences(INSTANT, PARIS, 'fr')[0];
    const tokyo = renderOccurrences(INSTANT, 'Asia/Tokyo', 'fr')[0];
    // And back again — a cache that overwrote its entry would now be wrong.
    const parisAgain = renderOccurrences(INSTANT, PARIS, 'fr')[0];

    expect(paris.label).not.toBe(tokyo.label);
    expect(parisAgain.label).toBe(paris.label);
  });

  it('keeps two locales apart', () => {
    const fr = renderOccurrences(INSTANT, PARIS, 'fr')[0];
    const en = renderOccurrences(INSTANT, PARIS, 'en-US')[0];
    const frAgain = renderOccurrences(INSTANT, PARIS, 'fr')[0];

    expect(fr.label).not.toBe(en.label);
    expect(frAgain.label).toBe(fr.label);
  });

  it('does not let a bad zone poison the next good one', () => {
    // The unknown zone falls back to a zone-less formatter; that entry must
    // not then be served to a caller who DID name a valid zone.
    renderOccurrences(INSTANT, 'Mars/Olympus_Mons', 'fr');
    const paris = renderOccurrences(INSTANT, PARIS, 'fr')[0];

    expect(paris.label).toMatch(/08:00/);
  });
});
