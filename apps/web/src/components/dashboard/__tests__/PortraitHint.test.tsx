/**
 * PortraitHint (QW-10) — visibility rule + interactions.
 *
 * The hint shows only for a RECENT portrait compilation the user has not yet
 * seen/dismissed (localStorage keyed by compiled_at, so a newer compilation
 * re-surfaces it). CTA navigates to the journals deep link; both actions
 * remember the compilation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PortraitHint, isPortraitHintVisible } from '../PortraitHint';
import { PORTRAIT_HINT_STORAGE_KEY } from '@/lib/constants';
import type { JournalPortrait } from '@/hooks/useJournals';

const push = vi.fn();
let portraitValue: JournalPortrait | null = null;
let journalsEnabled = true;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { journals_enabled: journalsEnabled } },
    loading: false,
  }),
}));

vi.mock('@/hooks/useJournalPortrait', () => ({
  useJournalPortrait: (enabled: boolean) => ({
    portrait: enabled ? portraitValue : null,
    hasPortrait: Boolean(enabled && (portraitValue?.full || portraitValue?.brief)),
    loading: false,
  }),
}));

function recentIso(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000).toISOString();
}

describe('isPortraitHintVisible', () => {
  const now = new Date('2026-07-22T12:00:00Z');

  it('is visible for a recent, unseen compilation only', () => {
    expect(isPortraitHintVisible('2026-07-20T00:00:00Z', null, now)).toBe(true);
    expect(isPortraitHintVisible('2026-07-01T00:00:00Z', null, now)).toBe(false); // stale
    expect(isPortraitHintVisible(null, null, now)).toBe(false); // never compiled
    expect(isPortraitHintVisible('2026-07-20T00:00:00Z', '2026-07-20T00:00:00Z', now)).toBe(false); // seen
  });

  it('re-surfaces when a NEWER compilation lands', () => {
    expect(isPortraitHintVisible('2026-07-21T00:00:00Z', '2026-07-20T00:00:00Z', now)).toBe(true);
  });
});

describe('PortraitHint', () => {
  beforeEach(() => {
    push.mockClear();
    window.localStorage.clear();
    journalsEnabled = true;
    portraitValue = { full: 'portrait', brief: 'brief', compiled_at: recentIso(1) };
  });

  it('navigates to the journals deep link and remembers the compilation', () => {
    render(<PortraitHint />);

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.portrait_hint.cta' }));

    expect(push).toHaveBeenCalledWith('/fr/dashboard/settings?section=journals');
    expect(window.localStorage.getItem(PORTRAIT_HINT_STORAGE_KEY)).toBe(portraitValue?.compiled_at);
  });

  it('dismisses without navigating and stays hidden afterwards', () => {
    const { unmount } = render(<PortraitHint />);

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.portrait_hint.dismiss' }));
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByText('dashboard.portrait_hint.text')).toBeNull();

    unmount();
    render(<PortraitHint />);
    expect(screen.queryByText('dashboard.portrait_hint.text')).toBeNull();
  });

  it('renders nothing for a stale compilation', () => {
    portraitValue = { full: 'portrait', brief: null, compiled_at: recentIso(30) };
    render(<PortraitHint />);
    expect(screen.queryByText('dashboard.portrait_hint.text')).toBeNull();
  });

  it('renders nothing when the journals feature is disabled', () => {
    journalsEnabled = false;
    render(<PortraitHint />);
    expect(screen.queryByText('dashboard.portrait_hint.text')).toBeNull();
  });
});
