import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { AgendaCard } from '../AgendaCard';
import type { AgendaData, CardSection } from '@/types/briefing';

const state = vi.hoisted(() => ({ timezone: 'Pacific/Honolulu', language: 'fr', open: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { timezone: state.timezone } }) }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: (href: string) => state.open(href) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: state.language },
    t: (key: string, args?: Record<string, unknown>) =>
      args?.title ? `${key} ${args.title} ${args.time}` : key,
  }),
}));

type Event = AgendaData['events'][number] & { start_at?: string | null; id?: string | null };
const event = (title: string, start_at?: string | null, extra: Partial<Event> = {}): Event => ({
  title,
  start_at,
  start_local: '14:30',
  end_local: '15:00',
  location: 'Salle A',
  ...extra,
});
function section(events: Event[]): CardSection<AgendaData> {
  return {
    status: 'ok',
    data: { events },
    generated_at: '2026-10-15T12:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}
function show(events: Event[]) {
  return renderWithProviders(
    <AgendaCard section={section(events)} isRefreshing={false} onRefresh={vi.fn()} />
  );
}
beforeEach(() => {
  state.timezone = 'Pacific/Honolulu';
  state.language = 'fr';
  vi.clearAllMocks();
});

describe('Agenda home day timeline', () => {
  it('separates real civil days in the account timezone, not the browser timezone', () => {
    show([
      event('Late today', '2026-10-15T00:30:00Z'),
      event('Early tomorrow', '2026-10-15T10:15:00Z'),
    ]);
    expect(screen.getAllByRole('heading', { level: 4 }).map(x => x.textContent)).toEqual([
      'mercredi 14 octobre',
      'jeudi 15 octobre',
    ]);
    expect(screen.getAllByText('14:30')).toHaveLength(2);
    expect(screen.getAllByText('15:00')).toHaveLength(2);
  });
  it('uses the compact server range but retains the original time in the chat intent', async () => {
    const { user } = show([
      event('Tomorrow', undefined, {
        start_local: '10:00 demain',
        end_local: '11:00 demain',
        time_range_local: 'demain 10:00 – 11:00',
      }),
    ]);
    expect(screen.getByText('demain 10:00 – 11:00')).toBeVisible();
    expect(screen.queryByText('11:00 demain')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /intents.event Tomorrow/ }));
    expect(state.open.mock.calls[0][0]).toContain(encodeURIComponent('10:00 demain'));
  });
  it('orders known dates and instants without dropping equal-title events', () => {
    show([
      event('Same title', '2026-10-16T20:00:00Z', { id: 'c' }),
      event('First appointment', '2026-10-15T19:00:00Z', { id: 'a' }),
      event('Same title', '2026-10-16T18:00:00Z', { id: 'b' }),
    ]);
    const entries = screen.getAllByRole('button', { name: /dashboard.briefing.intents.event / });
    expect(entries.map(x => x.textContent)).toEqual([
      expect.stringContaining('First appointment'),
      expect.stringContaining('Same title'),
      expect.stringContaining('Same title'),
    ]);
    expect(screen.getAllByRole('heading', { level: 4 })).toHaveLength(2);
  });
  it('uses the same day once across the repeated DST hour', () => {
    state.timezone = 'Europe/Paris';
    show([
      event('Before clocks change', '2026-10-25T00:30:00Z'),
      event('After clocks change', '2026-10-25T01:30:00Z'),
    ]);
    expect(screen.getAllByRole('heading', { level: 4 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('dimanche 25 octobre');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
  it('keeps legacy display-only rows without inventing a date or interpreting localized labels', () => {
    show([
      event('Legacy', undefined, { start_local: 'demain 09:00' }),
      event('Unknown date', 'invalid'),
    ]);
    expect(screen.queryByRole('heading', { level: 4 })).toBeNull();
    expect(screen.getByText('demain 09:00')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
  it('keeps all-day and missing-end labels as supplied instead of inventing midnight', () => {
    show([
      event('All day', '2026-10-14T10:00:00Z', {
        start_local: 'Journée entière',
        end_local: null,
        location: null,
      }),
    ]);
    expect(screen.getByText('Journée entière')).toBeInTheDocument();
    expect(screen.queryByText('00:00')).toBeNull();
    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('mercredi 14 octobre');
  });
  it('preserves the focused event when a refresh changes its hour and order in the same civil day', () => {
    const original = event('Moved meeting', '2026-10-15T19:00:00Z', {
      id: 'stable',
      start_local: '09:00',
    });
    const other = event('Another meeting', '2026-10-15T20:00:00Z', { id: 'other' });
    const view = show([original, other]);
    const target = screen.getByRole('button', { name: /intents.event Moved meeting/ });
    act(() => target.focus());
    expect(target).toHaveFocus();
    view.rerender(
      <AgendaCard
        section={section([
          { ...original, start_at: '2026-10-15T21:00:00Z', start_local: '11:00' },
          other,
        ])}
        isRefreshing={false}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /intents.event Moved meeting/ })).toBe(target);
    expect(target).toHaveFocus();
    expect(target).toHaveTextContent('11:00');
  });
  it('retains duplicate provider identities without creating duplicate React keys', () => {
    const error = vi.spyOn(console, 'error');
    show([
      event('First copy', '2026-10-15T19:00:00Z', { id: 'duplicate' }),
      event('Second copy', '2026-10-15T19:00:00Z', { id: 'duplicate' }),
    ]);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(error.mock.calls.flat().join(' ')).not.toMatch(/same key/);
    error.mockRestore();
  });
  it('falls back to supplied labels for an invalid account timezone', () => {
    state.timezone = 'broken/timezone';
    show([event('Conserved', '2026-10-15T00:30:00Z')]);
    expect(screen.queryByRole('heading', { level: 4 })).toBeNull();
    expect(screen.getByText('Conserved')).toBeInTheDocument();
  });
  it('localizes day headings and retains every received row and the existing draft action', async () => {
    state.language = 'de';
    const events = Array.from({ length: 14 }, (_, i) =>
      event(`Appointment ${i}`, `2026-10-15T${String(i + 10).padStart(2, '0')}:00:00Z`, {
        id: String(i),
      })
    );
    const { user } = show(events);
    expect(screen.getAllByRole('listitem')).toHaveLength(14);
    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('Donnerstag, 15. Oktober');
    const last = screen.getByRole('button', {
      name: /dashboard.briefing.intents.event Appointment 13 /,
    });
    await user.click(last);
    expect(state.open).toHaveBeenCalledTimes(1);
    const href = state.open.mock.calls[0][0] as string;
    expect(href).toContain('/de/dashboard/chat?draft=');
    expect(new URL(href, 'https://example.test').searchParams.get('draft')).toContain(
      'Appointment 13'
    );
    expect(within(last).getByText('Salle A')).toBeInTheDocument();
  });
});
