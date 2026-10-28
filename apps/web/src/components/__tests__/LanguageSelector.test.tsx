/**
 * LanguageSelector — trigger contract.
 *
 * The language switch itself lives on Radix `DropdownMenuItem`s rendered through
 * a floating-ui popper, which does not open under jsdom (floating-ui's
 * `autoUpdate` needs real ResizeObserver/IntersectionObserver constructors). We
 * therefore pin the observable trigger contract here; the pure switch helpers
 * (`switchLanguageInPath`, `frontendToBackendLocale`) are unit-tested separately.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/en',
}));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { patch: vi.fn() } }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { LanguageSelector } from '../LanguageSelector';
import { languageNames, type Language } from '@/i18n/settings';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
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
});
