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
import { languageNames, languageFlags } from '@/i18n/settings';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
});

describe('LanguageSelector', () => {
  it('shows the current language native name and flag on the trigger', () => {
    renderWithProviders(<LanguageSelector currentLocale="en" />);
    expect(screen.getByText(languageNames.en.native)).toBeInTheDocument();
    expect(screen.getByText(languageFlags.en)).toBeInTheDocument();
  });

  it('exposes the trigger as a menu button', () => {
    renderWithProviders(<LanguageSelector currentLocale="fr" />);
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(screen.getByText(languageNames.fr.native)).toBeInTheDocument();
  });

  /**
   * Header reachability (S10): below `lg` only the flag renders, and a flag
   * emoji is not an accessible name — a screen-reader user would hear "🇫🇷"
   * or nothing. The trigger therefore carries an explicit name at every
   * viewport. The i18n stub echoes keys, so the key is what is asserted.
   */
  it('names the trigger independently of the visible label', () => {
    renderWithProviders(<LanguageSelector currentLocale="de" />);
    expect(
      screen.getByRole('button', { name: 'settings.language.selector_label' })
    ).toBeInTheDocument();
  });
});
