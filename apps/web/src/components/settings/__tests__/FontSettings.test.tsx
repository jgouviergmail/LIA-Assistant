/**
 * FontSettings — the font choices, selecting one (local state + persistence for
 * an authenticated user), and the no-user path.
 *
 * `@/lib/font-context` is mocked so `setFontFamily` is observable.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { setFontFamily } = vi.hoisted(() => ({ setFontFamily: vi.fn() }));
vi.mock('@/lib/font-context', () => ({
  // FontProvider must stay a passthrough: renderWithProviders mounts it.
  FontProvider: ({ children }: { children: React.ReactNode }) => children,
  useFontFamily: () => ({ fontFamily: 'system', setFontFamily }),
}));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

import { FontSettings } from '../FontSettings';

const LABEL = (name: string) => `settings.font.fonts.${name}.label`;

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
});

describe('FontSettings', () => {
  it('renders selectable font options', () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    renderWithProviders(<FontSettings lng="en" />);
    expect(screen.getByRole('button', { name: LABEL('system') })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: LABEL('noto-sans') })).toBeInTheDocument();
  });

  it('selecting a font updates local state and persists it for an authenticated user', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<FontSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: LABEL('noto-sans') }));
    expect(setFontFamily).toHaveBeenCalledWith('noto-sans');
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/users/u1', { font_family: 'noto-sans' })
    );
  });

  it('selecting a font updates local state but does not persist without a user', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<FontSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: LABEL('noto-sans') }));
    expect(setFontFamily).toHaveBeenCalledWith('noto-sans');
    expect(mutate).not.toHaveBeenCalled();
  });
});
