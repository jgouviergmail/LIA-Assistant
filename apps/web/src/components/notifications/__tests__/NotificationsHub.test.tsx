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

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { settingsSectionHref } from '@/lib/settings-sections';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

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
  useAppConfig.mockReset();
  flags();
});

describe('NotificationsHub', () => {
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

  it('keeps the existing settings deep links as the advanced route', () => {
    renderWithProviders(<NotificationsHub lng="fr" />);

    // Named after the DESTINATION, not after the hub section: the same words
    // twice on one page, meaning two different things, is how a reader loses
    // track of where a link goes.
    expect(
      screen.getByRole('link', { name: 'notifications_hub.advanced_links.proactive' })
    ).toHaveAttribute('href', settingsSectionHref('fr', 'heartbeat'));
    expect(
      screen.getByRole('link', { name: 'notifications_hub.advanced_links.device' })
    ).toHaveAttribute('href', settingsSectionHref('fr', 'notifications'));
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
