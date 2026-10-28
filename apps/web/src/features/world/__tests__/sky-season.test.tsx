import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldSkyBadge } from '../WorldSkyBadge';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
it('adds the current season after the phase without inventing a season for a stale clock', () => {
  const atmosphere = {
    ...NEUTRAL_ATMOSPHERE,
    phase: 'noon' as const,
    time: Date.UTC(2026, 9, 27, 11, 54),
    timezone: 'Europe/Paris',
  };
  const ui = render(<WorldSkyBadge lng="fr" atmosphere={atmosphere} />);
  expect(screen.getByText(/world.atmosphere.noon/).parentElement).toHaveTextContent(
    'world.seasons.autumn'
  );
  ui.rerender(<WorldSkyBadge lng="fr" atmosphere={NEUTRAL_ATMOSPHERE} />);
  expect(screen.queryByText(/world.seasons/)).not.toBeInTheDocument();
});
