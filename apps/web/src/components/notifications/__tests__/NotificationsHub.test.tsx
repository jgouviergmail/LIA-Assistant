/**
 * The notifications hub — five folded sections, and nothing fetched until one
 * is opened.
 *
 * The rules that matter here are the ones a reader would notice being broken:
 *
 *  - arriving costs ZERO requests (five sections, all folded, children
 *    unmounted). A hub that fires five queries to show five closed headings
 *    would be worse than the four settings pages it replaces;
 *  - a section disabled on this instance is ABSENT, never greyed out
 *    (gate-keeper, ADR-061);
 *  - reminders and routines announce that they list the FUTURE — a reminder is
 *    deleted the moment it fires, so a reader hunting for a history there
 *    would find an empty list and no reason for it;
 *  - the advanced links keep the existing settings deep links intact.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
const { patchMock } = vi.hoisted(() => ({ patchMock: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch: patchMock } }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({
  useApplicationAccountQuery: (endpoint: string, componentName: string) => ({
    ...useApiQuery(endpoint, { componentName }),
    ownerId: 'hub-owner',
  }),
}));

const { useAppConfig } = vi.hoisted(() => ({ useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
    i18n: { language: 'fr' },
  }),
}));

import { NotificationsHub } from '../NotificationsHub';

function flags(over: Record<string, boolean> = {}) {
  useAppConfig.mockReturnValue({
    config: { features: { peers_enabled: true, heartbeat_enabled: true, ...over } },
  });
}

/**
 * Which DISTINCT endpoints were asked for with `enabled: true`.
 *
 * Deduplicated on purpose: the mock records one call per render, so a single
 * open section appears several times and the oracle would count re-renders
 * instead of requests.
 */
function fetched(): string[] {
  return [
    ...new Set(
      useApiQuery.mock.calls
        .filter(([, options]) => (options as { enabled?: boolean }).enabled)
        .map(([endpoint]) => endpoint as string)
    ),
  ];
}

/**
 * Make the hub's single count read answer, leaving every paged read empty.
 *
 * Keyed on the endpoint rather than on call order: the five sections and the
 * counts share one mocked hook, and an order-based stub would silently drift
 * the day a section moves.
 */
function answerHubCounts(counts: Record<string, number>) {
  useApiQuery.mockImplementation((endpoint: string) =>
    endpoint === '/notifications/hub-counts'
      ? { data: counts, loading: false, error: null, refetch: vi.fn() }
      : { data: undefined, loading: false, error: null, refetch: vi.fn() }
  );
}

beforeEach(() => {
  useApiQuery.mockReset();
  useApiQuery.mockReturnValue({ data: undefined, loading: false, error: null, refetch: vi.fn() });
  patchMock.mockReset().mockResolvedValue({});
  useAppConfig.mockReset();
  flags();
});

