/**
 * OpenLoopsSection (UXR Lot 7, B5) — flag/availability gating, direction
 * groups, and the three one-tap actions (done / relaunch prefill /
 * dismissed). Actions are named with the loop subject (a11y).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { OpenLoop } from '@/hooks/useOpenLoops';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));

const close = vi.fn(async () => true);
const refetch = vi.fn();
const state = {
  flagOn: true,
  unavailable: false,
  loadError: false,
  loops: [] as OpenLoop[],
};

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { open_loops_enabled: state.flagOn } },
  }),
}));
vi.mock('@/hooks/useOpenLoops', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useOpenLoops')>();
  return {
    ...original,
    useOpenLoops: () => ({
      loops: state.loops,
      loading: false,
      unavailable: state.unavailable,
      loadError: state.loadError,
      refetch,
      close,
    }),
  };
});

import { OpenLoopsSection } from '../OpenLoopsSection';

function loop(over: Partial<OpenLoop> = {}): OpenLoop {
  return {
    id: 'l-1',
    subject: 'rappeler le plombier',
    counterparty: 'le plombier',
    direction: 'user_owes',
    due_hint: null,
    created_at: '2026-07-20T08:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.flagOn = true;
  state.unavailable = false;
  state.loadError = false;
  state.loops = [
    loop(),
    loop({ id: 'l-2', subject: 'réponse de Marc', direction: 'waiting_on_other' }),
  ];
});

function renderSection() {
  return render(<OpenLoopsSection lng="fr" collapsible={false} />);
}

describe('OpenLoopsSection', () => {
  it('renders both direction groups with their loops', () => {
    renderSection();
    expect(screen.getByText('settings.open_loops.owed_title')).toBeInTheDocument();
    expect(screen.getByText('settings.open_loops.waiting_title')).toBeInTheDocument();
    expect(screen.getByText('rappeler le plombier')).toBeInTheDocument();
    expect(screen.getByText('réponse de Marc')).toBeInTheDocument();
  });

  it('renders nothing when the instance flag is off (gate-keeper)', () => {
    state.flagOn = false;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('a transient load failure offers a retry instead of vanishing', () => {
    state.loadError = true;
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders nothing when the surface is unavailable (404-tolerance)', () => {
    state.unavailable = true;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('closes as done through the hook', async () => {
    renderSection();
    // The i18n stub echoes keys without interpolation — index 0 is loop l-1.
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.open_loops.done' })[0]);
    await waitFor(() => expect(close).toHaveBeenCalledWith('l-1', 'done'));
  });

  it('dismisses as no-longer-relevant through the hook', async () => {
    renderSection();
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.open_loops.dismiss' })[1]);
    await waitFor(() => expect(close).toHaveBeenCalledWith('l-2', 'dismissed'));
  });

  it('relaunches into a prefilled chat — never a send', () => {
    renderSection();
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.open_loops.relaunch' })[0]);
    expect(openChat).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(close).not.toHaveBeenCalled();
  });

  it('shows the automatic-ledger empty state', () => {
    state.loops = [];
    renderSection();
    expect(screen.getByText('settings.open_loops.empty')).toBeInTheDocument();
  });
});
