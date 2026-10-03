/**
 * One colour code for LIA's domains: the briefing tiles' icons and the
 * notification hub's chips read the same table, and a chip is never drawn in
 * the grey the design rules reserve for inactive elements.
 */

import { describe, expect, it } from 'vitest';

import {
  DOMAIN_CHIP_TONE,
  DOMAIN_ICON_TONE,
  HEARTBEAT_SOURCE_TONE,
  THEME_CHIP_TONE,
  heartbeatSourceChipTone,
} from '../domain-tone';

describe('domain tone', () => {
  it('gives every domain both an icon and a chip colour', () => {
    expect(Object.keys(DOMAIN_CHIP_TONE).sort()).toEqual(Object.keys(DOMAIN_ICON_TONE).sort());
  });

  it("colours a heartbeat source with its domain's tile colour", () => {
    expect(heartbeatSourceChipTone('UPCOMING_CALENDAR_EVENTS')).toBe(DOMAIN_CHIP_TONE.violet);
    expect(heartbeatSourceChipTone('UNREAD_EMAILS')).toBe(DOMAIN_CHIP_TONE.emerald);
    expect(heartbeatSourceChipTone('CURRENT_WEATHER')).toBe(DOMAIN_CHIP_TONE.sky);
    // The workboard card's tone, read again on a notification that used it.
    expect(heartbeatSourceChipTone('WORKBOARD')).toBe(DOMAIN_CHIP_TONE.orange);
  });

  it('falls back to the theme primary, never to grey, for a source without a domain', () => {
    expect(heartbeatSourceChipTone('A_SOURCE_ADDED_LATER')).toBe(THEME_CHIP_TONE);
    for (const classes of [THEME_CHIP_TONE, ...Object.values(DOMAIN_CHIP_TONE)]) {
      expect(classes).not.toMatch(/muted|secondary|gray|slate|zinc|neutral/);
    }
    for (const tone of Object.values(HEARTBEAT_SOURCE_TONE)) {
      expect(DOMAIN_CHIP_TONE[tone]).toBeDefined();
    }
  });
});