describe('NotificationsHub', () => {
  it('states a failed count read separately and retries without unfolding histories', async () => {
    const refetch = vi.fn();
    useApiQuery.mockImplementation((endpoint: string) => ({
      data: endpoint === '/notifications/hub-counts' ? { proactive: 7 } : undefined,
      error: endpoint === '/notifications/hub-counts' ? new Error('offline') : null,
      loading: false,
      refetch,
    }));
    const { user } = renderWithProviders(<NotificationsHub lng="fr" />);
    expect(screen.getByRole('alert')).toHaveTextContent('notifications_hub.counts_error');
    expect(screen.getByText('7')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(refetch).toHaveBeenCalledOnce();
    expect(fetched()).toEqual([]);
  });
  it('heads the page like the activity timeline: switch, journal, refresh', () => {
    // Owner request 2026-10-21: the two views share one header.
    flags({ activity_timeline_enabled: true });
    renderWithProviders(<NotificationsHub lng="fr" />);

    const timeline = screen.getByRole('link', { name: 'activity.hub_cta' });
    expect(timeline).toHaveAttribute('href', '/fr/dashboard/activity');
    const journal = screen.getByRole('link', { name: 'effects.journal.title' });
    expect(journal).toHaveAttribute('href', '/fr/dashboard/actions');
    const refresh = screen.getByRole('button', { name: 'common.refresh' });
    for (const control of [timeline, journal, refresh]) expect(control).toHaveClass('min-h-11');
  });

  it('keeps the journal and the refresh when the timeline is not served', () => {
    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.queryByRole('link', { name: 'activity.hub_cta' })).toBeNull();
    expect(screen.getByRole('link', { name: 'effects.journal.title' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.refresh' })).toBeInTheDocument();
  });

  it('re-reads the totals and every open section in one press', async () => {
    // One spy per PATH: a paged section's endpoint carries its page in the query.
    const reads: Record<string, ReturnType<typeof vi.fn>> = {};
    const readOf = (endpoint: string) => (reads[endpoint.split('?')[0]] ??= vi.fn());
    useApiQuery.mockImplementation((endpoint: string) => ({
      data: endpoint === '/notifications/hub-counts' ? { reminders: 1 } : undefined,
      loading: false,
      error: null,
      refetch: readOf(endpoint),
    }));
    const { user } = renderWithProviders(<NotificationsHub lng="fr" />);
    await user.click(screen.getByText('notifications_hub.sections.reminders.title'));

    await user.click(screen.getByRole('button', { name: 'common.refresh' }));

    // The totals follow the application signal the press publishes, so they
    // are read ONCE — never a second read racing it.
    await waitFor(() => expect(readOf('/notifications/hub-counts')).toHaveBeenCalledOnce());
    expect(readOf('/reminders')).toHaveBeenCalledOnce();
  });

  it('ignores the refresh while the totals are still being read', async () => {
    const counts = vi.fn();
    useApiQuery.mockImplementation((endpoint: string) => ({
      data: undefined,
      loading: endpoint === '/notifications/hub-counts',
      error: null,
      refetch: endpoint === '/notifications/hub-counts' ? counts : vi.fn(),
    }));
    const { user } = renderWithProviders(<NotificationsHub lng="fr" />);
    const refresh = screen.getByRole('button', { name: 'common.refresh' });

    await user.click(refresh);

    expect(counts).not.toHaveBeenCalled();
    expect(refresh).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows the five sections folded, and fetches no PAGE', () => {
    renderWithProviders(<NotificationsHub lng="fr" />);

    for (const key of ['peer_messages', 'proactive', 'interests', 'reminders', 'scheduled']) {
      expect(screen.getByText(`notifications_hub.sections.${key}.title`)).toBeInTheDocument();
    }
    // No page of rows. The badge counts are a separate, cheap read — asserted
    // below — and they are what makes a folded section choosable at all.
    expect(fetched()).toEqual([]);
  });

  it('badges every folded section with its exact total, before any unfold', () => {
    // The defect this pins: the badge read "—" until the section was opened,
    // so the one number that decides whether to open a section could only be
    // obtained by opening it.
    answerHubCounts({
      peer_messages: 3,
      proactive: 12,
      interests: 0,
      reminders: 7,
      scheduled: 2,
      offers: 5,
    });

    renderWithProviders(<NotificationsHub lng="fr" />);

    for (const total of ['3', '12', '7', '2', '5']) {
      expect(screen.getByText(total)).toBeInTheDocument();
    }
    // Zero is a REAL answer: an empty section reads as empty, never as unknown.
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.queryByText('—')).toBeNull();
  });

  it('says "—" rather than "0" while the counts are still unknown', () => {
    // "0" would be a claim nobody has verified yet; an em dash is the honest
    // shape of "not known".
    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.getAllByText('—')).toHaveLength(6);
  });

  it('fetches only the section the reader opened', async () => {
    const { user } = renderWithProviders(<NotificationsHub lng="fr" />);

    await user.click(screen.getByText('notifications_hub.sections.interests.title'));

    await waitFor(() => expect(fetched()).toHaveLength(1));
    expect(fetched()[0]).toContain('/interests/notifications/history');
    expect(fetched()[0]).toContain('limit=10');
  });

  it('omits a section the instance has disabled, rather than greying it out', () => {
    flags({ peers_enabled: false, heartbeat_enabled: false });

    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.queryByText('notifications_hub.sections.peer_messages.title')).toBeNull();
    expect(screen.queryByText('notifications_hub.sections.proactive.title')).toBeNull();
    // The three that do not depend on an instance flag are still there.
    expect(screen.getByText('notifications_hub.sections.interests.title')).toBeInTheDocument();
  });

  it('says under each title what the section holds', () => {
    // Load-bearing for reminders and routines: they list the FUTURE, and a
    // reader looking there for what they were notified of would find nothing
    // with no explanation.
    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.getByText('notifications_hub.sections.reminders.subtitle')).toBeInTheDocument();
    expect(screen.getByText('notifications_hub.sections.scheduled.subtitle')).toBeInTheDocument();
  });

  it('removes advanced settings shortcuts without fetching notification pages', () => {
    renderWithProviders(<NotificationsHub lng="fr" />);
    expect(screen.queryByText('notifications_hub.advanced_title')).not.toBeInTheDocument();
    expect(fetched()).toEqual([]);
  });

  it('shows a dash rather than a zero before a section has ever been read', () => {
    // "0" is a claim; nobody has counted anything yet.
    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(5);
  });
});

