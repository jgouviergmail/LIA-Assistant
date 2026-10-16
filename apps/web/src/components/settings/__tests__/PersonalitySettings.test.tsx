/** Personality selection: real UI state, recovery, focus and account-bound saves. */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, within, act } from '@/__tests__/test-utils';
import type { PersonalityListItem } from '@/types/personality';
import type { UsePersonalityReturn } from '@/hooks/usePersonality';

const mocks = vi.hoisted(() => ({
  usePersonality: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  owner: { id: 'owner-a' },
  confirmedId: 'p2',
}));
vi.mock('@/hooks/usePersonality', () => ({ usePersonality: mocks.usePersonality }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: mocks.owner }) }));
vi.mock('@/stores/personalityStore', () => ({
  usePersonalityStore: {
    getState: () => ({
      currentPersonality: PERSONALITIES.find(item => item.id === mocks.confirmedId) ?? null,
      currentPersonalityId: mocks.confirmedId,
    }),
  },
}));
vi.mock('sonner', () => ({ toast: { success: mocks.success, error: mocks.error } }));
import { PersonalitySettings } from '../PersonalitySettings';

const PERSONALITIES: PersonalityListItem[] = [
  {
    id: 'p1',
    code: 'companion',
    title: 'Companion',
    description: 'Warm',
    emoji: '😊',
    is_default: true,
  },
  {
    id: 'p2',
    code: 'analyst',
    title: 'Analyst',
    description: 'Precise',
    emoji: '🔬',
    is_default: false,
  },
];
function hook(overrides: Partial<UsePersonalityReturn> = {}): UsePersonalityReturn {
  return {
    personalities: PERSONALITIES,
    currentPersonality: PERSONALITIES[0],
    currentPersonalityId: 'p1',
    loading: false,
    refreshing: false,
    updating: false,
    error: null,
    updatePersonality: vi.fn().mockResolvedValue(undefined),
    refetch: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}
function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>(done => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.owner = { id: 'owner-a' };
  mocks.confirmedId = 'p2';
});

describe('PersonalitySettings', () => {
  it('shows first-load status without inventing a selected personality', () => {
    mocks.usePersonality.mockReturnValue(
      hook({ loading: true, personalities: [], currentPersonality: null })
    );
    renderWithProviders(<PersonalitySettings lng="en" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Companion' })).not.toBeInTheDocument();
  });
  it('renders the complete catalogue and describes its real current selection', () => {
    const personalities = Array.from({ length: 24 }, (_, index) => ({
      ...PERSONALITIES[index % 2],
      id: `p-${index}`,
      title: `Style ${index}`,
      is_default: index === 0,
    }));
    mocks.usePersonality.mockReturnValue(
      hook({
        personalities,
        currentPersonality: personalities[20],
        currentPersonalityId: personalities[20].id,
      })
    );
    renderWithProviders(<PersonalitySettings lng="en" />);
    const current = screen.getByRole('region', { name: 'personality.current' });
    expect(within(current).getByText('Style 20')).toBeInTheDocument();
    for (const personality of personalities)
      expect(screen.getByRole('button', { name: personality.title })).toHaveAttribute(
        'aria-pressed',
        String(personality.id === personalities[20].id)
      );
    expect(screen.getByRole('button', { name: 'Style 20' })).toHaveAccessibleDescription('Warm');
  });
  it('does not rewrite or announce the current choice', async () => {
    const updatePersonality = vi.fn();
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Companion' }));
    expect(updatePersonality).not.toHaveBeenCalled();
    expect(mocks.success).not.toHaveBeenCalled();
  });
  it('keeps the confirmed selection and focused target during a pending save, ignoring duplicate activation', async () => {
    const task = deferred<void>();
    const updatePersonality = vi.fn(() => task.promise);
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    const choice = screen.getByRole('button', { name: 'Analyst' });
    await user.dblClick(choice);
    expect(updatePersonality).toHaveBeenCalledTimes(1);
    expect(choice).toHaveFocus();
    expect(choice).toHaveAttribute('aria-disabled', 'true');
    expect(choice).toHaveAttribute('aria-busy', 'true');
    expect(choice).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Companion' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    task.resolve();
    await waitFor(() => expect(choice).not.toHaveAttribute('aria-busy'));
    expect(choice).toHaveFocus();
  });
  it('reports success only after the chosen style is confirmed', async () => {
    const updatePersonality = vi.fn().mockResolvedValue(undefined);
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    expect(updatePersonality).toHaveBeenCalledWith('p2');
    await waitFor(() => expect(mocks.success).toHaveBeenCalledTimes(1));
  });
  it('does not claim success when a competing shared save made the requested update a no-op', async () => {
    mocks.confirmedId = 'p1';
    const updatePersonality = vi.fn().mockResolvedValue(undefined);
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Analyst' })).not.toHaveAttribute('aria-busy')
    );
    expect(updatePersonality).toHaveBeenCalledWith('p2');
    expect(mocks.success).not.toHaveBeenCalled();
  });

  it('retains the confirmed style and offers recovery after a save fails', async () => {
    const updatePersonality = vi.fn().mockRejectedValue(new Error('offline'));
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    await waitFor(() => expect(mocks.error).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Companion' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(mocks.success).not.toHaveBeenCalled();
  });
  it('shows an initial load failure with retry rather than false emptiness', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    mocks.usePersonality.mockReturnValue(
      hook({ personalities: [], currentPersonality: null, error: new Error('offline'), refetch })
    );
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    expect(screen.getByRole('alert')).toHaveTextContent('personality.load_error');
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
  it('keeps populated styles mounted during catalogue refresh, including their focus', () => {
    mocks.usePersonality.mockReturnValue(hook());
    const { rerender } = renderWithProviders(<PersonalitySettings lng="en" />);
    const selected = screen.getByRole('button', { name: 'Companion' });
    act(() => selected.focus());
    mocks.usePersonality.mockReturnValue(hook({ refreshing: true }));
    rerender(<PersonalitySettings lng="en" />);
    expect(screen.getByRole('button', { name: 'Companion' })).toBe(selected);
    expect(selected).toHaveFocus();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('does not publish old-account save side effects after navigation to another account', async () => {
    const task = deferred<void>();
    const updatePersonality = vi.fn(() => task.promise);
    mocks.usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user, rerender } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    mocks.owner = { id: 'owner-b' };
    rerender(<PersonalitySettings lng="en" />);
    task.resolve();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Analyst' })).not.toHaveAttribute('aria-busy')
    );
    expect(mocks.success).not.toHaveBeenCalled();
  });

});
