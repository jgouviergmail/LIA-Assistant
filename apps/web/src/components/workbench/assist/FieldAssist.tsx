'use client';

/**
 * FieldAssist — writing with LIA beside a free text field of the Tools (ADR-372).
 *
 * It stands in the field's own label line, so the form gains no height. Empty, the field is written
 * from an instruction; filled, its words can be changed or translated, what is proposed only
 * replacing them if the person says so. Past the published bound nothing is offered: the words
 * could not be sent.
 */
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WritingKind } from '@/lib/workbench/assist';

import { useAssistBounds } from '../WorkbenchShell';
import { rewriteLines, translateLine, writeLine } from './writingLines';
import { WritingAssist, type WritingUse } from './WritingAssist';

export interface FieldAssistProps {
  lng: Language;
  /** What the field is for. */
  kind: WritingKind;
  /** What the field holds. */
  value: string;
  onChange: (value: string) => void;
}

/** @returns What the field holds once the proposal joined it. */
export function joinedWords(value: string, words: string, use: WritingUse): string {
  return use === 'add' && value.trim() ? `${value.trimEnd()}\n\n${words}` : words;
}

export function FieldAssist({ lng, kind, value, onChange }: FieldAssistProps) {
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const own = value.trim();
  if (!bounds || own.length > bounds.textMax) return null;
  return (
    <WritingAssist
      lng={lng}
      compact
      lines={own ? [...rewriteLines(t, own), translateLine(t, lng, own)] : [writeLine(t, kind)]}
      blank={!own}
      maxInstruction={bounds.instructionMax}
      onApply={(answer, use) => onChange(joinedWords(value, answer.text, use))}
      onDictated={bounds.dictates ? words => onChange(joinedWords(value, words, 'add')) : undefined}
    />
  );
}
