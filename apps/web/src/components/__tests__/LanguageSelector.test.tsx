/**
 * LanguageSelector — accessible trigger and explicit preference changes.
 *
 * Drive the real Radix menu and cookie store. Only the API and document-navigation
 * boundaries are intercepted; browser coverage verifies the fresh Next route cache.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAuth, navigation, patch, refreshUser } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  navigation: { pathname: '/en', assign: vi.fn<(url: string) => void>() },
  patch: vi.fn<(url: string, body: { language: string }) => Promise<void>>(),
  refreshUser: vi.fn<() => Promise<void>>(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
}));

vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { LanguageSelector } from '../LanguageSelector';
import { cookieName, languageNames, setLocaleCookie, type Language } from '@/i18n/settings';
import { logger } from '@/lib/logger';

let originalLocation: Location;

beforeEach(() => {
  vi.clearAllMocks();
  navigation.assign.mockReset();
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { href: originalLocation.href, assign: navigation.assign },
  });
  navigation.pathname = '/en';
  patch.mockResolvedValue(undefined);
  refreshUser.mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: null, refreshUser });
  document.cookie = `${cookieName}=; path=/; max-age=0`;
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
  document.cookie = `${cookieName}=; path=/; max-age=0`;
});

describe('LanguageSelector', () => {
  it.each<[Language, string]>([
    ['fr', '/flags/fr.svg'],
    ['en', '/flags/gb.svg'],
    ['es', '/flags/es.svg'],
    ['de', '/flags/de.svg'],
    ['it', '/flags/it.svg'],
    ['zh', '/flags/cn.svg'],
  ])('renders %s as a local flag image instead of a platform-dependent emoji', (locale, asset) => {
    renderWithProviders(<LanguageSelector currentLocale={locale} />);
    const flag = screen.getByRole('button').querySelector('img');
    expect(flag).toHaveAttribute('src', asset);
    expect(flag).toHaveAttribute('alt', '');
    expect(flag).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText(languageNames[locale].native)).not.toBeInTheDocument();
  });

  it('exposes the trigger as a menu button', () => {
    renderWithProviders(<LanguageSelector currentLocale="fr" />);
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).not.toHaveTextContent(/FR|🇫🇷/);
  });

  /**
   * Header reachability (S10): only the flag renders, and a flag
   * image is decorative. The trigger therefore carries an explicit name at every
   * viewport. The i18n stub echoes keys, so the key is what is asserted.
   */
  it('names the trigger independently of the visible label', () => {
    renderWithProviders(<LanguageSelector currentLocale="de" />);
    expect(
      screen.getByRole('button', { name: 'settings.language.selector_label' })
    ).toBeInTheDocument();
  });

  /** Owner rule (2026-10-31): every icon of the header names itself on hover. */
  it('names the current language in the tooltip too', () => {
    renderWithProviders(<LanguageSelector currentLocale="de" />);
    expect(screen.getByRole('button')).toHaveAttribute('title', 'settings.language.selector_label');
  });

  it.each<[Language, string]>([
    ['fr', '/blog'],
    ['en', '/en/blog'],
    ['es', '/es/blog'],
    ['de', '/de/blog'],
    ['it', '/it/blog'],
    ['zh', '/zh/blog'],
  ])('persists an explicit %s choice before a document navigation to %s', async (locale, path) => {
    navigation.pathname = '/blog';
    setLocaleCookie('en');
    navigation.assign.mockImplementation(() => {
      expect(document.cookie).toContain(`${cookieName}=${locale}`);
    });
    const { user } = renderWithProviders(<LanguageSelector currentLocale="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
    await user.click(
      await screen.findByRole('menuitem', { name: new RegExp(languageNames[locale].native) })
    );

    await waitFor(() => expect(navigation.assign).toHaveBeenCalledWith(path));
    expect(patch).not.toHaveBeenCalled();
    expect(refreshUser).not.toHaveBeenCalled();
  });

  it('persists a reselected displayed language for the account before leaving the page', async () => {
    navigation.pathname = '/';
    setLocaleCookie('en');
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser });
    let finishPatch: () => void = () => {
      throw new Error('PATCH did not start');
    };
    patch.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          finishPatch = resolve;
        })
    );
    let finishRefresh: () => void = () => {
      throw new Error('Profile refresh did not start');
    };
    refreshUser.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          finishRefresh = resolve;
        })
    );
    const { user } = renderWithProviders(<LanguageSelector currentLocale="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
    await user.click(await screen.findByRole('menuitem', { name: /Français/ }));

    expect(patch).toHaveBeenCalledWith('/users/u1', { language: 'fr' });
    expect(navigation.assign).not.toHaveBeenCalled();
    await act(async () => {
      finishPatch();
    });
    expect(refreshUser).toHaveBeenCalledOnce();
    expect(navigation.assign).not.toHaveBeenCalled();
    await act(async () => {
      finishRefresh();
    });
    expect(document.cookie).toContain(`${cookieName}=fr`);
    expect(navigation.assign).toHaveBeenCalledExactlyOnceWith('/');
  });

  it('maps Chinese to the backend locale while preserving the frontend cookie and URL', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser });
    const { user } = renderWithProviders(<LanguageSelector currentLocale="en" />);

    await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
    await user.click(await screen.findByRole('menuitem', { name: /中文/ }));

    await waitFor(() => expect(navigation.assign).toHaveBeenCalledWith('/zh'));
    expect(patch).toHaveBeenCalledWith('/users/u1', { language: 'zh-CN' });
    expect(refreshUser).toHaveBeenCalledOnce();
    expect(document.cookie).toContain(`${cookieName}=zh`);
  });

  it('keeps the active page mounted when the displayed language and browser preference already match', async () => {
    navigation.pathname = '/fr/dashboard';
    setLocaleCookie('fr');
    const { user } = renderWithProviders(<LanguageSelector currentLocale="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
    await user.click(await screen.findByRole('menuitem', { name: /Français/ }));

    expect(document.cookie).toContain(`${cookieName}=fr`);
    expect(navigation.assign).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
  });

  it('still updates a different account preference when the displayed language and cookie match', async () => {
    navigation.pathname = '/fr/dashboard';
    setLocaleCookie('fr');
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser });
    const { user } = renderWithProviders(<LanguageSelector currentLocale="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
    await user.click(await screen.findByRole('menuitem', { name: /Français/ }));

    await waitFor(() => expect(refreshUser).toHaveBeenCalledOnce());
    expect(patch).toHaveBeenCalledWith('/users/u1', { language: 'fr' });
    expect(navigation.assign).not.toHaveBeenCalled();
    expect(document.cookie).toContain(`${cookieName}=fr`);
  });

  it.each(['patch', 'refresh'] as const)(
    'still saves the browser preference when %s fails',
    async failure => {
      useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser });
      const error = new Error('Network unavailable');
      if (failure === 'patch') patch.mockRejectedValueOnce(error);
      else refreshUser.mockRejectedValueOnce(error);
      const { user } = renderWithProviders(<LanguageSelector currentLocale="en" />);

      await user.click(screen.getByRole('button', { name: 'settings.language.selector_label' }));
      await user.click(await screen.findByRole('menuitem', { name: /Deutsch/ }));

      await waitFor(() => expect(navigation.assign).toHaveBeenCalledWith('/de'));
      expect(document.cookie).toContain(`${cookieName}=de`);
      expect(logger.error).toHaveBeenCalledWith(
        'Failed to update language in database',
        error,
        expect.objectContaining({ newLanguage: 'de' })
      );
      expect(refreshUser).toHaveBeenCalledTimes(failure === 'patch' ? 0 : 1);
    }
  );
});
