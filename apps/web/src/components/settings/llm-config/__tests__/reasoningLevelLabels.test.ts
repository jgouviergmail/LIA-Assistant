/**
 * Every ladder level the API can offer must have a label in every locale.
 *
 * The dropdown builds its keys dynamically —
 * `settings.admin.llmConfig.reasoningLevels.${level}` — so a level added to
 * the backend ladder without a translation renders the raw key to the admin,
 * in six languages, with nothing failing. Key PARITY across locales is already
 * enforced by `task lint:i18n`; what parity cannot see is a key that exists
 * nowhere at all.
 */
import { describe, expect, it } from 'vitest';

import deDict from '../../../../../locales/de/translation.json';
import enDict from '../../../../../locales/en/translation.json';
import esDict from '../../../../../locales/es/translation.json';
import frDict from '../../../../../locales/fr/translation.json';
import itDict from '../../../../../locales/it/translation.json';
import zhDict from '../../../../../locales/zh/translation.json';
import { REASONING_LEVELS } from '@/types/llm-config';

const LOCALES: Record<string, Record<string, unknown>> = {
  en: enDict,
  fr: frDict,
  de: deDict,
  es: esDict,
  it: itDict,
  zh: zhDict,
};

function levelLabels(locale: Record<string, unknown>): Record<string, string> {
  const settings = locale.settings as Record<string, unknown>;
  const admin = settings.admin as Record<string, unknown>;
  const llmConfig = admin.llmConfig as Record<string, unknown>;
  return llmConfig.reasoningLevels as Record<string, string>;
}

describe('reasoning level labels', () => {
  it.each(Object.keys(LOCALES))('%s labels every level of the ladder', locale => {
    const labels = levelLabels(LOCALES[locale]);
    for (const level of REASONING_LEVELS) {
      expect(labels[level], `${locale} is missing ${level}`).toBeTruthy();
    }
  });

  it('publishes no label for a level the ladder does not carry', () => {
    // A leftover label is a level the API stopped accepting — the mirror of
    // the missing one, and just as invisible.
    const extra = Object.keys(levelLabels(enDict)).filter(
      key => !(REASONING_LEVELS as readonly string[]).includes(key)
    );
    expect(extra).toEqual([]);
  });

  it('translates them, rather than echoing the English', () => {
    // A locale that copied the English wholesale is a locale nobody filled in.
    const english = levelLabels(enDict);
    const french = levelLabels(frDict);
    const identical = REASONING_LEVELS.filter(level => english[level] === french[level]);
    expect(identical.length).toBeLessThan(REASONING_LEVELS.length / 2);
  });
});
