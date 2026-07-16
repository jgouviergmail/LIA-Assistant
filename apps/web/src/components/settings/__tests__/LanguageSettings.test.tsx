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

const btn = (native: string) => `Select ${native}`;

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue({ language: 'fr' });
});

describe('LanguageSettings', () => {
  it('selecting a different language persists it', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: btn(languageNames.fr.native) }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/users/u1', { language: frontendToBackendLocale('fr') })
    );
  });

  it('re-selecting the current language is a no-op', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', language: 'en' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: btn(languageNames.en.native) }));
    expect(mutate).not.toHaveBeenCalled();
  });

  it('renders nothing without an authenticated user', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<LanguageSettings lng="en" collapsible={false} />);
    expect(screen.queryByRole('button', { name: btn(languageNames.fr.native) })).toBeNull();
  });
});
