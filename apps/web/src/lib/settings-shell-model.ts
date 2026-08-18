/**
 * Derived model of the master-detail settings shell.
 *
 * The rail and the overview cards need each section's tab, group, title key
 * and visibility — all of which the two existing tables already declare:
 * `SETTINGS_SECTIONS` owns page order and the tab, `SETTINGS_SEARCH_META` owns
 * the group, the i18n keys and the availability gate. This module folds the
 * two into a render-ready tree; it declares nothing of its own, so there is no
 * third table to drift.
 */

import {
  isSectionAvailable,
  SETTINGS_SEARCH_META,
  type SettingsGroupKey,
  type SettingsSearchAvailability,
} from './settings-search';
import {
  SETTINGS_SECTIONS,
  type SettingsSectionToken,
  type SettingsTab,
} from './settings-sections';

export interface SettingsShellSection {
  token: SettingsSectionToken;
  /** i18n key of the section title — the same one the section header renders. */
  titleKey: string;
  /** i18n key of the section description. */
  descriptionKey: string;
}

export interface SettingsShellGroup {
  key: SettingsGroupKey;
  sections: SettingsShellSection[];
}

export interface SettingsShellTab {
  tab: SettingsTab;
  groups: SettingsShellGroup[];
}

/**
 * The sections this user can see, grouped for the rail and the overview.
 *
 * Page order is `SETTINGS_SECTIONS` order (the search tie-break contract);
 * groups come out contiguously because the table lists them that way. Gated
 * sections are dropped with the exact same predicate as the search index, so
 * the rail and the search can never disagree about what exists.
 *
 * Args:
 *   availability: Resolved flags for this user and instance.
 *
 * Returns:
 *   Tabs in page order, each with its non-empty groups in page order.
 */
export function buildSettingsShellModel(
  availability: SettingsSearchAvailability
): SettingsShellTab[] {
  const tabs: SettingsShellTab[] = [];

  for (const [token, target] of Object.entries(SETTINGS_SECTIONS) as Array<
    [SettingsSectionToken, (typeof SETTINGS_SECTIONS)[SettingsSectionToken]]
  >) {
    const meta = SETTINGS_SEARCH_META[token];
    if (!isSectionAvailable(meta.gate, availability)) continue;

    let tab = tabs.at(-1);
    if (!tab || tab.tab !== target.tab) {
      tab = { tab: target.tab, groups: [] };
      tabs.push(tab);
    }

    let group = tab.groups.at(-1);
    if (!group || group.key !== meta.group) {
      group = { key: meta.group, sections: [] };
      tab.groups.push(group);
    }

    group.sections.push({
      token,
      titleKey: meta.titleKey,
      descriptionKey: meta.descriptionKey,
    });
  }

  return tabs;
}
