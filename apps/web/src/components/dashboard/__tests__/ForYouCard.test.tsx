/**
 * « For you » card (P15, interdomain program Lot 4).
 *
 * Aggregates the commitments ledger (ADR-139) + automations digest (ADR-140).
 * Loop rows are real labelled buttons opening the chat prefilled with a
 * direction-aware intent (QW-9 `?draft=` pattern).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/__tests__/test-utils';

import { ForYouCard } from '../cards/ForYouCard';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { CardSection, ForYouData } from '@/types/briefing';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
}));

// The ledger's own hook, spied: acting in place must drive the SAME writes
// the settings ledger drives, not a second implementation.
const { close, update, useOpenLoops } = vi.hoisted(() => {
  const close = vi.fn().mockResolvedValue(true);
  const update = vi.fn().mockResolvedValue(true);
  return {
    close,
    update,
    useOpenLoops: vi.fn(() => ({
      loops: [],
      unavailable: false,
      loadError: null,
      refetch: vi.fn(),
      close,
      update,
    })),
  };
});
vi.mock('@/hooks/useOpenLoops', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useOpenLoops')>();
  return { ...actual, useOpenLoops };
});

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

function section(data: ForYouData | null, status = 'ok'): CardSection<ForYouData> {
  return {
    status: status as CardSection<ForYouData>['status'],
    data,
    generated_at: '2026-07-22T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

const fullData: ForYouData = {
  open_loops: [
    {
      id: 'l1',
      subject: 'rappeler le plombier',
      counterparty: 'le plombier',
      direction: 'user_owes',
      due_hint: null,
      days_open: 3,
    },
    {
      id: 'l2',
      subject: 'devis de Marie',
      counterparty: 'Marie',
      direction: 'waiting_on_other',
      due_hint: '2026-07-25T18:00:00Z',
      days_open: 9,
    },
  ],
  recent_automations: [
    {
      id: 'a1',
      title: 'Revue de presse IA',
      executed_at: '2026-07-22T06:00:00Z',
      next_trigger_at: null,
      next_trigger_local: null,
    },
  ],
  next_automation: {
    id: 'a2',
    title: 'Météo du matin',
    executed_at: null,
    next_trigger_at: '2026-07-23T06:00:00Z',
    next_trigger_local: '06:00 demain',
  },
};

describe('ForYouCard', () => {
  beforeEach(() => {
    openChat.mockClear();
  });

  it('renders loops with direction-aware intents and opens the chat on click', () => {
    render(<ForYouCard {...cardProps} section={section(fullData)} />);

    const owed = screen.getByRole('button', {
      name: /intents\.loop_owed\|subject=rappeler le plombier/,
    });
    fireEvent.click(owed);
    expect(openChat).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(openChat.mock.calls[0][0]).toContain(encodeURIComponent('rappeler le plombier'));

    // Waiting-direction loop gets the waiting intent
    expect(
      screen.getByRole('button', { name: /intents\.loop_waiting\|subject=devis de Marie/ })
    ).toBeInTheDocument();
  });

  it('sends the commitments heading to the ledger section, not to the settings root', () => {
    // The heading used to link to a bare `/dashboard/settings`, dropping the
    // reader at the top of ~30 collapsed accordions. `open-loops` is a
    // declared token, so the page activates the right tab, expands the
    // section and scrolls it clear of the sticky chrome.
    render(<ForYouCard {...cardProps} section={section(fullData)} />);

    const heading = screen.getByRole('link', {
      name: 'dashboard.briefing.cards.for_you.loops_title',
    });
    expect(heading).toHaveAttribute('href', settingsSectionHref('fr', 'open-loops'));
  });

  it('shows only the UPCOMING automation — past runs are not displayed', () => {
    render(<ForYouCard {...cardProps} section={section(fullData)} />);

    // Past executions (owner arbitration 2026-07-30): present in the payload,
    // absent from the card.
    expect(screen.queryByText('Revue de presse IA')).not.toBeInTheDocument();
    expect(
      screen.queryByText('dashboard.briefing.cards.for_you.ran_recently')
    ).not.toBeInTheDocument();
    // The upcoming one renders with its precise backend-formatted time.
    expect(screen.getByText('Météo du matin')).toBeInTheDocument();
    expect(screen.getByText('06:00 demain')).toBeInTheDocument();
    expect(screen.queryByText('dashboard.briefing.cards.for_you.next_up')).not.toBeInTheDocument();
  });

  it('renders no automations block at all when only past runs exist', () => {
    render(
      <ForYouCard {...cardProps} section={section({ ...fullData, next_automation: null })} />
    );
    expect(
      screen.queryByText('dashboard.briefing.cards.for_you.automations_title')
    ).not.toBeInTheDocument();
  });

  it('falls back to the next-up label when no local time is provided', () => {
    const data = {
      ...fullData,
      next_automation: {
        id: 'a2',
        title: 'Météo du matin',
        executed_at: null,
        next_trigger_at: '2026-07-23T06:00:00Z',
        next_trigger_local: null,
      },
    };
    render(<ForYouCard {...cardProps} section={section(data)} />);

    expect(screen.getByText('dashboard.briefing.cards.for_you.next_up')).toBeInTheDocument();
  });

  it('is hidden entirely when the section is not configured', () => {
    const { container } = render(
      <ForYouCard {...cardProps} section={section(null, 'not_configured')} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the empty state when the section is empty', () => {
    render(<ForYouCard {...cardProps} section={section(null, 'empty')} />);
    expect(screen.getByText('dashboard.briefing.cards.for_you.empty')).toBeInTheDocument();
  });
});

describe('acting on a commitment where the reader is looking at it', () => {
  // The ledger in settings already carries "Fait", "Plus d'actualité" and
  // "Modifier". Sending the reader there means finding the same row a second
  // time, on another page — so the three act in place, against the same hook
  // and the same editor the ledger uses. The heading still links to the full
  // ledger for everything else.
  //
  // No confirmation dialog, deliberately: `OpenLoopsSection` is documented as
  // "one-tap actions" and closing a commitment is not a deletion. Two gestures
  // for the same act on two surfaces would be the inconsistency.
  beforeEach(() => {
    // The hoisted mocks are module-scoped: without this, call counts add up
    // across tests and a "called once" assertion reads six.
    close.mockReset().mockResolvedValue(true);
    update.mockReset().mockResolvedValue(true);
    toast.error.mockClear();
    toast.success.mockClear();
  });

  const oneLoop: ForYouData = {
    open_loops: [
      {
        id: 'l1',
        subject: 'Rendre la perceuse',
        counterparty: null,
        direction: 'user_owes',
        due_hint: null,
        days_open: 4,
      },
    ],
    recent_automations: [],
    next_automation: null,
  };

  function renderCard() {
    return renderWithProviders(<ForYouCard {...cardProps} section={section(oneLoop)} />);
  }

  it('marks a commitment done without leaving the dashboard', async () => {
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_done' })
    );

    expect(close).toHaveBeenCalledWith('l1', 'done');
  });

  it('dismisses one that is no longer relevant', async () => {
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_dismiss' })
    );

    // A distinct verdict, not a second "done": the ledger records WHY a
    // commitment left, and collapsing the two would erase that.
    expect(close).toHaveBeenCalledWith('l1', 'dismissed');
  });

  it('opens the ledger editor rather than a second implementation', async () => {
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_edit' })
    );

    // The subject arrives prefilled — a correction starts from what is wrong,
    // never from an empty field.
    expect(await screen.findByDisplayValue('Rendre la perceuse')).toBeInTheDocument();
  });

  it('saves a correction through the same hook the ledger uses', async () => {
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_edit' })
    );
    const field = await screen.findByDisplayValue('Rendre la perceuse');
    await user.clear(field);
    await user.type(field, 'Rendre la scie');
    await user.click(screen.getByRole('button', { name: 'settings.open_loops.edit_save' }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith('l1', expect.objectContaining({ subject: 'Rendre la scie' }))
    );
  });

  it('refreshes the card so the closed commitment actually leaves it', async () => {
    // The card renders the BRIEFING section, not the hook's own list: without
    // an explicit refresh the row stays on screen after a successful close,
    // and the next click lands on a commitment the API has already closed —
    // `404 Open_loop not found`, which is exactly what shipped.
    const onRefresh = vi.fn();
    useOpenLoops.mockReturnValue({
      loops: [],
      unavailable: false,
      loadError: null,
      refetch: vi.fn(),
      close,
      update,
    });
    const { user } = renderWithProviders(
      <ForYouCard {...cardProps} onRefresh={onRefresh} section={section(oneLoop)} />
    );

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_done' })
    );

    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('does not refresh when the close failed — the row is still open', async () => {
    // Refreshing on failure would hide a commitment that is still there.
    close.mockResolvedValueOnce(false);
    const onRefresh = vi.fn();
    const { user } = renderWithProviders(
      <ForYouCard {...cardProps} onRefresh={onRefresh} section={section(oneLoop)} />
    );

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_dismiss' })
    );

    await waitFor(() => expect(close).toHaveBeenCalled());
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('refreshes after a correction too', async () => {
    const onRefresh = vi.fn();
    const { user } = renderWithProviders(
      <ForYouCard {...cardProps} onRefresh={onRefresh} section={section(oneLoop)} />
    );

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_edit' })
    );
    const field = await screen.findByDisplayValue('Rendre la perceuse');
    await user.clear(field);
    await user.type(field, 'Rendre la scie');
    await user.click(screen.getByRole('button', { name: 'settings.open_loops.edit_save' }));

    // Otherwise the card keeps showing the OLD subject until the next poll.
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('says so when the close fails, instead of leaving the row silently there', async () => {
    // The ledger toasts on failure. Here the row STAYS (the card renders the
    // briefing section, and no reload is asked for on failure), so silence
    // would read as "it worked" — the worst of the two readings.
    close.mockResolvedValueOnce(false);
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_done' })
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it('ignores a second click while the first close is still in flight', async () => {
    // The row stays visible until the reload lands, so a double click is
    // REACHABLE here — unlike the ledger, whose optimistic removal takes the
    // row away instantly. The second request would hit a commitment the API
    // just closed: `404 Open_loop not found`, which is what the user reported.
    let release: (value: boolean) => void = () => {};
    close.mockImplementationOnce(() => new Promise<boolean>(resolve => (release = resolve)));
    const { user } = renderCard();

    const done = await screen.findByRole('button', {
      name: 'dashboard.briefing.actions.loop_done',
    });
    await user.click(done);
    await user.click(done);

    expect(close).toHaveBeenCalledTimes(1);
    release(true);
  });

  it('marks the busy chip aria-disabled rather than disabled', async () => {
    // `disabled` on a focused control blurs it and drops it from the tab
    // order; the GUARD above is what prevents the double submit.
    let release: (value: boolean) => void = () => {};
    close.mockImplementationOnce(() => new Promise<boolean>(resolve => (release = resolve)));
    const { user } = renderCard();

    const done = await screen.findByRole('button', {
      name: 'dashboard.briefing.actions.loop_done',
    });
    await user.click(done);

    await waitFor(() => expect(done).toHaveAttribute('aria-disabled', 'true'));
    expect(done).not.toBeDisabled();
    release(true);
  });

  it('keeps the keyboard inside the card once the row is gone', async () => {
    // Closing removes the row the chips lived on. Without an anchor the
    // keyboard user is dropped on <body> — the defect already fixed on the
    // reminders card and the routines panel.
    const { user } = renderCard();

    await user.click(
      await screen.findByRole('button', { name: 'dashboard.briefing.actions.loop_done' })
    );

    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      expect(document.activeElement).toHaveAttribute('role', 'region');
    });
  });
});
