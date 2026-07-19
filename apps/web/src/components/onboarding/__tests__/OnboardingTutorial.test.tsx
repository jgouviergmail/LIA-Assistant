/**
 * OnboardingTutorial — completion persistence (Lot 1 onboarding fix).
 *
 * Runtime-proven defect being pinned: the final CTA closed the dialog
 * WITHOUT persisting onboarding_completed, and the dashboard layout
 * re-mounts the dialog on every navigation while the flag is false — the
 * tutorial re-opened endlessly for users who read it to the end. Both exit
 * buttons must now persist.
 */

import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OnboardingTutorial } from '@/components/onboarding/OnboardingTutorial';

const patchMock = vi.fn().mockResolvedValue({ data: {} });

vi.mock('@/lib/api-client', () => ({
  default: { patch: (...args: unknown[]) => patchMock(...args) },
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ refreshUser: vi.fn().mockResolvedValue(undefined) }),
}));

const pushMock = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: (href: string) => pushMock(href) }),
}));

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    // Identity translator, except one materialized example per category:
    // Page7 SKIPS examples whose translation is missing (t returns the key),
    // so the actionable-example test needs one real value.
    t: (key: string) => (key.endsWith('.example1') ? `Exemple ${key.split('.')[3]}` : key),
  }),
}));

describe('OnboardingTutorial — completion persistence', () => {
  beforeAll(() => {
    // jsdom lacks Element#scrollTo (used by the page-change scroll reset).
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      value: () => undefined,
      writable: true,
    });
  });

  beforeEach(() => {
    patchMock.mockClear();
    pushMock.mockClear();
  });

  async function renderAtLastPage(onComplete: () => void) {
    render(<OnboardingTutorial lng="fr" open onComplete={onComplete} />);
    // Walk pages 1 → 7 via the "next" button (label mocked to its key).
    for (let i = 0; i < 6; i++) {
      await userEvent.click(screen.getByRole('button', { name: /common\.next/ }));
    }
  }

  it('the final CTA persists onboarding_completed and closes', async () => {
    const onComplete = vi.fn();
    await renderAtLastPage(onComplete);

    await userEvent.click(screen.getByRole('button', { name: /onboarding\.page7\.cta/ }));

    expect(patchMock).toHaveBeenCalledWith('/auth/me/onboarding-preference', {
      onboarding_completed: true,
    });
    expect(onComplete).toHaveBeenCalled();
  });

  it('page 2 CTA completes onboarding THEN navigates to connectors settings', async () => {
    const onComplete = vi.fn();
    render(<OnboardingTutorial lng="fr" open onComplete={onComplete} />);
    await userEvent.click(screen.getByRole('button', { name: /common\.next/ }));

    await userEvent.click(screen.getByRole('button', { name: /onboarding\.page2\.cta/ }));

    expect(patchMock).toHaveBeenCalledWith('/auth/me/onboarding-preference', {
      onboarding_completed: true,
    });
    expect(onComplete).toHaveBeenCalled();
    expect(pushMock).toHaveBeenCalledWith('/dashboard/settings?section=connectors');
  });

  it('page 2 CTA does NOT navigate when persistence fails', async () => {
    patchMock.mockRejectedValueOnce(new Error('boom'));
    const onComplete = vi.fn();
    render(<OnboardingTutorial lng="fr" open onComplete={onComplete} />);
    await userEvent.click(screen.getByRole('button', { name: /common\.next/ }));

    await userEvent.click(screen.getByRole('button', { name: /onboarding\.page2\.cta/ }));

    expect(onComplete).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('a page 7 example completes onboarding then opens the chat prefilled', async () => {
    const onComplete = vi.fn();
    await renderAtLastPage(onComplete);

    // Open the first category accordion, then tap its first example button.
    await userEvent.click(
      screen.getByRole('button', { name: /onboarding\.page7\.categories\.contacts\.title/ })
    );
    await userEvent.click(screen.getByRole('button', { name: /Exemple contacts/ }));

    expect(patchMock).toHaveBeenCalledWith('/auth/me/onboarding-preference', {
      onboarding_completed: true,
    });
    expect(pushMock).toHaveBeenCalledWith(
      `/dashboard/chat?draft=${encodeURIComponent('Exemple contacts')}`
    );
  });

  it('the skip button persists too (unchanged behavior)', async () => {
    const onComplete = vi.fn();
    render(<OnboardingTutorial lng="fr" open onComplete={onComplete} />);

    await userEvent.click(screen.getByRole('button', { name: /onboarding\.skip/ }));

    expect(patchMock).toHaveBeenCalledWith('/auth/me/onboarding-preference', {
      onboarding_completed: true,
    });
    expect(onComplete).toHaveBeenCalled();
  });
});
