'use client';

import { useId } from 'react';
import { Clock, Eclipse, Monitor, Moon, Sun } from '@/lib/icons';

import { useThemeMode } from '@/hooks/useThemeMode';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import type { DisplayMode } from '@/lib/theme-mode';
import { ThemeScheduleEditor } from './ThemeScheduleEditor';
import { Button } from '@/components/ui/button';

/**
 * Manual, operating-system and civil-time display choices.
 *
 * Why this exists at all: the header's circular toggle deliberately offers
 * three predictable stops and drops `system` — but `system` is the column's
 * `server_default`, so it is where EVERY account starts. Without a control that
 * can return to it, one press of the header toggle would lose it for good.
 *
 * `users.theme` stores 'oled' as explicit dark mode with absolute black.
 */
const MODES: ReadonlyArray<{ name: DisplayMode | 'oled'; Icon: typeof Sun }> = [
  { name: 'light', Icon: Sun },
  { name: 'dark', Icon: Moon },
  { name: 'oled', Icon: Eclipse },
  { name: 'system', Icon: Monitor },
  { name: 'auto', Icon: Clock },
];

export function DisplayModeSelector({ lng }: { lng: Language }) {
  const groupId = useId();
  const { t } = useTranslation(lng);
  const { mounted, mode, oled, apply, schedule, setSchedule, saving, saveError, retrySave } =
    useThemeMode();

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
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {MODES.map(({ name, Icon }) => {
            const selected =
              name === 'oled'
                ? mode === 'dark' && oled
                : mode === name && (name !== 'dark' || !oled);
            return (
              <label
                key={name}
                className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border-2 p-3 text-center transition-all hover:bg-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background ${
                  selected ? 'border-primary bg-primary/5' : 'border-border bg-background'
                }`}
              >
                <input
                  type="radio"
                  name={groupId}
                  value={name}
                  checked={selected}
                  onChange={() =>
                    apply({ mode: name === 'oled' ? 'dark' : name, oled: name === 'oled' })
                  }
                  // aria-labelledby, same rationale as the auth forms (F012):
                  // the wrapping <label> really does name this input, but
                  // static analysis cannot resolve a name that lives two
                  // elements down behind a `t()` call. The explicit reference
                  // makes the accessible name verifiable instead of assumed.
                  aria-labelledby={`${groupId}-${name}-label`}
                  className="sr-only"
                />
                <Icon
                  className={`h-5 w-5 ${selected ? 'text-primary' : 'text-muted-foreground'}`}
                  aria-hidden="true"
                />
                <span
                  id={`${groupId}-${name}-label`}
                  className={`text-xs font-medium ${selected ? 'text-primary' : 'text-foreground'}`}
                >
                  {t(`settings.theme.${name}`)}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
      {mode === 'auto' && (
        <ThemeScheduleEditor
          lng={lng}
          schedule={schedule}
          setSchedule={setSchedule}
          saving={saving}
        />
      )}
      {saveError && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-destructive">
            {t('settings.theme.save_error')}
          </p>
          <Button
            type="button"
            variant="outline"
            aria-disabled={saving}
            onClick={() => {
              if (!saving) void retrySave();
            }}
          >
            {t('common.retry')}
          </Button>
        </div>
      )}
    </div>
  );
}
