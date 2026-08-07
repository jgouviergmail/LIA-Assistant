/**
 * Mission picker + page-level binding (GuidedShowroom).
 *
 * What must hold:
 * - the picker lists every registered mission as a real button carrying its
 *   translated title, tagline and mechanism badge;
 * - selecting a mission mounts it (keyed remount) and the utility row leads
 *   back to the picker;
 * - `demo_viewed` fires exactly once per page mount (StrictMode-safe),
 *   whatever the visitor picks — mission starts stay per-mission events;
 * - switching missions gives a fresh state machine (no leaked decisions).
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { GuidedShowroom } from '@/components/showroom/GuidedShowroom';
import { SHOWROOM_MISSIONS } from '@/components/showroom/missions';

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true, // reduced motion: deterministic walkthrough
}));

vi.mock('@/components/showroom/ShowroomRichResponse', () => ({
  ShowroomRichResponse: ({ html }: { html: string }) => (
    <div data-testid="showroom-rich-response" data-html={html} />
  ),
}));

const trackSpy = vi.fn();
vi.mock('@/lib/product-telemetry', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/product-telemetry')>();
  return {
    ...actual,
    trackShowroomEvent: (event: string) => trackSpy(event),
  };
});

describe('GuidedShowroom', () => {
  afterEach(() => {
    trackSpy.mockClear();
  });

  it('lists every registered mission with title, tagline and mechanism', () => {
    renderWithProviders(<GuidedShowroom lng="fr" />);
    expect(screen.getByRole('heading', { name: 'showroom.title' })).toBeInTheDocument();
    // A way back to the landing, as a FULL navigation (plain <a>, never a
    // client-side Link: /demo skips auth hydration on purpose).
    const home = screen.getByTestId('showroom-back-home');
    expect(home.tagName).toBe('A');
    // fr is the default locale: no prefix (middleware prefixDefault: false).
    expect(home.getAttribute('href')).toBe('/');
    for (const mission of SHOWROOM_MISSIONS) {
      const card = screen.getByTestId(`showroom-pick-${mission.id}`);
      expect(card.tagName).toBe('BUTTON');
      expect(card).toHaveTextContent(mission.titleKey);
      expect(card).toHaveTextContent(mission.taglineKey);
      expect(card).toHaveTextContent(mission.mechanismKey);
    }
  });

  it('mounts the picked mission and returns to the picker', async () => {
    const { user } = renderWithProviders(<GuidedShowroom lng="fr" />);
    await user.click(screen.getByTestId('showroom-pick-memory_dinner'));
    expect(
      screen.getByRole('heading', { name: 'showroom.m.memory_dinner.title' })
    ).toBeInTheDocument();
    expect(screen.queryByTestId('showroom-pick-memory_dinner')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('showroom-back-to-picker'));
    expect(screen.getByTestId('showroom-pick-memory_dinner')).toBeInTheDocument();
  });

  it('fires demo_viewed once per page, not per mission selection', async () => {
    const { user } = renderWithProviders(<GuidedShowroom lng="fr" />);
    const viewed = () => trackSpy.mock.calls.filter(([e]) => e === 'demo_viewed').length;
    expect(viewed()).toBe(1);

    await user.click(screen.getByTestId('showroom-pick-config_tour'));
    await user.click(screen.getByTestId('showroom-back-to-picker'));
    await user.click(screen.getByTestId('showroom-pick-daily_briefing'));
    expect(viewed()).toBe(1);
  });

  it('gives each picked mission a fresh state machine', async () => {
    const { user } = renderWithProviders(<GuidedShowroom lng="fr" />);
    // Start the phone mission, then leave mid-run.
    await user.click(screen.getByTestId('showroom-pick-phone_booking'));
    await user.click(screen.getByRole('button', { name: 'showroom.start' }));
    await user.click(screen.getByTestId('showroom-back-to-picker'));
    // Re-entering shows the ready screen again — nothing leaked.
    await user.click(screen.getByTestId('showroom-pick-phone_booking'));
    expect(screen.getByRole('button', { name: 'showroom.start' })).toBeInTheDocument();
  });
});
