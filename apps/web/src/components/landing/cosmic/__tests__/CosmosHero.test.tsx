/**
 * Hero contract — the guided-demo call to action (P0 showroom program).
 *
 * The CTA must appear ONLY when `/demo` actually serves the guided mission.
 * Under `legacy` that page is a passive mockup, so advertising a demo would
 * overpromise: the link must be absent from the DOM, not merely hidden.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/i18n', () => ({
  initI18next: async () => ({ t: (key: string) => key }),
}));
vi.mock('../Planetarium', () => ({
  Planetarium: () => <div data-testid="planetarium" />,
}));
vi.mock('../../InteractiveChatMockup', () => ({
  InteractiveChatMockup: () => <div data-testid="chat-mockup" />,
}));
vi.mock('../TrustStat', () => ({
  TrustStat: ({ label }: { label: string }) => <span>{label}</span>,
}));
vi.mock('@/lib/showroom-config', () => ({
  getPublicShowroomVariant: vi.fn(() => 'legacy'),
}));

import { getPublicShowroomVariant } from '@/lib/showroom-config';
import { LANDING_PLANETARIUM_ENABLED } from '../../constants';
import { CosmosHero } from '../CosmosHero';

const variantMock = vi.mocked(getPublicShowroomVariant);

describe('CosmosHero — the planetarium switch', () => {
  it('mounts no planetarium while the switch is off, and reserves no orbit zone for it', async () => {
    const { queryByTestId, getByTestId, container } = render(
      await CosmosHero({ lng: 'fr', planetarium: false })
    );
    expect(queryByTestId('planetarium')).not.toBeInTheDocument();
    expect(getByTestId('chat-mockup')).toBeInTheDocument();
    expect(container.querySelector('.cosmos-orbit-zone')).not.toBeInTheDocument();
  });

  it('mounts the planetarium around the mockup while the switch is on', async () => {
    const { getByTestId, container } = render(await CosmosHero({ lng: 'fr', planetarium: true }));
    expect(getByTestId('planetarium')).toBeInTheDocument();
    expect(getByTestId('chat-mockup')).toBeInTheDocument();
    expect(container.querySelector('.cosmos-orbit-zone')).toBeInTheDocument();
  });

  it('follows the landing switch by default', async () => {
    const { queryByTestId } = render(await CosmosHero({ lng: 'fr' }));
    expect(queryByTestId('planetarium') !== null).toBe(LANDING_PLANETARIUM_ENABLED);
  });
});

describe('CosmosHero — guided demo CTA', () => {
  beforeEach(() => {
    variantMock.mockReset();
  });

  it('exposes a localized /demo link when the guided mission is served', async () => {
    variantMock.mockReturnValue('guided');
    const { getByTestId } = render(await CosmosHero({ lng: 'fr' }));

    const link = getByTestId('hero-cta-demo');
    expect(link).toBeInTheDocument();
    expect(link.getAttribute('href')).toContain('/demo');
    expect(link).toHaveTextContent('landing.hero.cta_demo');
  });

  it('renders no demo link at all under the legacy variant', async () => {
    variantMock.mockReturnValue('legacy');
    const { queryByTestId, container } = render(await CosmosHero({ lng: 'fr' }));

    expect(queryByTestId('hero-cta-demo')).not.toBeInTheDocument();
    const demoLinks = Array.from(container.querySelectorAll('a[href*="/demo"]'));
    expect(demoLinks).toHaveLength(0);
  });

  it('keeps the other hero calls to action in both variants', async () => {
    for (const variant of ['guided', 'legacy'] as const) {
      variantMock.mockReturnValue(variant);
      const { container, unmount } = render(await CosmosHero({ lng: 'fr' }));
      expect(container.querySelector('a[href*="/register"]')).toBeInTheDocument();
      expect(container.querySelector('a[href^="https://github.com/"]')).toBeInTheDocument();
      unmount();
    }
  });

  it('keeps the GitHub link without a redundant Star action', async () => {
    variantMock.mockReturnValue('guided');
    const { queryByTestId, container } = render(await CosmosHero({ lng: 'fr' }));
    expect(queryByTestId('hero-cta-star')).not.toBeInTheDocument();
    expect(container.querySelector('a[href^="https://github.com/"]')).toBeInTheDocument();
  });
});
