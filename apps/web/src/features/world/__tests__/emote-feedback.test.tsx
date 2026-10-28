import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { WorldEmoteFeedback, EMOTE_FEEDBACK_MS } from '../WorldEmoteFeedback';
import { WorldEmoteAnnouncements } from '../WorldEmoteAnnouncements';

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string, values?: Record<string, unknown>) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const part of key.split('.'))
        value =
          value && typeof value === 'object' && part in value
            ? Reflect.get(value, part)
            : undefined;
      if (typeof value !== 'string') return key;
      return value.replace(/{{(\w+)}}/g, (_, name: string) => String(values?.[name] ?? ''));
    },
  }),
}));
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it.each([
  ['en', en],
  ['fr', fr],
] as const)('says a refused gesture in %s, withdraws it, and says a repeat again', (lng, copy) => {
  const view = render(<WorldEmoteFeedback lng={lng} feedback={null} />);
  const region = screen.getByRole('status');
  expect(region).toBeEmptyDOMElement();
  view.rerender(<WorldEmoteFeedback lng={lng} feedback={{ result: 'rate_limited', serial: 1 }} />);
  expect(region).toHaveTextContent(copy.world.emotes.rate_limited);
  expect(screen.getByRole('status')).toBe(region);
  act(() => vi.advanceTimersByTime(EMOTE_FEEDBACK_MS));
  expect(region).toBeEmptyDOMElement();
  view.rerender(<WorldEmoteFeedback lng={lng} feedback={{ result: 'rate_limited', serial: 2 }} />);
  expect(region).toHaveTextContent(copy.world.emotes.rate_limited);
  view.rerender(<WorldEmoteFeedback lng={lng} feedback={{ result: 'unavailable', serial: 3 }} />);
  expect(region).toHaveTextContent(copy.world.emotes.unavailable);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
it.each([
  ['en', 'Léa waves'],
  ['fr', 'Léa salue'],
] as const)('announces a peer gesture as a translated sentence in %s', (lng, sentence) => {
  render(
    <WorldEmoteAnnouncements
      lng={lng}
      gestures={[{ id: 'peer', alias: 'Léa', serial: 1, kind: 'wave' }]}
    />
  );
  expect(screen.getByText(sentence)).toHaveAttribute('data-world-emote', 'wave');
  expect(screen.getByRole('status')).toHaveTextContent(sentence);
});
