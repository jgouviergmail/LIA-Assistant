/**
 * The "How LIA works" cards are wired by THREE independent things, and any one
 * of them can drift in silence:
 *
 *  - the locale content (`faq.intro.features.<key>.title` / `.description`),
 *    written and translated into the six languages;
 *  - the `featureKeys` array, which decides what the section renders;
 *  - the `featureIcons` map, read as `featureIcons[key as keyof typeof …]` —
 *    a missing icon yields `undefined`, and `<undefined />` crashes the page.
 *    The `as keyof` cast hides that from tsc entirely.
 *
 * Proven damage: `hitl` (1,332 characters, rewritten at v1.25.7), and
 * `semanticLeakDefense` (v1.20.6) and `healthMetrics` (v1.17.1) were fully
 * translated and listed nowhere, so they rendered nowhere. Wiring them
 * immediately crashed the FAQ test suite for want of icons — which is the
 * failure mode this file now catches before a human does.
 *
 * i18n parity across the other five locales is enforced by the pre-commit hook,
 * so checking the reference locale here is enough to catch the wiring drift.
 */

import { describe, it, expect } from 'vitest';

import en from '../../../../locales/en/translation.json';
import { featureKeys, featureIcons } from '../FAQContent';

const features = en.faq.intro.features as Record<string, { title: string; description: string }>;

/**
 * Cards that predate the `featureKeys` array (created at v1.6.1) and were never
 * part of it: a deliberate curation of the section, not an oversight. Verified
 * with `git log -S '"<key>": {' -- apps/web/locales/en/translation.json`.
 *
 * SHRINK-ONLY. Wiring one of these is welcome — remove it from the list. Adding
 * to it means a card was written, translated six times, and hidden: fix the
 * wiring instead.
 */
const DELIBERATELY_NOT_RENDERED = [
  'routing',
  'query',
  'semantic',
  'context',
  'summarization',
  'connectors',
  'streaming',
  'resilience',
  'reminders',
  'personalities',
  // 'geolocation' left this list at v1.30.0: the ADR-219 generalized cascade
  // made the card a differentiator, so it was rewritten and wired.
  'tools',
] as const;

describe('FAQ feature cards wiring', () => {
  it('renders every card that is not deliberately withheld', () => {
    const orphaned = Object.keys(features).filter(
      key =>
        !(featureKeys as readonly string[]).includes(key) &&
        !(DELIBERATELY_NOT_RENDERED as readonly string[]).includes(key)
    );

    expect(
      orphaned,
      `these cards exist in the six locales but are absent from featureKeys, so ` +
        `they render nowhere: ${orphaned.join(', ')}. Wire them, or add them to ` +
        `DELIBERATELY_NOT_RENDERED with the reason.`
    ).toEqual([]);
  });

  it('has locale content for every card it renders', () => {
    const dangling = featureKeys.filter(key => !(key in features));

    expect(
      dangling,
      `these keys are rendered but have no locale entry, so the card would show ` +
        `raw i18n keys: ${dangling.join(', ')}`
    ).toEqual([]);
  });

  it('has an icon for every card it renders', () => {
    // The crash class: `featureIcons[key as keyof typeof featureIcons]` returns
    // undefined for an unlisted key, and React throws on `<undefined />`.
    const iconless = featureKeys.filter(key => !(key in featureIcons));

    expect(
      iconless,
      `these keys have no icon, so rendering the section throws: ${iconless.join(', ')}`
    ).toEqual([]);
  });

  it('keeps the withheld list honest and shrink-only', () => {
    const contradictory = DELIBERATELY_NOT_RENDERED.filter(key =>
      (featureKeys as readonly string[]).includes(key)
    );
    expect(
      contradictory,
      `these keys are listed as withheld but ARE rendered: ${contradictory.join(', ')}`
    ).toEqual([]);

    const vanished = DELIBERATELY_NOT_RENDERED.filter(key => !(key in features));
    expect(
      vanished,
      `these withheld keys no longer exist in the locales: ${vanished.join(', ')}`
    ).toEqual([]);

    // Ratchet: 12 at v1.25.30, after wiring hitl / semanticLeakDefense /
    // healthMetrics. Lower it when a card is wired; never raise it.
    expect(DELIBERATELY_NOT_RENDERED.length).toBeLessThanOrEqual(12);
  });

  it('declares no icon that nothing renders', () => {
    const unused = Object.keys(featureIcons).filter(
      key => !(featureKeys as readonly string[]).includes(key)
    );

    expect(unused, `these icons are declared but unused: ${unused.join(', ')}`).toEqual([]);
  });
});
