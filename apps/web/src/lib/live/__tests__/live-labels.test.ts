/**
 * Every outcome a session can end on and every refusal a start can name has a
 * label in every locale. The banner and the card build their keys dynamically
 * (`live.outcome.${outcome}`, `live.error.${code}`), so a value added to the
 * vocabulary without its six sentences renders the raw key with nothing
 * failing. Parity across locales is `task lint:i18n`'s; what parity cannot
 * see is a key that exists nowhere, or a label nothing can reach.
 */
import { describe, expect, it } from 'vitest';

import deDict from '../../../../locales/de/translation.json';
import enDict from '../../../../locales/en/translation.json';
import esDict from '../../../../locales/es/translation.json';
import frDict from '../../../../locales/fr/translation.json';
import itDict from '../../../../locales/it/translation.json';
import zhDict from '../../../../locales/zh/translation.json';

import { LIVE_ERROR_CODES } from '../live-message';
import { LIVE_OUTCOMES, LIVE_RELAY_FATES } from '../types';

const LOCALES: Record<string, Record<string, unknown>> = {
  en: enDict,
  fr: frDict,
  de: deDict,
  es: esDict,
  it: itDict,
  zh: zhDict,
};

function section(locale: Record<string, unknown>, name: 'outcome' | 'error') {
  const live = locale.live as Record<string, unknown>;
  return live[name] as Record<string, string>;
}

/** `live.summary.relay.*`: the fate of a DIRECT session's words, one line each (ADR-301). */
function relaySection(locale: Record<string, unknown>) {
  const live = locale.live as Record<string, unknown>;
  const summary = live.summary as Record<string, unknown>;
  return summary.relay as Record<string, string>;
}

/** The one error key that is not a code: the generic line every unnamed failure falls back to. */
const GENERIC_ERROR_KEY = 'start';

describe('live labels', () => {
  it.each(Object.keys(LOCALES))('%s labels every outcome and every refusal code', locale => {
    const outcomes = section(LOCALES[locale], 'outcome');
    for (const outcome of LIVE_OUTCOMES) {
      expect(outcomes[outcome], `${locale} is missing live.outcome.${outcome}`).toBeTruthy();
    }
    const errors = section(LOCALES[locale], 'error');
    for (const code of LIVE_ERROR_CODES) {
      expect(errors[code], `${locale} is missing live.error.${code}`).toBeTruthy();
    }
    expect(errors[GENERIC_ERROR_KEY]).toBeTruthy();
    // The card formats `live.summary.relay.${fate}` for whatever fate the
    // API wrote — the relay's WHOLE vocabulary, not the four the closing
    // itself can answer: a settle may name any of them.
    const relays = relaySection(LOCALES[locale]);
    for (const fate of LIVE_RELAY_FATES) {
      expect(relays[fate], `${locale} is missing live.summary.relay.${fate}`).toBeTruthy();
    }
  });

  it('carries no relay line nothing can reach', () => {
    const unreachable = Object.keys(relaySection(enDict)).filter(
      key => !(LIVE_RELAY_FATES as readonly string[]).includes(key)
    );
    expect(unreachable).toEqual([]);
  });

  it('carries no label nothing can reach', () => {
    const outcomes = Object.keys(section(enDict, 'outcome')).filter(
      key => !(LIVE_OUTCOMES as readonly string[]).includes(key)
    );
    const errors = Object.keys(section(enDict, 'error')).filter(
      key => key !== GENERIC_ERROR_KEY && !(LIVE_ERROR_CODES as readonly string[]).includes(key)
    );
    expect({ outcomes, errors }).toEqual({ outcomes: [], errors: [] });
  });

  it('translates them, rather than echoing the English', () => {
    const english = section(enDict, 'outcome');
    const french = section(frDict, 'outcome');
    const identical = LIVE_OUTCOMES.filter(outcome => english[outcome] === french[outcome]);
    expect(identical.length).toBeLessThan(LIVE_OUTCOMES.length / 2);
  });
});
