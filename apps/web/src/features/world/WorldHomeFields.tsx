'use client';

import { useId } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { HOME_PALETTES } from './home-catalogue';
import type { HomeEdit } from './home-protocol';

const SWATCHES: Record<(typeof HOME_PALETTES)[number], string> = {
  auto: 'linear-gradient(135deg, #538675 0 33%, #4a889e 33% 66%, #cd8555 66%)',
  sage: '#648f69',
  teal: '#287f83',
  clay: '#c77559',
  violet: '#8163ac',
  amber: '#d4a044',
  cream: '#e5d5ad',
};

export function WorldHomeFields({
  lng,
  value,
  onChange,
  disabled = false,
}: {
  lng: Language;
  value: HomeEdit;
  onChange(value: HomeEdit): void;
  disabled?: boolean;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className="text-sm font-medium">{t('world.home.palette')}</legend>
      <div className="grid grid-cols-2 gap-2">
        {HOME_PALETTES.map(palette => (
          <label
            key={palette}
            htmlFor={id + '-' + palette}
            className={
              'world-palette-choice ' + (value.palette === palette ? 'world-palette-selected' : '')
            }
          >
            <input
              id={id + '-' + palette}
              type="radio"
              aria-label={t('world.home.palettes.' + palette)}
              name={id + '-palette'}
              value={palette}
              checked={value.palette === palette}
              disabled={disabled}
              onChange={() => onChange({ palette })}
              className="size-4 shrink-0 accent-primary"
            />
            <span
              className="size-6 shrink-0 rounded-md border"
              aria-hidden="true"
              style={{ background: SWATCHES[palette] }}
            />
            <span className="min-w-0 text-sm">{t('world.home.palettes.' + palette)}</span>
          </label>
        ))}
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t('world.home.colours_hint')}
      </p>
    </fieldset>
  );
}
