'use client';

/**
 * How the station runs by default: whether a model re-reads programmes before
 * they air (every reading is billed, and how many programmes that means is
 * said), when it stops on its own, and whether nothing personal airs
 * (listening in company).
 */
import { Headphones } from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import { timerChoices } from '@/lib/radio/preferences';

import type { RadioFieldsProps } from './fields';

/** The select value that stands for « the instance's default ». */
const DEFAULT_TIMER = 'default';

export function RadioListeningFields({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  // A listener who never chose runs on the instance's default, shown as chosen.
  const verification = preferences.verification ?? options.verification_default;
  const reread = options.verification_checked[verification];
  return (
    <Disclosure
      icon={Headphones}
      title={t('radio.settings.listening.title')}
      description={t('radio.settings.listening.description')}
    >
      <div className="space-y-4">
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">
            {t('radio.settings.listening.verification')}
          </legend>
          <p id="radio-verification-hint" className="text-xs text-muted-foreground">
            {t('radio.settings.listening.verification_hint')}
          </p>
          {options.verification_modes.map(mode => {
            const id = `radio-verification-${mode}`;
            return (
              <div key={mode} className="flex items-center gap-2">
                <input
                  type="radio"
                  id={id}
                  name="radio-verification"
                  value={mode}
                  checked={verification === mode}
                  aria-labelledby={`${id}-label`}
                  aria-describedby="radio-verification-hint"
                  onChange={() => onChange({ ...preferences, verification: mode })}
                  className="h-4 w-4 accent-primary"
                />
                <label id={`${id}-label`} htmlFor={id} className="text-sm">
                  {t(`radio.settings.verification.${mode}`)}
                </label>
              </div>
            );
          })}
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {t('radio.settings.listening.verification_cost', { count: reread.length })}
          </p>
        </fieldset>
        <div className="space-y-3">
          <Label htmlFor="radio-timer">{t('radio.settings.listening.timer')}</Label>
          <Select
            value={
              preferences.timer_minutes === null ? DEFAULT_TIMER : String(preferences.timer_minutes)
            }
            onValueChange={value =>
              onChange({
                ...preferences,
                timer_minutes: value === DEFAULT_TIMER ? null : Number(value),
              })
            }
          >
            <SelectTrigger id="radio-timer" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_TIMER}>
                {t('radio.settings.listening.timer_default', {
                  count: options.timer_default_minutes,
                })}
              </SelectItem>
              {timerChoices(preferences.timer_minutes, options.timer_max_minutes).map(minutes => (
                <SelectItem key={minutes} value={String(minutes)}>
                  {minutes === 0
                    ? t('radio.page.timer_none')
                    : t('radio.page.timer_minutes', { count: minutes })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-1">
            <Label htmlFor="radio-company">{t('radio.settings.listening.company')}</Label>
            <p id="radio-company-hint" className="text-xs text-muted-foreground">
              {t('radio.page.company_description')}
            </p>
          </div>
          <Switch
            id="radio-company"
            aria-describedby="radio-company-hint"
            checked={preferences.public_mode}
            onCheckedChange={value => onChange({ ...preferences, public_mode: value })}
          />
        </div>
      </div>
    </Disclosure>
  );
}
