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
import { CosmosHero } from '../CosmosHero';

const variantMock = vi.mocked(getPublicShowroomVariant);

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

  it('offers the star call to action toward the repository', async () => {
    variantMock.mockReturnValue('guided');
    const { getByTestId } = render(await CosmosHero({ lng: 'fr' }));
    const star = getByTestId('hero-cta-star');
    // GitHub exposes no auto-star URL: the honest maximum is landing the
    // visitor on the repo, where the star control is one click away.
    expect(star.getAttribute('href')).toMatch(/^https:\/\/github\.com\//);
    expect(star.getAttribute('target')).toBe('_blank');
    expect(star).toHaveTextContent('landing.hero.cta_star');
  });
});
