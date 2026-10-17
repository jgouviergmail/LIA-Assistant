/**
 * CardsDisplaySettings — the four response display modes, selecting one
 * (persist + refresh + toast), the same-mode no-op, and the error toast.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { CardsDisplaySettings } from '../CardsDisplaySettings';

const MODE = (m: string) => `settings.preferences.display_mode.modes.${m}.label`;

function authed(over: Partial<User> = {}) {
  return {
    user: makeUser({ response_display_mode: 'cards', ...over }),
    refreshUser: vi.fn<() => Promise<boolean>>().mockResolvedValue(true),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
});

describe('CardsDisplaySettings', () => {
  it('renders the four display modes and announces the selected one', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    for (const m of ['cards', 'html', 'html_cards', 'markdown']) {
      expect(screen.getByRole('button', { name: MODE(m) })).toHaveAttribute(
        'aria-pressed',
        String(m === 'cards')
      );
      expect(screen.getByRole('button', { name: MODE(m) })).toHaveAccessibleDescription(
        `settings.preferences.display_mode.modes.${m}.summary`
      );
    }
  });

  it.each(['html', 'html_cards', 'markdown'])(
    'selecting %s persists it, refreshes and toasts',
    async mode => {
      const ctx = authed({ response_display_mode: 'cards' });
      useAuth.mockReturnValue(ctx);
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      await user.click(screen.getByRole('button', { name: MODE(mode) }));
      await waitFor(() =>
        expect(patch).toHaveBeenCalledWith('/auth/me/display-mode-preference', {
          response_display_mode: mode,
        })
      );
      expect(ctx.refreshUser).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledTimes(1);
    }
  );

  it('preserves focus while saving the combined mode and ignores duplicate clicks', async () => {
    const request = Promise.withResolvers<object>();
    patch.mockReturnValue(request.promise);
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    const combined = screen.getByRole('button', { name: MODE('html_cards') });
    await user.click(combined);
    expect(combined).toHaveFocus();
    expect(combined).toHaveAttribute('aria-disabled', 'true');
    await user.click(combined);
    expect(patch).toHaveBeenCalledTimes(1);
    await act(async () => request.resolve({}));
    expect(combined).toHaveFocus();
    expect(combined).toHaveAttribute('aria-disabled', 'false');
  });

  it.each(['cards', 'html', 'html_cards', 'markdown'])(
    're-selecting the active mode %s is a no-op',
    async mode => {
      useAuth.mockReturnValue(authed({ response_display_mode: mode }));
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      await user.click(screen.getByRole('button', { name: MODE(mode) }));
      expect(patch).not.toHaveBeenCalled();
    }
  );

  it.each(['markdown', 'html_cards'])(
    'keeps the previous mode after a failed %s update and allows retry',
    async mode => {
      patch.mockRejectedValueOnce(new Error('boom'));
      const ctx = authed({ response_display_mode: 'cards' });
      useAuth.mockReturnValue(ctx);
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      const option = screen.getByRole('button', { name: MODE(mode) });
      await user.click(option);
      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(screen.getByRole('button', { name: MODE('cards') })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      expect(option).toHaveAttribute('aria-pressed', 'false');
      expect(ctx.refreshUser).not.toHaveBeenCalled();
      await user.click(option);
      await waitFor(() => expect(ctx.refreshUser).toHaveBeenCalledTimes(1));
      expect(toast.success).toHaveBeenCalledTimes(1);
    }
  );
});

describe('CardsDisplaySettings — preview and account lifetime', () => {
  it('distinguishes the answer format while keeping exactly the same result cards', () => {
    const auth = authed();
    useAuth.mockReturnValue(auth);
    const { rerender } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    const preview = screen.getByRole('region', {
      name: 'settings.preferences.display_mode.preview.title',
    });
    expect(
      within(preview).getByText('settings.preferences.display_mode.preview.classic_answer')
    ).toBeVisible();
    expect(
      within(preview).getByText('settings.preferences.display_mode.preview.cards_title')
    ).toBeVisible();
    const cards = within(preview)
      .getAllByRole('article')
      .map(card => card.textContent);
    expect(cards).toHaveLength(2);
    useAuth.mockReturnValue({
      ...auth,
      user: { ...auth.user, response_display_mode: 'html_cards' },
    });
    rerender(<CardsDisplaySettings lng="en" />);
    expect(
      within(preview).queryByText('settings.preferences.display_mode.preview.classic_answer')
    ).not.toBeInTheDocument();
    const synthesis = within(preview).getByRole('region', {
      name: 'settings.preferences.display_mode.preview.rich_title',
    });
    expect(
      within(synthesis).getByText('settings.preferences.display_mode.preview.rich_summary')
    ).toBeVisible();
    expect(
      within(synthesis).getByText('settings.preferences.display_mode.preview.highlight_text')
    ).toBeVisible();
    expect(
      within(preview)
        .getAllByRole('article')
        .map(card => card.textContent)
    ).toEqual(cards);
    expect(patch).not.toHaveBeenCalled();
  });
  it('shows an explicitly illustrative preview without another data request', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    expect(
      screen.getByRole('region', { name: 'settings.preferences.display_mode.preview.title' })
    ).toHaveTextContent('settings.preferences.display_mode.preview.example_label');
    expect(
      screen.getByText('settings.preferences.display_mode.preview.weather.location')
    ).toBeInTheDocument();
    expect(
      screen.getByText('settings.preferences.display_mode.preview.meeting.name')
    ).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
  });

  it('falls back to cards for an unrecognized stored mode', () => {
    useAuth.mockReturnValue(authed({ response_display_mode: 'legacy-unknown' }));
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    expect(screen.getByRole('button', { name: MODE('cards') })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.queryByText(/legacy-unknown/)).not.toBeInTheDocument();
  });

  it('blocks two activations in the same event batch', async () => {
    const request = Promise.withResolvers<object>();
    patch.mockReturnValue(request.promise);
    useAuth.mockReturnValue(authed());
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    act(() => {
      screen.getByRole('button', { name: MODE('html') }).click();
      screen.getByRole('button', { name: MODE('markdown') }).click();
    });
    expect(patch).toHaveBeenCalledTimes(1);
    await act(async () => request.resolve({}));
  });

  it.each(['success', 'failure'])('ignores a late %s after an account change', async outcome => {
    const request = Promise.withResolvers<object>();
    patch.mockReturnValueOnce(request.promise);
    const previous = authed({ id: 'previous-account' });
    useAuth.mockReturnValue(previous);
    const { user, rerender } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: MODE('html') }));
    const current = authed({ id: 'current-account', response_display_mode: 'markdown' });
    useAuth.mockReturnValue(current);
    rerender(<CardsDisplaySettings lng="en" />);
    expect(screen.getByRole('button', { name: MODE('markdown') })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: MODE('html') })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    );
    await act(async () =>
      outcome === 'success' ? request.resolve({}) : request.reject(new Error('late'))
    );
    expect(previous.refreshUser).not.toHaveBeenCalled();
    expect(current.refreshUser).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: MODE('html_cards') }));
    await waitFor(() => expect(current.refreshUser).toHaveBeenCalledTimes(1));
  });

  it('does not refresh authentication after leaving the section during a save', async () => {
    const request = Promise.withResolvers<object>();
    patch.mockReturnValue(request.promise);
    const ctx = authed();
    useAuth.mockReturnValue(ctx);
    const { user, unmount } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: MODE('html') }));
    unmount();
    await act(async () => request.resolve({}));
    expect(ctx.refreshUser).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });
});

it('does not announce activation if the saved preference cannot be reloaded and permits retry', async () => {
  const ctx = authed();
  ctx.refreshUser.mockResolvedValueOnce(false);
  useAuth.mockReturnValue(ctx);
  const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
  const target = screen.getByRole('button', { name: MODE('html') });
  await user.click(target);
  await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  expect(toast.success).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: MODE('cards') })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(target).toHaveFocus();
  expect(target).toHaveAttribute('aria-disabled', 'false');
  await user.click(target);
  await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  expect(patch).toHaveBeenCalledTimes(2);
  expect(ctx.refreshUser).toHaveBeenCalledTimes(2);
});
