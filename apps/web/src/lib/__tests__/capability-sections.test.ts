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
  CAPABILITY_SECTION,
  SECTION_CAPABILITY,
  capabilityOfSection,
  sectionOfCapability,
} from '../capability-sections';
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
    expect(Object.keys(SECTION_CAPABILITY)).toHaveLength(
      Object.keys(CAPABILITY_SECTION).length
    );
  });
});

describe('lookups', () => {
  it('answers both directions for a linked pair', () => {
    expect(sectionOfCapability('memory')).toBe('memories');
    expect(capabilityOfSection('memories')).toBe('memory');
  });

  it('answers null rather than guessing, on either side', () => {
    // `documents` has no settings section at all, and `theme` no capability:
    // an invented pairing would put a count on a card that cannot hold one.
    expect(sectionOfCapability('documents')).toBeNull();
    expect(capabilityOfSection('theme' as SettingsSectionToken)).toBeNull();
  });
});
