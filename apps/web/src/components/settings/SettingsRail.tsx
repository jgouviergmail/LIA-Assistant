'use client';

/**
 * SettingsRail — the navigation half of the master-detail settings shell.
 *
 * A `<nav>` of real buttons, one per visible section, grouped under their tab
 * and group headings. The rail is the map; the pane is the territory: every
 * section is one activation away at all times, and the active one is stated
 * with `aria-current` — never with `disabled`, which would blur a keyboard
 * user (apps/web/CLAUDE.md).
 *
 * Tab and group labels are deliberately NOT headings: on desktop the rail is
 * visible next to the overview, whose `SettingsGroupLabel` h2s own the page
 * outline — the same labels as h2 twice would double every group in a screen
 * reader's heading navigation. Structure for assistive tech comes from the
 * landmark and the lists.
 */

import { Puzzle, Settings, Shield } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import type { SettingsSectionToken, SettingsTab } from '@/lib/settings-sections';
import type { SettingsShellTab } from '@/lib/settings-shell-model';
import { cn } from '@/lib/utils';

/** Same icons the tab bar always used for the three tabs. */
const TAB_ICONS: Record<SettingsTab, LucideIcon> = {
  preferences: Settings,
  features: Puzzle,
  administration: Shield,
};

export interface SettingsRailProps {
  lng: Language;
  /** Output of `buildSettingsShellModel` for this user. */
  model: SettingsShellTab[];
  /** Section currently shown in the pane; null when the overview is shown. */
  activeToken: SettingsSectionToken | null;
  onSelect: (token: SettingsSectionToken) => void;
}

export function SettingsRail({ lng, model, activeToken, onSelect }: SettingsRailProps) {
  const { t } = useTranslation(lng);

  return (
    <nav aria-label={t('settings.shell.nav_label')} className="space-y-5">
      {model.map(tab => {
        const TabIcon = TAB_ICONS[tab.tab];
        return (
          <div
            key={tab.tab}
            className={cn(tab.tab === 'administration' && 'border-t border-border/60 pt-5')}
          >
            <p className="flex items-center gap-2 px-2 pb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <TabIcon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              {t(`settings.tabs.${tab.tab}`)}
            </p>
            {tab.groups.map(group => (
              <div key={group.key}>
                {/* Full-strength `text-muted-foreground`, NOT an opacity
                    modifier: `/75` measured 3.05:1 at 11 px — the exact
                    ADR-172 trap (axe run 3). Hierarchy comes from size and
                    weight, never from fading the ink. */}
                <p className="px-2 pb-0.5 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t(`settings.groups.${group.key}`)}
                </p>
                <ul className="space-y-0.5">
                  {group.sections.map(section => {
                    const Icon = SETTINGS_SECTION_ICONS[section.token];
                    const active = section.token === activeToken;
                    return (
                      <li key={section.token}>
                        <button
                          type="button"
                          aria-current={active ? 'true' : undefined}
                          onClick={() => onSelect(section.token)}
                          className={cn(
                            'flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background',
                            active
                              ? 'bg-primary/10 font-medium text-primary'
                              : 'text-foreground hover:bg-accent/60'
                          )}
                        >
                          <Icon
                            className={cn(
                              'h-4 w-4 shrink-0',
                              active ? 'text-primary' : 'text-muted-foreground'
                            )}
                            aria-hidden="true"
                          />
                          <span className="min-w-0 flex-1 truncate">{t(section.titleKey)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        );
      })}
    </nav>
  );
}
