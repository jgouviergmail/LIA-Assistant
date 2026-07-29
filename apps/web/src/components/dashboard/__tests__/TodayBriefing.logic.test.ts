/**
 * TodayBriefing grid logic (UXR Lot 5, B4) — the pure visible-order rule and
 * the completeness guard: every briefing section MUST have a renderer and be
 * listed in BRIEFING_SECTION_NAMES (a future section that skips registration
 * fails here, mirroring the backend registry guard).
 */

import { describe, it, expect } from 'vitest';

import { visibleOrderedSections } from '../TodayBriefing';
import { BRIEFING_SECTION_NAMES } from '@/types/briefing';
import type { BriefingSection, CardsBundle, CardSection } from '@/types/briefing';

function section(status: CardSection['status'] = 'ok'): CardSection {
  return {
    status,
    data: null,
    generated_at: '2026-07-23T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function bundle(over: Partial<Record<BriefingSection, CardSection>> = {}): CardsBundle {
  // The bundle's per-section generics are irrelevant to the ordering rule
  // under test — a status-only stand-in per section is the honest minimum.
  return {
    ...(Object.fromEntries(BRIEFING_SECTION_NAMES.map(name => [name, section()])) as Record<
      BriefingSection,
      CardSection
    >),
    ...over,
  } as CardsBundle;
}

describe('visibleOrderedSections', () => {
  it('renders the stored order minus the hidden set', () => {
    const out = visibleOrderedSections(
      { order: ['mails', 'weather', 'agenda'] as BriefingSection[], hidden: ['weather'] },
      bundle()
    );
    expect(out).toEqual(['mails', 'agenda']);
  });

  it('falls back to every section without preferences', () => {
    const out = visibleOrderedSections(null, bundle());
    expect(new Set(out)).toEqual(new Set(BRIEFING_SECTION_NAMES));
  });

  it('skips a backend-hidden status even if prefs disagree (belt and braces)', () => {
    const out = visibleOrderedSections(
      { order: ['weather', 'agenda'] as BriefingSection[], hidden: [] },
      bundle({ weather: section('hidden') })
    );
    expect(out).toEqual(['agenda']);
  });

  it('returns empty when everything is hidden (grid CTA case)', () => {
    const out = visibleOrderedSections(
      { order: [...BRIEFING_SECTION_NAMES], hidden: [...BRIEFING_SECTION_NAMES] },
      bundle()
    );
    expect(out).toEqual([]);
  });
});

describe('section registry completeness (frontend mirror)', () => {
  it('the fallback covers exactly the 9 sections', () => {
    // visibleOrderedSections' fallback derives from the renderer map keys —
    // equality with BRIEFING_SECTION_NAMES pins renderer completeness.
    const out = visibleOrderedSections(null, bundle());
    expect(out.length).toBe(9);
    expect(new Set(out)).toEqual(new Set(BRIEFING_SECTION_NAMES));
  });
});
