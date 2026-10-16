import type { ContextType } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type User } from '@/lib/auth';
import type { Language } from '@/i18n/settings';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import de from '../../../../locales/de/translation.json';
import es from '../../../../locales/es/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';
import { DashboardDateHeading } from '../DashboardDateHeading';

vi.unmock('react-i18next');

const resources = {
  en: { translation: en },
  fr: { translation: fr },
  de: { translation: de },
  es: { translation: es },
  it: { translation: itLocale },
  zh: { translation: zh },
};

function account(overrides: Partial<User> = {}): User {
  return {
    id: 'account-a',
    email: 'date@example.test',
    timezone: 'Asia/Tokyo',
    is_active: true,
    is_verified: true,
    is_superuser: false,
    memory_enabled: true,
    execution_mode: 'pipeline',
    voice_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'local',
    tokens_display_enabled: false,
    debug_panel_enabled: false,
    response_display_mode: 'markdown',
    onboarding_completed: true,
    ...overrides,
  };
}

function view(lng: Language = 'en', user: User | null = account()) {
  const i18n = createInstance();
  void i18n.init({ lng, resources, fallbackLng: lng, initAsync: false });
  const auth: NonNullable<ContextType<typeof AuthContext>> = {
    user,
    isLoading: false,
    login: vi.fn(),
    verifyMfa: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    initiateGoogleOAuth: vi.fn(),
    completeNativeSignIn: vi.fn(),
    refreshUser: vi.fn(),
  };
  return (
    <AuthContext.Provider value={auth}>
      <I18nextProvider i18n={i18n}>
        <DashboardDateHeading lng={lng} />
      </I18nextProvider>
    </AuthContext.Provider>
  );
}

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-15T00:30:00Z'));
  vi.stubEnv('TZ', 'Pacific/Honolulu');
  setVisibility('visible');
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  setVisibility('visible');
});

describe('DashboardDateHeading', () => {
  it('uses the account civil day for Tokyo and Los Angeles in a third browser timezone', () => {
    expect(new Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('Pacific/Honolulu');
    const { rerender } = render(view());
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Thursday, October 15');

    rerender(view('en', account({ id: 'account-b', timezone: 'America/Los_Angeles' })));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Wednesday, October 14');
  });

  it.each<[Language, string]>([
    ['en', 'Thursday, October 15'],
    ['fr', 'Jeudi 15 octobre'],
    ['de', 'Donnerstag, 15. Oktober'],
    ['es', 'Jueves, 15 de octubre'],
    ['it', 'Giovedì 15 ottobre'],
    ['zh', '10月15日星期四'],
  ])('formats the date in the %s UI locale', (lng, expected) => {
    render(view(lng));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(expected);
  });

  it('updates when the active UI language changes without changing the account language', () => {
    const user = account({ language: 'en' });
    const { rerender } = render(view('en', user));
    rerender(view('fr', user));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Jeudi 15 octobre');
  });

  it('updates when the account timezone changes', () => {
    const { rerender } = render(view());
    rerender(view('en', account({ timezone: 'America/Los_Angeles' })));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Wednesday, October 14');
  });

  it.each<[Language, string]>([
    ['en', 'Dashboard'],
    ['fr', 'Tableau de bord'],
  ])('falls back to the existing translated dashboard title in %s', (lng, title) => {
    const { rerender } = render(view(lng, account({ timezone: undefined })));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(title);
    rerender(view(lng, account({ timezone: 'Not/A_Timezone' })));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(title);
    rerender(view(lng, account({ timezone: '' })));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(title);
    rerender(view(lng, null));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(title);
  });

  it('changes the date exactly at account midnight without a page refresh', () => {
    vi.setSystemTime(new Date('2026-10-15T14:59:59.500Z'));
    render(view());
    act(() => vi.advanceTimersByTime(499));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Thursday, October 15');
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Friday, October 16');
  });

  it.each([
    ['2026-03-08T08:00:00Z', '2026-03-09T07:00:00Z', 'Monday, March 9'],
    ['2026-11-01T07:00:00Z', '2026-11-02T08:00:00Z', 'Monday, November 2'],
  ])('keeps the correct midnight across the DST day starting %s', (start, end, expected) => {
    vi.setSystemTime(new Date(start));
    render(view('en', account({ timezone: 'America/Los_Angeles' })));
    const before = screen.getByRole('heading', { level: 1 }).textContent;
    const duration = Date.parse(end) - Date.parse(start);
    act(() => vi.advanceTimersByTime(duration - 1));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(before ?? '');
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(expected);
  });

  it.each(['focus', 'visibilitychange'])('recovers after a suspended clock on %s', event => {
    render(view());
    vi.setSystemTime(new Date('2026-10-16T00:30:00Z'));
    act(() => {
      (event === 'focus' ? window : document).dispatchEvent(new Event(event));
    });
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Friday, October 16');
  });

  it('keeps server markup and the first client render stable across midnight', () => {
    vi.setSystemTime(new Date('2026-10-15T14:59:59Z'));
    const container = document.createElement('div');
    container.innerHTML = renderToString(view('fr'));
    expect(container.querySelector('h1')).toHaveTextContent('Tableau de bord');
    document.body.append(container);
    vi.setSystemTime(new Date('2026-10-15T15:00:01Z'));
    const onRecoverableError = vi.fn();

    render(view('fr'), { container, hydrate: true, onRecoverableError });

    expect(onRecoverableError).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Vendredi 16 octobre');
  });

  it('releases its clock and foreground subscriptions when unmounted', () => {
    const { unmount } = render(view());
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => {
      vi.setSystemTime(new Date('2026-10-16T00:30:00Z'));
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(vi.getTimerCount()).toBe(0);
  });
});
