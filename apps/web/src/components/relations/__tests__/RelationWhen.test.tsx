/**
 * RelationWhen — how long ago AND when, through the REAL translations.
 *
 * The suite-wide i18n mock echoes keys and renders `<Trans>` as its children,
 * so it could never show that the six phrases interpolate and bold the right
 * parts. This file runs real i18next on the real locale files instead.
 */

import { render } from '@testing-library/react';
import { createInstance, type i18n as I18n } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import enDict from '../../../../locales/en/translation.json';
import frDict from '../../../../locales/fr/translation.json';
import zhDict from '../../../../locales/zh/translation.json';
import { RelationWhen } from '../RelationWhen';

vi.unmock('react-i18next');

const DICTIONARIES = { en: enDict, fr: frDict, zh: zhDict };
const NOW = new Date('2026-08-05T12:00:00Z');

async function i18nFor(lng: keyof typeof DICTIONARIES): Promise<I18n> {
  const instance = createInstance();
  await instance.use(initReactI18next).init({
    lng,
    resources: { [lng]: { translation: DICTIONARIES[lng] } },
    interpolation: { escapeValue: false },
  });
  return instance;
}

async function renderWhen(
  lng: keyof typeof DICTIONARIES,
  start: string | null,
  end: string | null = null
) {
  const i18n = await i18nFor(lng);
  return render(
    <I18nextProvider i18n={i18n}>
      <RelationWhen start={start} end={end} />
    </I18nextProvider>
  );
}

function strongTexts(container: HTMLElement): string[] {
  return [...container.querySelectorAll('strong')].map(node => node.textContent ?? '');
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe('RelationWhen', () => {
  it('says how long ago and when, both in bold', async () => {
    const { container } = await renderWhen('fr', '2026-08-02T12:00:00Z');

    expect(container.textContent).toMatch(/^il y a 3 j le dimanche 2 août 2026, \d{2}:\d{2}$/);
    const [amount, moment] = strongTexts(container);
    expect(amount).toBe('3 j');
    expect(moment).toMatch(/^dimanche 2 août 2026, \d{2}:\d{2}$/);
  });

  it('reads an upcoming slot as ahead, with both clocks', async () => {
    const { container } = await renderWhen('fr', '2026-08-08T08:00:00Z', '2026-08-08T09:30:00Z');

    // The dash sits between narrow no-break spaces: a slot never wraps.
    expect(container.textContent).toMatch(
      /^dans 2 j le samedi 8 août 2026, \d{2}:\d{2}\s–\s\d{2}:\d{2}$/
    );
  });

  it('says "just now" for the current minute, with no amount', async () => {
    const { container } = await renderWhen('fr', '2026-08-05T11:59:40Z');

    expect(container.textContent).toMatch(/^à l’instant, le mercredi 5 août 2026, /);
    expect(strongTexts(container)).toHaveLength(2);
  });

  it('follows the reader language', async () => {
    const english = await renderWhen('en', '2026-08-02T12:00:00Z');
    expect(english.container.textContent).toMatch(/^3 d ago, on Sunday, Aug 2, 2026, /);

    const chinese = await renderWhen('zh', '2026-08-02T12:00:00Z');
    expect(chinese.container.textContent).toMatch(/^3 天前，2026年8月2日星期日/);
  });

  it('renders nothing without a readable instant', async () => {
    expect((await renderWhen('fr', null)).container.textContent).toBe('');
    expect((await renderWhen('fr', 'pas une date')).container.textContent).toBe('');
  });
});
