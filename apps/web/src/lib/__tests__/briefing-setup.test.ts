/**
 * Unconfigured briefing cards (W7).
 *
 * The rule under test is narrow and consequential: a card the user WANTS but
 * that has no source must be named, and a card the user HID must stay silent.
 * Getting the second half wrong would nag people about features they turned
 * off — the exact noise this line exists to avoid.
 *
 * The mapping itself is checked against the backend contract: every section the
 * app declares has an entry, and the ones that can never be `not_configured`
 * are pinned as such rather than left to chance.
 */

import { describe, it, expect } from 'vitest';

import {
  SECTION_SETTINGS_TARGET,
  assertSettingsTargetCompleteness,
  unconfiguredCards,
} from '../briefing-setup';
import { SETTINGS_SECTIONS } from '../settings-sections';
import { BRIEFING_SECTION_NAMES, type BriefingSection, type CardsBundle } from '@/types/briefing';

/** A bundle where every named section is `not_configured` and the rest is ok. */
function bundle(notConfigured: readonly BriefingSection[]): CardsBundle {
  const entries = BRIEFING_SECTION_NAMES.map(section => [
    section,
    {
      status: notConfigured.includes(section) ? 'not_configured' : 'ok',
      data: null,
      generated_at: '2026-07-26T08:00:00Z',
      error_code: notConfigured.includes(section) ? 'connector_not_configured' : null,
      error_message: null,
    },
  ]);
  return Object.fromEntries(entries) as unknown as CardsBundle;
}

const ALL = [...BRIEFING_SECTION_NAMES];

describe('unconfiguredCards', () => {
  it('names nothing when everything is configured', () => {
    expect(unconfiguredCards(bundle([]), ALL)).toEqual([]);
  });

  it('names a card that has no source', () => {
    expect(unconfiguredCards(bundle(['agenda']), ALL)).toEqual([
      { section: 'agenda', target: 'connectors' },
    ]);
  });

  it('stays silent about a card the user hid', () => {
    // The whole point: someone who hid the health card must never be asked to
    // configure it.
    const visible = ALL.filter(section => section !== 'health');
    expect(unconfiguredCards(bundle(['health']), visible)).toEqual([]);
  });

  it('keeps the grid order rather than a table order', () => {
    const visible: BriefingSection[] = ['mails', 'weather', 'agenda'];
    expect(unconfiguredCards(bundle(['weather', 'agenda', 'mails']), visible)).toEqual([
      { section: 'mails', target: 'connectors' },
      { section: 'weather', target: 'connectors' },
      { section: 'agenda', target: 'connectors' },
    ]);
  });

  it('sends the health card to its own settings section', () => {
    // health is gated by a toggle, not by a connector — sending the user to the
    // connectors page would be a dead end.
    expect(unconfiguredCards(bundle(['health']), ALL)).toEqual([
      { section: 'health', target: 'health-metrics' },
    ]);
  });

  it('survives a missing payload', () => {
    // First paint, or a failed fetch: no bundle, nothing to claim.
    expect(unconfiguredCards(undefined, ALL)).toEqual([]);
  });

  it('ignores statuses that are not a missing configuration', () => {
    // `empty` and `error` have their own in-card treatments; hijacking them
    // here would double up the message.
    const mixed = bundle([]);
    (mixed.agenda as { status: string }).status = 'empty';
    (mixed.mails as { status: string }).status = 'error';
    expect(unconfiguredCards(mixed, ALL)).toEqual([]);
  });
});

describe('SECTION_SETTINGS_TARGET — the contract', () => {
  it('covers every declared section', () => {
    expect(() => assertSettingsTargetCompleteness()).not.toThrow();
    expect(Object.keys(SECTION_SETTINGS_TARGET).sort()).toEqual([...BRIEFING_SECTION_NAMES].sort());
  });

  it('only points at settings sections that really exist', () => {
    // A typo here would produce a link to a section the settings page cannot
    // resolve — it would silently land the user at the top of the page.
    for (const target of Object.values(SECTION_SETTINGS_TARGET)) {
      if (target) expect(SETTINGS_SECTIONS).toHaveProperty(target);
    }
  });

  it('pins the two cards that can never report a missing configuration', () => {
    // `reminders` and `for_you` read local tables and never raise
    // ConnectorNotConfiguredError (fetchers.py). If that ever changes, this
    // test is where the contract breaks first.
    expect(SECTION_SETTINGS_TARGET.reminders).toBeNull();
    expect(SECTION_SETTINGS_TARGET.for_you).toBeNull();
  });

  it('gives every other card a destination', () => {
    const configurable = BRIEFING_SECTION_NAMES.filter(
      section => section !== 'reminders' && section !== 'for_you'
    );
    for (const section of configurable) {
      expect(
        SECTION_SETTINGS_TARGET[section],
        `${section} has nowhere to send the user`
      ).not.toBeNull();
    }
  });
});
