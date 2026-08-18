/**
 * Shell model — what the rail and the overview render, derived, never declared.
 *
 * The master-detail rail groups sections by tab and by group heading, in page
 * order, filtered by the same availability gates as the search. All of that
 * already lives in `SETTINGS_SECTIONS` (order, tab) and `SETTINGS_SEARCH_META`
 * (group, gate): the model is a pure fold over the two tables, so there is no
 * third table to drift.
 */

import { describe, expect, it } from 'vitest';

import { buildSettingsShellModel } from '../settings-shell-model';
import { SETTINGS_SEARCH_META, type SettingsSearchAvailability } from '../settings-search';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '../settings-sections';

const ALL: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

function flatTokens(model: ReturnType<typeof buildSettingsShellModel>): SettingsSectionToken[] {
  return model.flatMap(tab => tab.groups.flatMap(group => group.sections.map(s => s.token)));
}

describe('buildSettingsShellModel', () => {
  it('keeps page order and covers every available section for a regular user', () => {
    const model = buildSettingsShellModel(ALL);
    const expected = TOKENS.filter(
      token => SETTINGS_SECTIONS[token].tab !== 'administration'
    );
    expect(flatTokens(model)).toEqual(expected);
  });

  it('shows two tabs to a regular user, three to a superuser', () => {
    expect(buildSettingsShellModel(ALL).map(tab => tab.tab)).toEqual(['preferences', 'features']);
    expect(buildSettingsShellModel({ ...ALL, isSuperuser: true }).map(tab => tab.tab)).toEqual([
      'preferences',
      'features',
      'administration',
    ]);
  });

  it('groups sections under the group the search meta declares, in order', () => {
    const model = buildSettingsShellModel(ALL);
    for (const tab of model) {
      for (const group of tab.groups) {
        expect(group.sections.length).toBeGreaterThan(0);
        for (const section of group.sections) {
          expect(SETTINGS_SEARCH_META[section.token].group).toBe(group.key);
        }
      }
    }
    // Order inside the preferences tab: personalization first, then the rest,
    // each group listed once (page order groups sections contiguously).
    const prefGroups = model[0].groups.map(group => group.key);
    expect(prefGroups[0]).toBe('personalization');
    expect(new Set(prefGroups).size).toBe(prefGroups.length);
  });

  it('applies the availability gates — a gated section leaves its group', () => {
    const model = buildSettingsShellModel({ ...ALL, openLoopsEnabled: false });
    expect(flatTokens(model)).not.toContain('open-loops');
  });

  it('drops the user debug panel for a superuser, and the admin tab for everyone else', () => {
    const superuser = flatTokens(buildSettingsShellModel({ ...ALL, isSuperuser: true }));
    expect(superuser).not.toContain('debug-panel');
    expect(superuser).toContain('admin-users');
    expect(superuser).toContain('debug-settings');

    const regular = flatTokens(buildSettingsShellModel(ALL));
    expect(regular).toContain('debug-panel');
    expect(regular).not.toContain('admin-users');
  });

  it('exposes the title and description keys the sections themselves render', () => {
    const model = buildSettingsShellModel(ALL);
    const language = model[0].groups[0].sections[0];
    expect(language.token).toBe('language');
    expect(language.titleKey).toBe('settings.language.title');
    expect(language.descriptionKey).toBe('settings.language.description');
  });
});
