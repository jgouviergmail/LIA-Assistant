/**
 * Section renderer registry — the pane renders what the table declares.
 *
 * The master-detail page mounts ONE section, resolved through this registry.
 * Completeness is the `Record` type (a token with no renderer fails to
 * compile); what only a test can hold is AGREEMENT: the element a renderer
 * returns must be the very component `SETTINGS_SECTIONS.declaredIn` names —
 * checked by function identity name, so a registry entry quietly wired to the
 * wrong section fails here instead of shipping a pane that opens the wrong
 * card.
 */

import { describe, expect, it } from 'vitest';

import { SETTINGS_SECTIONS, type SettingsSectionToken } from '@/lib/settings-sections';
import { exportedComponentOf } from '@/lib/__tests__/helpers/settings-page-source';

import { SETTINGS_SECTION_REGISTRY } from '../settings-section-registry';

const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

describe('SETTINGS_SECTION_REGISTRY', () => {
  it('declares a renderer for every token', () => {
    for (const token of TOKENS) {
      expect(SETTINGS_SECTION_REGISTRY[token], `${token} has no entry`).toBeDefined();
      expect(typeof SETTINGS_SECTION_REGISTRY[token].render).toBe('function');
    }
  });

  it.each(TOKENS)('%s renders the component its table entry declares', token => {
    const element = SETTINGS_SECTION_REGISTRY[token].render('en');
    const component = element.type;
    expect(typeof component, `${token}: renderer did not return a component element`).toBe(
      'function'
    );
    expect(
      (component as { name: string }).name,
      `${token}: renderer returns a different component than declaredIn names`
    ).toBe(exportedComponentOf(SETTINGS_SECTIONS[token].declaredIn));
  });

  it('propagates the language to every section that takes one', () => {
    for (const token of TOKENS) {
      const element = SETTINGS_SECTION_REGISTRY[token].render('fr');
      const props = element.props as { lng?: string };
      if ('lng' in props) {
        expect(props.lng, `${token}: lng not forwarded`).toBe('fr');
      }
    }
  });

  it('keeps error-boundary features as non-empty labels', () => {
    for (const token of TOKENS) {
      const { feature } = SETTINGS_SECTION_REGISTRY[token];
      if (feature !== undefined) {
        expect(feature.length, `${token}: empty feature label`).toBeGreaterThan(0);
      }
    }
  });
});
