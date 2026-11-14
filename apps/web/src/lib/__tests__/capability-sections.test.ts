/**
 * The one table linking a capability to the settings section that governs it.
 *
 * Two surfaces read it in opposite directions — the constellation asks "where
 * do I set this up?", the settings overview asks "what does this section
 * currently hold?" — and two hand-written tables would eventually disagree
 * about the same pair. So there is one, and the reverse is derived.
 */

import { describe, expect, it } from 'vitest';

import {
  CAPABILITY_PAGE,
  CAPABILITY_SECTION,
  SECTION_CAPABILITY,
  CAPABILITY_SECTION_TAB,
  capabilityOfSection,
  pageOfCapability,
  tabOfCapability,
  sectionOfCapability,
} from '../capability-sections';
import { DASHBOARD_DESTINATIONS, destinationPath } from '../dashboard-nav';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '../settings-sections';

describe('CAPABILITY_SECTION', () => {
  it('only ever points at a real settings token', () => {
    for (const token of Object.values(CAPABILITY_SECTION)) {
      expect(Object.hasOwn(SETTINGS_SECTIONS, token)).toBe(true);
    }
  });

  it('never sends two capabilities to the same section', () => {
    // The reverse direction is a function, not a relation: a card showing
    // "12 items" must know WHICH capability it is quoting.
    const tokens = Object.values(CAPABILITY_SECTION);
    expect(new Set(tokens).size).toBe(tokens.length);
  });
});

describe('SECTION_CAPABILITY — the derived reverse', () => {
  it('is the exact inverse of the declared table', () => {
    for (const [capability, token] of Object.entries(CAPABILITY_SECTION)) {
      expect(SECTION_CAPABILITY[token]).toBe(capability);
    }
    expect(Object.keys(SECTION_CAPABILITY)).toHaveLength(Object.keys(CAPABILITY_SECTION).length);
  });
});

describe('lookups', () => {
  it('answers both directions for a linked pair', () => {
    expect(sectionOfCapability('memory')).toBe('memories');
    expect(capabilityOfSection('memories')).toBe('memory');
  });

  it('answers null rather than guessing, on either side', () => {
    // `relations` lives on its page, not in the settings, and `theme` holds no
    // capability: an invented pairing would put a count on a card that cannot
    // hold one.
    expect(sectionOfCapability('relations')).toBeNull();
    expect(capabilityOfSection('theme' as SettingsSectionToken)).toBeNull();
  });
});

describe('CAPABILITY_SECTION_TAB — a node landing on a TAB of a shared section (ADR-282)', () => {
  it('keeps the shared section out of the bijection', () => {
    // The kept answers share « generated-assets » with the files: the card
    // keeps the files' status, the node keeps its own destination.
    for (const capability of Object.keys(CAPABILITY_SECTION_TAB)) {
      expect(CAPABILITY_SECTION[capability]).toBeUndefined();
    }
  });

  it('routes the bookmarks node to the generated files, on their tab', () => {
    expect(sectionOfCapability('bookmarks')).toBe('generated-assets');
    expect(tabOfCapability('bookmarks')).toBe('bookmarks');
    // The reverse still names the capability that OWNS the section.
    expect(capabilityOfSection('generated-assets')).toBe('generated_files');
  });

  it('answers null for a capability that owns its whole section', () => {
    expect(tabOfCapability('memory')).toBeNull();
  });
});

describe('CAPABILITY_PAGE — a capability whose place is a page, not a section', () => {
  it('sends the workboard to its own page: it has no settings section left', () => {
    // The owner removed the board's settings section on 2026-11-11: the board
    // is a destination of the header, and its figures stand above its filters.
    expect(sectionOfCapability('workboard')).toBeNull();
    expect(pageOfCapability('workboard')).toBe('/dashboard/workboard');
  });

  it('sends the relations to their own page too: what they configure is shown there', () => {
    // ADR-269 put the debrief's switch on the Relations page, where its result
    // is read. The star used to fall back to the settings root, which holds
    // nothing about relations.
    expect(sectionOfCapability('relations')).toBeNull();
    expect(pageOfCapability('relations')).toBe('/dashboard/relations');
  });

  it('only names pages the header offers as destinations', () => {
    // A star must not lead to a route nothing else in the application knows.
    const known = new Set(
      DASHBOARD_DESTINATIONS.map(destination => destinationPath(destination.segment))
    );
    for (const page of Object.values(CAPABILITY_PAGE)) expect(known.has(page)).toBe(true);
  });

  it('never doubles a settings destination', () => {
    for (const capability of Object.keys(CAPABILITY_PAGE)) {
      expect(sectionOfCapability(capability)).toBeNull();
    }
  });

  it('answers null for a capability the settings configure', () => {
    expect(pageOfCapability('memory')).toBeNull();
    expect(pageOfCapability('documents')).toBeNull();
  });
});
