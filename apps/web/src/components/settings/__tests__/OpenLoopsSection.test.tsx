/**
 * OpenLoopsSection (UXR Lot 7, B5) — flag/availability gating, direction
 * groups, and the three one-tap actions (done / relaunch prefill /
 * dismissed). Rows expose their actions through `RowActions` (ADR-208): short
 * per-action labels, the phone "⋮" menu named with the loop subject (a11y).
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
// A PARTIAL hook mock is its own defect: the component would call an
// undefined `update` and the suite would blame the component.
const update = vi.fn(async () => true);
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
      update,
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
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.open_loops.done_label' })[0]);
    await waitFor(() => expect(close).toHaveBeenCalledWith('l-1', 'done'));
  });

  it('dismisses as no-longer-relevant through the hook', async () => {
    renderSection();
    fireEvent.click(
      screen.getAllByRole('button', { name: 'settings.open_loops.dismiss_label' })[1]
    );
    await waitFor(() => expect(close).toHaveBeenCalledWith('l-2', 'dismissed'));
  });

  it('relaunches into a prefilled chat — never a send', () => {
    renderSection();
    fireEvent.click(
      screen.getAllByRole('button', { name: 'settings.open_loops.relaunch_label' })[0]
    );
    expect(openChat).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(close).not.toHaveBeenCalled();
  });

  it('names each row menu with its loop subject — never an anonymous "⋮"', () => {
    renderSection();
    // The i18n stub echoes keys, so both rows read `common.actions_for`; the
    // per-row uniqueness contract lives in the interpolated name parameter.
    expect(screen.getAllByRole('button', { name: 'common.actions_for' })).toHaveLength(2);
  });

  it('shows the automatic-ledger empty state', () => {
    state.loops = [];
    renderSection();
    expect(screen.getByText('settings.open_loops.empty')).toBeInTheDocument();
  });
});

describe('correcting a commitment the extractor got wrong', () => {
  // The i18n stub echoes KEYS without interpolation, so controls are addressed
  // by their key — the same convention as the suite above.
  const openEditor = () => {
    renderSection();
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.open_loops.edit_label' })[0]);
  };

  it('opens an editor seeded with the current wording', async () => {
    openEditor();

    // Seeding matters: an empty field would read as a NEW entry, and the
    // ledger deliberately has no manual creation.
    await waitFor(() =>
      expect(screen.getByDisplayValue('rappeler le plombier')).toBeInTheDocument()
    );
  });

  it('sends only what actually changed', async () => {
    openEditor();

    const field = await screen.findByDisplayValue('rappeler le plombier');
    fireEvent.change(field, { target: { value: 'rappeler le plombier mardi' } });
    fireEvent.click(screen.getByRole('button', { name: 'settings.open_loops.edit_save' }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith('l-1', { subject: 'rappeler le plombier mardi' })
    );
  });

  it('refuses to save an empty commitment', async () => {
    openEditor();

    const field = await screen.findByDisplayValue('rappeler le plombier');
    fireEvent.change(field, { target: { value: '   ' } });
    const save = screen.getByRole('button', { name: 'settings.open_loops.edit_save' });

    // `aria-disabled`, never `disabled`: a disabled control that HAS focus
    // blurs and drops out of the tab order mid-interaction.
    expect(save).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(save);
    expect(update).not.toHaveBeenCalled();
  });

  it('leaves the row alone when the user cancels', async () => {
    openEditor();
    fireEvent.click(await screen.findByRole('button', { name: 'common.cancel' }));

    await waitFor(() => expect(screen.queryByDisplayValue('rappeler le plombier')).toBeNull());
    expect(update).not.toHaveBeenCalled();
  });
});
