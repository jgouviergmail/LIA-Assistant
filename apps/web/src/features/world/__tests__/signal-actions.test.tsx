import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { WorldSignalActions } from '../WorldSignalActions';
import type { PrivateObjectSignal } from '../private-signal-projection';

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const part of key.split('.'))
        value =
          value && typeof value === 'object' && part in value
            ? Reflect.get(value, part)
            : undefined;
      return typeof value === 'string' ? value : key;
    },
  }),
}));
const signals: PrivateObjectSignal[] = [
  { propId: 'desk', kind: 'workboard', count: 1234, status: 'ready', target: null },
  { propId: 'easel', kind: 'images', count: null, status: 'unavailable', target: null },
  { propId: 'phone', kind: 'sms', count: 2, status: 'ready', target: null },
];
it.each([
  ['en', en, '1,234'],
  ['fr', fr, '1 234'],
] as const)('names each marker and formats its count for %s', (lng, copy, count) => {
  const select = vi.fn(() => true);
  render(<WorldSignalActions lng={lng} signals={signals} onSelect={select} />);
  const board = screen.getByRole('button', { name: `${copy.world.signals.workboard} · ${count}` });
  expect(
    screen.getByRole('button', {
      name: `${copy.world.signals.images} · ${copy.world.signals.unavailable}`,
    })
  ).toBeInTheDocument();
  // Notices are read through the phone and the alarm, never listed here.
  expect(screen.getAllByRole('button')).toHaveLength(2);
  fireEvent.click(board);
  expect(select).toHaveBeenCalledExactlyOnceWith('desk');
});
