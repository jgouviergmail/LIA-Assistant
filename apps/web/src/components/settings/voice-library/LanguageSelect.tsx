'use client';

/**
 * The language a recording is spoken in, or a design should speak (ADR-345):
 * « automatic » or one of the interface's six, each under its own name.
 */

import { useId } from 'react';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { languageNames } from '@/i18n/settings';
import type { LibraryLanguage } from '@/types/voice-library';

const LANGUAGES: readonly LibraryLanguage[] = ['en', 'fr', 'de', 'es', 'it', 'zh'];
const AUTO = 'auto';

export interface LanguageSelectProps {
  label: string;
  autoLabel: string;
  value: LibraryLanguage | null;
  onChange: (language: LibraryLanguage | null) => void;
}

export function LanguageSelect({ label, autoLabel, value, onChange }: LanguageSelectProps) {
  const labelId = useId();
  return (
    <div className="space-y-3">
      <Label id={labelId}>{label}</Label>
      <Select
        value={value ?? AUTO}
        onValueChange={next => onChange(LANGUAGES.find(language => language === next) ?? null)}
      >
        <SelectTrigger aria-labelledby={labelId}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={AUTO}>{autoLabel}</SelectItem>
          {LANGUAGES.map(language => (
            <SelectItem key={language} value={language}>
              {languageNames[language].native}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
