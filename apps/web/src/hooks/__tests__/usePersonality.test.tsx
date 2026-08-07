/**
 * Two components, one preference: changing it anywhere must show everywhere.
 *
 * The reported symptom, 2026-08-07: "dans réglages - Style de LIA quand je
 * change de style ça ne rafraîchit pas le style affiché dans le header. Je
 * dois rafraîchir manuellement la page." The header selector and the settings
 * panel both call `usePersonality`, which held its data in `useState` — so
 * each held a private copy and neither could hear the other.
 *
 * This suite renders both at once, exactly as the dashboard does, and drives
 * the update from each side in turn. A hook that keeps state per consumer
 * fails it; nothing short of shared state passes.
 */

import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PersonalityListItem } from '@/types/personality';

const fetchPersonalities = vi.fn();
const fetchCurrentPersonality = vi.fn();
const updateCurrentPersonality = vi.fn();

vi.mock('@/lib/api/personality', () => ({
  fetchPersonalities: () => fetchPersonalities(),
  fetchCurrentPersonality: () => fetchCurrentPersonality(),
  updateCurrentPersonality: (body: unknown) => updateCurrentPersonality(body),
}));

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

const authUser = { current: { id: 'user-1' } as { id: string } | null };
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: authUser.current }) }));

import { usePersonality } from '@/hooks/usePersonality';
import { usePersonalityStore } from '@/stores/personalityStore';

const CALM: PersonalityListItem = {
  id: 'calm-id',
  code: 'calm',
  emoji: '🌊',
  is_default: true,
  title: 'Posé',
  description: 'Répond calmement',
};

const SHARP: PersonalityListItem = {
  id: 'sharp-id',
  code: 'sharp',
  emoji: '⚡',
  is_default: false,
  title: 'Incisif',
  description: 'Va droit au but',
};

/** Stands in for the header selector: shows the style, and can change it. */
function Header() {
  const { currentPersonality, updatePersonality, loading } = usePersonality();
  return (
    <div>
      <span data-testid="header-style">
        {loading ? 'chargement' : (currentPersonality?.title ?? 'aucun')}
      </span>
      <button onClick={() => void updatePersonality(CALM.id)}>header vers Posé</button>
    </div>
  );
}

/** Stands in for the settings panel: same data, other side of the screen. */
function SettingsPanel() {
  const { currentPersonality, updatePersonality } = usePersonality();
  return (
    <div>
      <span data-testid="settings-style">{currentPersonality?.title ?? 'aucun'}</span>
      <button onClick={() => void updatePersonality(SHARP.id)}>réglages vers Incisif</button>
    </div>
  );
}


/** Reads the refreshing flag the way a consumer sets `aria-busy`. */
function Busy() {
  const { refreshing } = usePersonality();
  return <span data-testid="busy" data-busy={String(refreshing)} />;
}

beforeEach(() => {
  vi.clearAllMocks();
  usePersonalityStore.getState().reset();
  authUser.current = { id: 'user-1' };
  fetchPersonalities.mockResolvedValue({ personalities: [CALM, SHARP], count: 2 });
  fetchCurrentPersonality.mockResolvedValue({ personality: CALM, personality_id: CALM.id });
  updateCurrentPersonality.mockImplementation(
    async ({ personality_id }: { personality_id: string | null }) => {
      const chosen = [CALM, SHARP].find((p) => p.id === personality_id) ?? null;
      return { personality: chosen, personality_id: chosen?.id ?? null };
    }
  );
});

describe('the reported bug', () => {
  it('updates the header when the style is changed from settings', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Header />
        <SettingsPanel />
      </>
    );
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));

    await user.click(screen.getByRole('button', { name: 'réglages vers Incisif' }));

    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Incisif'));
    expect(screen.getByTestId('settings-style')).toHaveTextContent('Incisif');
  });

  it('updates settings when the style is changed from the header', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Header />
        <SettingsPanel />
      </>
    );
    await waitFor(() => expect(screen.getByTestId('settings-style')).toHaveTextContent('Posé'));
    await user.click(screen.getByRole('button', { name: 'réglages vers Incisif' }));
    await waitFor(() => expect(screen.getByTestId('settings-style')).toHaveTextContent('Incisif'));

    await user.click(screen.getByRole('button', { name: 'header vers Posé' }));

    await waitFor(() => expect(screen.getByTestId('settings-style')).toHaveTextContent('Posé'));
    expect(screen.getByTestId('header-style')).toHaveTextContent('Posé');
  });
});

