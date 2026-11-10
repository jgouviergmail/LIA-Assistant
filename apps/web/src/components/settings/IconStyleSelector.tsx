'use client';

import { useId } from 'react';
import { Calendar, Home, MessageSquare } from '@/lib/icons';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';
import { useIconStyleSettings } from './IconStyleProvider';

export function IconStyleSelector({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { style, selectStyle, saving, failed, retry } = useIconStyleSettings();
  const id = useId();
  return (
    <fieldset className="space-y-3" aria-busy={saving}>
      <legend className="text-sm font-medium">{t('settings.theme.icons.title')}</legend>
      <p className="text-xs text-muted-foreground">{t('settings.theme.icons.description')}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {ICON_STYLES.map(option => (
          <label
            key={option}
            className={`flex cursor-pointer items-center gap-3 rounded-lg border-2 p-3 sm:flex-col has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background ${style === option ? 'border-primary bg-primary/5' : 'border-border bg-background'}`}
          >
            <input
              type="radio"
              name={`${id}-icon-style`}
              value={option}
              checked={style === option}
              onChange={() => selectStyle(option)}
              aria-labelledby={`${id}-${option}`}
              className="sr-only"
            />
            <IconStyleContext.Provider value={option}>
              <span className="flex gap-2 text-primary" aria-hidden="true">
                <MessageSquare size={22} />
                <Home size={22} />
                <Calendar size={22} />
              </span>
            </IconStyleContext.Provider>
            <span id={`${id}-${option}`} className="text-sm font-medium">
              {t(`settings.theme.icons.${option}`)}
            </span>
          </label>
        ))}
      </div>
      <p role="status" className="text-xs text-muted-foreground">
        {t(saving ? 'settings.theme.icons.saving' : 'settings.theme.icons.saved_on_account')}
      </p>
      {failed && (
        <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <span>{t('settings.theme.icons.save_failed')}</span>
          <button type="button" onClick={retry} className="underline underline-offset-2">
            {t('common.retry')}
          </button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {t('settings.theme.icons.credits')}{' '}
        <a
          href="https://github.com/microsoft/fluentui-system-icons"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          Microsoft Fluent (MIT)
        </a>
        {' · '}
        <a
          href="https://www.streamlinehq.com"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          Streamline (CC BY 4.0)
        </a>
        {' · '}
        {t('settings.theme.icons.adaptations')}
        {' · '}
        <a href="/icon-licenses.txt" target="_blank" rel="noreferrer" className="underline">
          {t('settings.theme.icons.licenses')}
        </a>
      </p>
    </fieldset>
  );
}