describe('what the badge colour says', () => {
  it('tints the pill of a section that holds something', () => {
    // "How many" is the second question. The first is "is there anything
    // here?", and a grey pill on both an empty and a full section answered
    // only the second.
    answerHubCounts({ peer_messages: 0, proactive: 12, interests: 0, reminders: 7, scheduled: 0 });

    renderWithProviders(<NotificationsHub lng="fr" />);

    expect(screen.getByText('12').className).toMatch(/bg-primary/);
    expect(screen.getByText('7').className).toMatch(/bg-primary/);
  });

  it('tints a zero too — an empty section is a fact, not another kind of thing', () => {
    // Owner call (2026-08-04): every count wears the app's badge colour. The
    // earlier rule tinted only non-empty sections, which made one pill look
    // like a different component.
    answerHubCounts({ peer_messages: 0, proactive: 0, interests: 0, reminders: 0, scheduled: 0 });

    renderWithProviders(<NotificationsHub lng="fr" />);

    for (const pill of screen.getAllByText('0')) {
      expect(pill.className).toMatch(/bg-primary/);
    }
  });

  it('leaves the UNKNOWN state neutral — it is not a count', () => {
    renderWithProviders(<NotificationsHub lng="fr" />);

    for (const pill of screen.getAllByText('—')) {
      expect(pill.className).not.toMatch(/bg-primary/);
    }
  });
});

describe('notification registers', () => {
  it('places upcoming items before delivered histories in reading order, after decisions', () => {
    flags({ workboard_enabled: true });
    renderWithProviders(<NotificationsHub lng="fr" />);
    const future = screen.getByRole('region', { name: 'notifications_hub.groups.upcoming' });
    const received = screen.getByRole('region', { name: 'notifications_hub.groups.received' });
    expect(
      future.compareDocumentPosition(received) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    for (const key of ['reminders', 'scheduled', 'workboard']) {
      expect(
        within(future).getByText(`notifications_hub.sections.${key}.title`)
      ).toBeInTheDocument();
    }
    for (const key of ['peer_messages', 'proactive', 'interests']) {
      expect(
        within(received).getByText(`notifications_hub.sections.${key}.title`)
      ).toBeInTheDocument();
    }
    const offers = screen.getByText('notifications_hub.sections.offers.title');
    expect(offers.compareDocumentPosition(future) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fetched()).toEqual([]);
  });
});

it('does not resurrect a decided offer when folded during a failed refresh', async () => {
  const payload = {
    notifications: [
      {
        id: 'offer-once',
        content: 'Préparer le rendez-vous ?',
        created_at: '2026-10-15T10:00:00Z',
        priority: 'low',
        sources_used: [],
        user_feedback: null,
      },
    ],
    total: 1,
  };
  const refetch = vi.fn();
  useApiQuery.mockImplementation((endpoint: string) => ({
    data: endpoint.startsWith('/heartbeat/offers') ? payload : undefined,
    loading: false,
    error: new Error('offline'),
    refetch,
  }));
  const { user } = renderWithProviders(<NotificationsHub lng="fr" />);
  const title = screen.getByText('notifications_hub.sections.offers.title');
  await user.click(title);
  await user.click(
    screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' })
  );
  await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
  expect(title.closest('summary')).toHaveFocus();
  await user.click(title);
  await user.click(title);
  expect(screen.queryByText('Préparer le rendez-vous ?')).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'notifications_hub.sections.offers.dismiss' })
  ).not.toBeInTheDocument();
});

it('keeps an in-flight decision locked across folding and reopening', async () => {
  let complete!: () => void;
  patchMock.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        complete = resolve;
      })
  );
  const payload = {
    notifications: [
      {
        id: 'offer-in-flight',
        content: 'Préparer le rendez-vous ?',
        created_at: '2026-10-15T10:00:00Z',
        priority: 'low',
        sources_used: [],
        user_feedback: null,
      },
    ],
    total: 1,
  };
  useApiQuery.mockImplementation((endpoint: string) => ({
    data: endpoint.startsWith('/heartbeat/offers') ? payload : undefined,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }));
  const { user } = renderWithProviders(<NotificationsHub lng="fr" />);
  const title = screen.getByText('notifications_hub.sections.offers.title');
  await user.click(title);
  await user.click(
    screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' })
  );
  await user.click(title);
  await user.click(title);
  const decline = screen.getByRole('button', { name: 'notifications_hub.sections.offers.dismiss' });
  expect(decline).toHaveAttribute('aria-disabled', 'true');
  await user.click(decline);
  expect(patchMock).toHaveBeenCalledTimes(1);
  complete();
  await waitFor(() =>
    expect(screen.queryByText('Préparer le rendez-vous ?')).not.toBeInTheDocument()
  );
});
