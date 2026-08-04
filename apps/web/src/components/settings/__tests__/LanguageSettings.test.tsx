/**
 * LanguageSettings — selecting a different language persists it (PATCH);
 * re-selecting the current one, or acting without a user, is a no-op.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate, loading: false }) }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { LanguageSettings } from '../LanguageSettings';
import { languageNames } from '@/i18n/settings';
import { frontendToBackendLocale } from '@/utils/locale-mapping';

// The button is named by what it SHOWS — flag, native name, English name —
// so the accessible name is localised for free and satisfies WCAG 2.5.3
// (Label in Name). It used to carry `aria-label={`Select ${native}`}`:
// English in all six locales, and it overrode the visible text.
const btn = (lang: keyof typeof languageNames) => new RegExp(`${languageNames[lang].native}`);

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue({ language: 'fr' });
});

describe('LanguageSettings', () => {
  it('selecting a different language persists it', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: btn('fr') }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/users/u1', { language: frontendToBackendLocale('fr') })
    );
  });

  it('re-selecting the current language is a no-op', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: btn('en') }));
    expect(mutate).not.toHaveBeenCalled();
  });

  it('keeps the selected option focusable and marks it as current', () => {
    // The selected option used to be `disabled`. The browser drops a disabled
    // control from the tab order and BLURS it — so the option a keyboard user
    // had just activated vanished from under them and focus fell back to
    // <body>. The selection is stated with `aria-current` instead.
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);

    const current = screen.getByRole('button', { name: btn('en') });
    expect(current).toBeEnabled();
    expect(current).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('button', { name: btn('fr') })).not.toHaveAttribute('aria-current');
  });

  it('leaves focus on the option the user just activated', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);

    const current = screen.getByRole('button', { name: btn('en') });
    current.focus();
    await user.click(current);

    // A focus oracle, not a snapshot: this is the regression that a rendered
    // -output assertion cannot see.
    expect(document.activeElement).toBe(current);
    expect(mutate).not.toHaveBeenCalled();
  });

  it('renders nothing without an authenticated user', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    expect(screen.queryByRole('button', { name: btn('fr') })).toBeNull();
  });
});
