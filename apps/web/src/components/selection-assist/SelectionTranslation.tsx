'use client';
/** The person chooses the target language before any translation is purchased. */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, languages, type Language } from '@/i18n/settings';
import { languageName } from '@/lib/language-name';

export function SelectionTranslation({
  lng,
  limit,
  onTranslate,
}: {
  lng: Language;
  limit: number;
  onTranslate: (language: string) => void;
}) {
  const { t } = useTranslation(lng);
  const [language, setLanguage] = useState('');
  const valid = language.trim().length >= 2 && language.trim().length <= limit;
  return (
    <form
      className="space-y-3"
      onSubmit={event => {
        event.preventDefault();
        event.stopPropagation();
        if (valid) onTranslate(language.trim());
      }}
    >
      <Input
        label={t('selectionAssist.target_language')}
        value={language}
        maxLength={limit}
        onChange={event => setLanguage(event.target.value)}
      />
      <div className="flex flex-wrap gap-1">
        {languages.map(code => {
          const name = languageName(code, getIntlLocale(lng));
          return (
            <Button
              key={code}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setLanguage(name)}
            >
              {name}
            </Button>
          );
        })}
      </div>
      <Button type="submit" aria-disabled={!valid}>
        {t('selectionAssist.send')}
      </Button>
    </form>
  );
}
