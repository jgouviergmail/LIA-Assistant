'use client';

/**
 * MyShortcutsSettings — pick the settings sections the floating dock shows on
 * every screen (ADR-277; server-persisted in users.settings_shortcuts).
 *
 * The list is the settings shell's own model (`buildSettingsShellModel` under
 * the same availability as the rail and the search), grouped as the rail
 * groups it and marked with each group's tone, so a person recognises here
 * the map they already know. One checkbox per section, saved on each change
 * (optimistic, rolled back with an error toast on failure). At the cap the
 * unchecked boxes are `aria-disabled` and guarded by their handler — never
 * `disabled`, which would drop a keyboard reader's focus on `<body>` — and
 * the counter says why.
 */

import { useMemo } from 'react';
import { Pin } from 'lucide-react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { Checkbox } from '@/components/ui/checkbox';
import { useSettingsAvailability } from '@/hooks/useSettingsAvailability';
import { MY_SHORTCUTS_TOKEN, useSettingsShortcuts } from '@/hooks/useSettingsShortcuts';
import { useTranslation } from '@/i18n/client';
import { toneForSection } from '@/lib/settings-group-tones';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import { cn } from '@/lib/utils';
import type { BaseSettingsProps } from '@/types/settings';

/** One section as a pinnable row: its icon in the group's tone, its title, a box. */
function SectionRow({
  token,
  label,
  checked,
  blocked,
  onToggle,
}: {
  token: SettingsSectionToken;
  label: string;
  checked: boolean;
  /** The cap is reached and this one is not pinned: shown, not takeable. */
  blocked: boolean;
  onToggle: () => void;
}) {
  const Icon = SETTINGS_SECTION_ICONS[token];
  const tone = toneForSection(token);
  const id = `my-shortcut-${token}`;
  return (
    <li>
      <label
        htmlFor={id}
        className={cn(
          'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm transition-colors',
          checked
            ? 'border-primary/40 bg-primary/5'
            : 'border-border/40 bg-card/60 hover:bg-accent/40',
          blocked && 'cursor-not-allowed opacity-60'
        )}
      >
        <Checkbox
          id={id}
          checked={checked}
          aria-disabled={blocked || undefined}
          onChange={() => {
            if (blocked) return;
            onToggle();
          }}
        />
        <span
          className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-md', tone.chip)}
        >
          <Icon className={cn('h-4 w-4', tone.glyph)} aria-hidden="true" />
        </span>
        <span className="min-w-0 truncate">{label}</span>
      </label>
    </li>
  );
}

export function MyShortcutsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const availability = useSettingsAvailability();
  const model = useMemo(() => buildSettingsShellModel(availability), [availability]);
  const { shortcuts, maxCount, save } = useSettingsShortcuts();
  const atCap = maxCount > 0 && shortcuts.length >= maxCount;

  const toggle = async (token: SettingsSectionToken) => {
    const next = shortcuts.includes(token)
      ? shortcuts.filter(pinned => pinned !== token)
      : [...shortcuts, token];
    const ok = await save(next);
    if (!ok) toast.error(t('common.error'));
  };

  return (
    <SettingsSection
      value="my-shortcuts"
      title={t('settings.my_shortcuts.title')}
      description={t('settings.my_shortcuts.description')}
      icon={Pin}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        {/* The counter is the one live region: it says how many, and at the
            cap it says why the other boxes are not takeable. */}
        <p className="text-sm font-medium tabular-nums" aria-live="polite">
          {maxCount > 0 &&
            t('settings.my_shortcuts.count', { current: shortcuts.length, max: maxCount })}
          {atCap && (
            <span className="ms-2 font-normal text-muted-foreground">
              {t('settings.my_shortcuts.limit_reached')}
            </span>
          )}
        </p>
        {shortcuts.length === 0 && (
          <p className="text-xs text-muted-foreground">{t('settings.my_shortcuts.empty')}</p>
        )}
      </div>
      <div className="space-y-4">
        {model.map(tab => (
          <section key={tab.tab} aria-label={t(`settings.tabs.${tab.tab}`)}>
            <h4 className="text-xs font-bold uppercase tracking-wider text-primary">
              {t(`settings.tabs.${tab.tab}`)}
            </h4>
            {tab.groups.map(group => {
              const sections = group.sections.filter(
                section => section.token !== MY_SHORTCUTS_TOKEN
              );
              if (sections.length === 0) return null;
              return (
                <div key={group.key} className="mt-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {t(`settings.groups.${group.key}`)}
                  </p>
                  <ul className="mt-1 grid gap-1 sm:grid-cols-2" role="list">
                    {sections.map(section => {
                      const checked = shortcuts.includes(section.token);
                      return (
                        <SectionRow
                          key={section.token}
                          token={section.token}
                          label={t(section.titleKey)}
                          checked={checked}
                          blocked={atCap && !checked}
                          onToggle={() => void toggle(section.token)}
                        />
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </section>
        ))}
      </div>
    </SettingsSection>
  );
}
