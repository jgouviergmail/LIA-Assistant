/**
 * The lines of writing with LIA (ADR-372), for any field a person writes in.
 *
 * On words already written: a change or a translation. On an empty field: a text from an
 * instruction, the field's kind saying what it is for. The server reads these words as data.
 */
import {
  Briefcase,
  Languages,
  PenLine,
  Scissors,
  Smile,
  SpellCheck,
  type LucideIcon,
} from '@/lib/icons';

import type { Language } from '@/i18n/settings';
import { getIntlLocale, languages } from '@/i18n/settings';
import { languageName } from '@/lib/language-name';
import { ASSIST_PATHS, type RewriteTone, type WritingKind } from '@/lib/workbench/assist';

import type { Say } from './lines';
import type { WritingLine } from './WritingAssist';

const TONES: readonly { tone: RewriteTone; icon: LucideIcon }[] = [
  { tone: 'fix', icon: SpellCheck },
  { tone: 'shorter', icon: Scissors },
  { tone: 'formal', icon: Briefcase },
  { tone: 'warm', icon: Smile },
];

/** @returns The changes a person can ask of words already written. */
export function rewriteLines(t: Say, text: string): readonly WritingLine[] {
  return TONES.map(({ tone, icon }) => ({
    key: tone,
    label: t(`workbench.assist.writing.tones.${tone}`),
    icon,
    path: ASSIST_PATHS.textRewrite,
    body: () => ({ text, tone }),
  }));
}

/** The app's other languages, in the reader's words. */
function otherLanguages(lng: Language): readonly string[] {
  return languages.filter(code => code !== lng).map(code => languageName(code, getIntlLocale(lng)));
}

/** @returns The translation of words already written, into the language the person names. */
export function translateLine(t: Say, lng: Language, text: string): WritingLine {
  return {
    key: 'translate',
    label: t('workbench.assist.writing.translate'),
    icon: Languages,
    path: ASSIST_PATHS.textTranslate,
    body: language => ({ text, language }),
    instruction: 'required',
    instructionLabel: t('workbench.assist.writing.to_language'),
    suggestions: otherLanguages(lng),
  };
}

/** @returns A text written from an instruction, for an empty field of this kind. */
export function writeLine(t: Say, kind: WritingKind): WritingLine {
  return {
    key: 'write',
    label: t('workbench.assist.writing.write'),
    icon: PenLine,
    path: ASSIST_PATHS.textWrite,
    body: instruction => ({ kind, instruction }),
    instruction: 'required',
  };
}
