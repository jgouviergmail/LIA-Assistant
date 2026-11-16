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
vi.mock('../../InteractiveChatMockup', () => ({
  InteractiveChatMockup: () => <div data-testid="chat-mockup" />,
}));
vi.mock('@/lib/showroom-config', () => ({
  getPublicShowroomVariant: vi.fn(() => 'legacy'),
}));

import { getPublicShowroomVariant } from '@/lib/showroom-config';
import { CosmosHero } from '../CosmosHero';

const variantMock = vi.mocked(getPublicShowroomVariant);

describe('CosmosHero — a promise, then the positioning (owner, 2026-11-15)', () => {
  it('leaves the bricks to the living map: no constellation, no demo on the home hero', async () => {
    const { queryByRole, queryByTestId, container } = render(await CosmosHero({ lng: 'fr' }));
    expect(queryByTestId('chat-mockup')).not.toBeInTheDocument();
    expect(container.querySelector('.cosmos-orbit-zone')).not.toBeInTheDocument();
    expect(container.querySelector('.landing-constellation')).not.toBeInTheDocument();
    expect(queryByRole('searchbox')).not.toBeInTheDocument();
  });

  it('points its scroll hint at the positioning that follows it', async () => {
    const { getByRole } = render(await CosmosHero({ lng: 'fr' }));
    expect(getByRole('link', { name: 'landing.hero.scroll_hint' })).toHaveAttribute(
      'href',
      '#positioning'
    );
  });
});

describe('CosmosHero — promise and registration note', () => {
  it('states the tagline alone under the title (owner, 2026-11-15)', async () => {
    const { getByText, queryByText } = render(await CosmosHero({ lng: 'fr' }));
    const tagline = getByText('landing.hero.subtitle_top').closest('p');
    expect(tagline).not.toBeNull();
    expect(tagline).toHaveTextContent(/^landing\.hero\.subtitle_top$/);
    expect(queryByText('landing.hero.home_value')).not.toBeInTheDocument();
  });

  it('states the registration conditions under the three proof items', async () => {
    const { getByText } = render(await CosmosHero({ lng: 'fr' }));
    const note = getByText('landing.hero.home_access_note');
    for (const proof of ['proof_origin', 'proof_accounts', 'proof_control']) {
      expect(getByText(`landing.hero.${proof}`).compareDocumentPosition(note)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING
      );
    }
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
    expect(link).toHaveTextContent('landing.hero.home_cta_demo');
  });

  it('renders no demo link at all under the legacy variant', async () => {
    variantMock.mockReturnValue('legacy');
    const { queryByTestId, container } = render(await CosmosHero({ lng: 'fr' }));

    expect(queryByTestId('hero-cta-demo')).not.toBeInTheDocument();
    const demoLinks = Array.from(container.querySelectorAll('a[href*="/demo"]'));
    expect(demoLinks).toHaveLength(0);
  });

  it('offers presentation and source code, without the neighboring registration CTA', async () => {
    for (const variant of ['guided', 'legacy'] as const) {
      variantMock.mockReturnValue(variant);
      const { container, unmount } = render(await CosmosHero({ lng: 'fr' }));
      expect(container.querySelector('a[href*="/register"]')).not.toBeInTheDocument();
      expect(container.querySelector('[data-testid="hero-cta-presentation"]')).toBeInTheDocument();
      expect(container.querySelector('a[href^="https://github.com/"]')).toBeInTheDocument();
      unmount();
    }
  });

  it('places presentation before the guided demonstration', async () => {
    variantMock.mockReturnValue('guided');
    const { getByTestId } = render(await CosmosHero({ lng: 'fr' }));
    expect(
      getByTestId('hero-cta-presentation').compareDocumentPosition(getByTestId('hero-cta-demo'))
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('keeps the GitHub link without a redundant Star action', async () => {
    variantMock.mockReturnValue('guided');
    const { queryByTestId, container } = render(await CosmosHero({ lng: 'fr' }));
    expect(queryByTestId('hero-cta-star')).not.toBeInTheDocument();
    expect(container.querySelector('a[href^="https://github.com/"]')).toBeInTheDocument();
  });
});