describe('what the shared state must not cost', () => {
  it('fetches once for the whole page, not once per consumer', async () => {
    render(
      <>
        <Header />
        <SettingsPanel />
      </>
    );

    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));

    expect(fetchPersonalities).toHaveBeenCalledTimes(1);
    expect(fetchCurrentPersonality).toHaveBeenCalledTimes(1);
  });

  it('shows its waiting state before the first answer, never an empty style', async () => {
    // The hook used to start at `loading: true`; the store starts at false, so
    // without `hasLoaded` the header would flash "aucun" on first paint.
    let resolve: (value: unknown) => void = () => {};
    fetchPersonalities.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      })
    );

    render(<Header />);

    expect(screen.getByTestId('header-style')).toHaveTextContent('chargement');
    resolve({ personalities: [CALM, SHARP], count: 2 });
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));
  });

  it('does not serve one account the style of the previous one', async () => {
    const { unmount } = render(<Header />);
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));
    unmount();

    authUser.current = { id: 'user-2' };
    fetchCurrentPersonality.mockResolvedValue({ personality: SHARP, personality_id: SHARP.id });
    render(<Header />);

    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Incisif'));
  });
});

describe('the hook keeps the contract its callers rely on', () => {
  it('still exposes the whole surface', async () => {
    render(<Header />);
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));

    const state = usePersonalityStore.getState();

    expect(state.personalities).toHaveLength(2);
    expect(state.currentPersonalityId).toBe(CALM.id);
    expect(state.updating).toBe(false);
    expect(state.error).toBeNull();
  });

  it('surfaces a failed update to the caller rather than swallowing it', async () => {
    updateCurrentPersonality.mockRejectedValue(new Error('refused'));
    render(<Header />);
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));

    // Wrapped: this call updates the store, which re-renders the mounted
    // component — outside `act` React rightly warns that the assertion below
    // could read a frame the user would never see.
    await act(async () => {
      await expect(usePersonalityStore.getState().updatePersonality(SHARP.id)).rejects.toThrow(
        'refused'
      );
    });

    expect(screen.getByTestId('header-style')).toHaveTextContent('Posé');
  });
});

describe('a refresh is not a first load', () => {
  // apps/web/CLAUDE.md, in as many words: `loading ? <Spinner/> : content`
  // unmounts the subtree on every post-mutation refetch. Both consumers do
  // exactly that — the header selector swaps itself for a disabled
  // placeholder, the settings panel for a spinner — so a `loading` that also
  // means "refreshing" would blank the header of the whole app the moment an
  // administrator saves a style in Settings.
  it('keeps showing the current style while it refreshes', async () => {
    render(<Header />);
    await waitFor(() => expect(screen.getByTestId('header-style')).toHaveTextContent('Posé'));

    let resolve: (value: unknown) => void = () => {};
    fetchPersonalities.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      })
    );
    act(() => {
      void usePersonalityStore.getState().refetch();
    });

    expect(screen.getByTestId('header-style')).toHaveTextContent('Posé');
    await act(async () => {
      resolve({ personalities: [CALM, SHARP], count: 2 });
    });
  });

  it('announces the refresh instead, so assistive tech is not left silent', async () => {
    render(<Busy />);
    await waitFor(() => expect(screen.getByTestId('busy')).toHaveAttribute('data-busy', 'false'));

    let resolve: (value: unknown) => void = () => {};
    fetchPersonalities.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      })
    );
    act(() => {
      void usePersonalityStore.getState().refetch();
    });

    expect(screen.getByTestId('busy')).toHaveAttribute('data-busy', 'true');
    await act(async () => {
      resolve({ personalities: [CALM, SHARP], count: 2 });
    });
    await waitFor(() => expect(screen.getByTestId('busy')).toHaveAttribute('data-busy', 'false'));
  });
});
