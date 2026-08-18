'use client';

/**
 * SettingsOverview — the landing pane of the master-detail settings shell.
 *
 * Shown when no section is selected (desktop; on phones the rail itself is
 * the landing). Every visible section appears as a card with its icon, title
 * and description — the descriptions the accordion page never surfaced —
 * under real `SettingsGroupLabel` headings, which own the page outline (the
 * rail's labels are deliberately not headings).
 *
 * Zero data fetching by design: the cards state what a section IS, not what
 * it currently holds. Status summaries would put every section's endpoint on
 * the landing path — a deliberate non-goal of this lot.
 */

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import type { SettingsShellTab } from '@/lib/settings-shell-model';

import { SettingsGroupLabel } from './SettingsGroupLabel';

export interface SettingsOverviewProps {
  lng: Language;
  /** Output of `buildSettingsShellModel` for this user. */
  model: SettingsShellTab[];
  onSelect: (token: SettingsSectionToken) => void;
  /** Rendered above the groups — the portrait shortcut card lives here. */
  children?: React.ReactNode;
}

export function SettingsOverview({ lng, model, onSelect, children }: SettingsOverviewProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="space-y-2">
      {children}
      {model.map(tab =>
        tab.groups.map(group => (
          <section key={`${tab.tab}-${group.key}`}>
            <SettingsGroupLabel label={t(`settings.groups.${group.key}`)} />
            <ul className="grid grid-cols-1 gap-3 pb-4 sm:grid-cols-2 xl:grid-cols-3">
              {group.sections.map(section => {
                const Icon = SETTINGS_SECTION_ICONS[section.token];
                return (
                  <li key={section.token} className="min-w-0">
                    <button
                      type="button"
                      onClick={() => onSelect(section.token)}
                      className="flex h-full w-full items-start gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    >
                      <span className="flex shrink-0 rounded-lg bg-primary/10 p-2">
                        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold leading-tight">
                          {t(section.titleKey)}
                        </span>
                        <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">
                          {t(section.descriptionKey)}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
