import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldSoundWidget } from '../WorldSoundWidget';
import type { Language } from '@/i18n/settings';
import fr from '../../../../locales/fr/translation.json';
import en from '../../../../locales/en/translation.json';
vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string) => {
      const table = lng === 'fr' ? fr.world.sound : en.world.sound;
      return table[key.split('.').at(-1) as keyof typeof table] ?? key;
    },
  }),
}));
function Harness({ lng }: { lng: Language }) {
  const [enabled, setEnabled] = useState(false);
  const [volume, setVolume] = useState(1);
  return (
    <WorldSoundWidget
      lng={lng}
      sound={{ enabled, volume, setVolume, failed: false, toggle: () => setEnabled(v => !v) }}
    />
  );
}
it.each(['fr', 'en'] as const)(
  'offers independent mute and volume controls in a named panel in %s',
  lng => {
    render(<Harness lng={lng} />);
    const text = lng === 'fr' ? fr.world.sound : en.world.sound;
    fireEvent.click(screen.getByRole('button', { name: text.settings }));
    expect(screen.getByRole('dialog', { name: text.settings })).toBeVisible();
    const slider = screen.getByRole('slider', { name: text.volume });
    expect(slider).toHaveAttribute('aria-valuenow', '100');
    fireEvent.keyDown(slider, { key: 'Home' });
    expect(slider).toHaveAttribute('aria-valuenow', '0');
    // Volume changes never opt the user into playback.
    expect(screen.getByRole('button', { name: text.enable })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    fireEvent.click(screen.getByRole('button', { name: text.enable }));
    expect(screen.getByRole('button', { name: text.disable })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(slider).toHaveAttribute('aria-valuenow', '1');
    fireEvent.click(screen.getByRole('button', { name: text.disable }));
    expect(slider).toHaveAttribute('aria-valuenow', '1');
  }
);
