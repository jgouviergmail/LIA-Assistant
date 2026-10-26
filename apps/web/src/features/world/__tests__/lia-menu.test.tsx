import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { WorldLiaMenu } from '../WorldLiaMenu';
vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string) => {
      const name = key.slice('world.lia_menu.'.length);
      const labels = lng === 'fr' ? fr.world.lia_menu : en.world.lia_menu;
      return name in labels ? Reflect.get(labels, name) : key;
    },
  }),
}));
it.each(['en', 'fr'] as const)('names LIA’s four local choices in %s', lng => {
  const selected = vi.fn();
  render(<WorldLiaMenu lng={lng} onSelect={selected} />);
  const labels = lng === 'fr' ? fr.world.lia_menu : en.world.lia_menu;
  for (const [key, target] of [
    ['conversation', 'lia'],
    ['journal', 'journals'],
    ['alerts', 'world-alerts'],
    ['psyche', 'psyche'],
  ] as const) {
    fireEvent.click(screen.getByRole('button', { name: labels[key] }));
    expect(selected).toHaveBeenLastCalledWith(target);
  }
});
