'use client';

import { Eclipse, Monitor, Moon, Sun } from 'lucide-react';

import { Switch } from '@/components/ui/switch';
import { useThemeMode } from '@/hooks/useThemeMode';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import type { DisplayMode } from '@/lib/theme-mode';

/**
 * Display mode (light / dark / system) plus the OLED refinement.
 *
 * Why this exists at all: the header's circular toggle deliberately offers
 * three predictable stops and drops `system` — but `system` is the column's
 * `server_default`, so it is where EVERY account starts. Without a control that
 * can return to it, one press of the header toggle would lose it for good.
 *
 * OLED is offered only under an EXPLICIT dark mode, never under `system`
 * resolving to dark. `users.theme` stores `'oled'` to mean "dark, with OLED",
 * so a `system + OLED` pair has nowhere to live; enabling it from `system`
 * would have to silently pin the user to dark. Disabling the switch and saying
 * why is honest — silently changing a different setting is not.
 */
const MODES: ReadonlyArray<{ name: DisplayMode; Icon: typeof Sun }> = [
  { name: 'light', Icon: Sun },
  { name: 'dark', Icon: Moon },
  { name: 'system', Icon: Monitor },
];

export function DisplayModeSelector({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { mounted, mode, oled, apply } = useThemeMode();

  // OLED needs `.dark` on <html> to render at all, and needs an explicit dark
  // mode to be persistable. Both conditions collapse to this one.
  const oledAvailable = mode === 'dark';

  if (!mounted) {
    return <div className="h-24 animate-pulse rounded-lg bg-muted" aria-hidden="true" />;
  }

  return (
    <div className="space-y-4">
      {/* Native radios: the browser gives arrow-key navigation, roving focus and
          the group semantics for free. The inputs are visually hidden and the
          <label> carries the styling, so the whole card stays the hit target. */}
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-foreground">
          {t('settings.theme.mode_label')}
        </legend>
        <div className="grid grid-cols-3 gap-2">
          {MODES.map(({ name, Icon }) => {
            const selected = mode === name;
            return (
              <label
                key={name}
                className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border-2 p-3 text-center transition-all hover:bg-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background ${
                  selected ? 'border-primary bg-primary/5' : 'border-border bg-card'
                }`}
              >
                <input
                  type="radio"
                  name="display-mode"
                  value={name}
                  checked={selected}
                  onChange={() => apply({ mode: name, oled: name === 'dark' && oled })}
                  // aria-labelledby, same rationale as the auth forms (F012):
                  // the wrapping <label> really does name this input, but
                  // static analysis cannot resolve a name that lives two
                  // elements down behind a `t()` call. The explicit reference
                  // makes the accessible name verifiable instead of assumed.
                  aria-labelledby={`display-mode-${name}-label`}
                  className="sr-only"
                />
                <Icon
                  className={`h-5 w-5 ${selected ? 'text-primary' : 'text-muted-foreground'}`}
                  aria-hidden="true"
                />
                <span
                  id={`display-mode-${name}-label`}
                  className={`text-xs font-medium ${selected ? 'text-primary' : 'text-foreground'}`}
                >
                  {t(`settings.theme.${name}`)}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-card p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Eclipse className="h-4 w-4 text-primary" aria-hidden="true" />
            <span id="oled-label" className="text-sm font-medium text-foreground">
              {t('settings.theme.oled')}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {oledAvailable
              ? t('settings.theme.oled_description')
              : t('settings.theme.oled_requires_dark')}
          </p>
        </div>
        <Switch
          checked={oled && oledAvailable}
          disabled={!oledAvailable}
          onCheckedChange={checked => apply({ mode: 'dark', oled: checked })}
          aria-labelledby="oled-label"
        />
      </div>
    </div>
  );
}
