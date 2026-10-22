/**
 * HeartbeatHistory — what the proactive engine actually said.
 *
 * The endpoint has existed since the domain shipped and nothing consumed it:
 * the panel showed the configuration and never its output, so there was no way
 * to see what LIA chose to say, from which sources, or to judge it.
 *
 * The oracles are the facts a reader needs to audit a notification — when, what
 * about, from where, how urgent, and what they already answered — plus the two
 * failure modes a list like this gets wrong: a refresh that unmounts the rows,
 * and a count that describes the page instead of the set.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

// The global stub returns the bare key, which cannot show whether the EXACT
// total reached the label. This one interpolates (same pattern as
// `ForYouCard.test.tsx`), so "10 of 137" is a testable claim.
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

import { HeartbeatHistory } from '../HeartbeatHistory';
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';

function notification(over: Partial<HeartbeatNotification> = {}): HeartbeatNotification {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    created_at: '2026-08-01T09:30:00Z',
    content: 'Il pleuvra cet après-midi, prends un parapluie.',
    sources_used: ['CURRENT_WEATHER'],
    priority: 'medium',
    user_feedback: null,
    ...over,
  };
}

function makeProps(
  over: Partial<React.ComponentProps<typeof HeartbeatHistory>> = {}
): React.ComponentProps<typeof HeartbeatHistory> {
  return {
    notifications: [notification()],
    total: 1,
    firstLoad: false,
    loading: false,
    error: null,
    locale: 'fr',
    ...over,
  };
}

describe('HeartbeatHistory — reading what was delivered', () => {
  it('shows the message, its sources and its priority', () => {
    renderWithProviders(<HeartbeatHistory {...makeProps()} />);

    expect(screen.getByText(/Il pleuvra cet après-midi/)).toBeInTheDocument();
    expect(screen.getByText('heartbeat.history.source_CURRENT_WEATHER')).toBeInTheDocument();
    expect(screen.getByText('heartbeat.history.priority_medium')).toBeInTheDocument();
  });

  it('renders a source label it does not know without leaking the raw key', () => {
    // A new backend label must never surface as `heartbeat.history.source_X`.
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({ notifications: [notification({ sources_used: ['NEW'] })] })}
      />
    );

    expect(screen.queryByText(/heartbeat\.history\.source_NEW/)).not.toBeInTheDocument();
    expect(screen.getByText('NEW')).toBeInTheDocument();
  });

  it('reports the verdict already given, and its absence', () => {
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({
          notifications: [
            notification({ id: 'a', user_feedback: 'thumbs_up' }),
            notification({ id: 'b', user_feedback: null }),
          ],
          total: 2,
        })}
      />
    );

    expect(screen.getByText('heartbeat.history.feedback_thumbs_up')).toBeInTheDocument();
    expect(screen.getByText('heartbeat.history.feedback_none')).toBeInTheDocument();
  });

  it('states the exact total, not the size of the page', () => {
    // The backend counts with an aggregate over the whole set; a "10 shown"
    // that silently means "10 exist" is the claim ADR-185 forbids.
    renderWithProviders(<HeartbeatHistory {...makeProps({ total: 137 })} />);

    expect(screen.getByText(/shown=1/)).toBeInTheDocument();
    expect(screen.getByText(/total=137/)).toBeInTheDocument();
  });
});

describe('HeartbeatHistory — states', () => {
  it('explains an empty history rather than showing nothing', () => {
    renderWithProviders(<HeartbeatHistory {...makeProps({ notifications: [], total: 0 })} />);

    expect(screen.getByText('heartbeat.history.empty')).toBeInTheDocument();
  });

  it('shows a spinner on FIRST load only', () => {
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({ notifications: undefined, firstLoad: true, loading: true })}
      />
    );

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('keeps the rows mounted while refreshing, and says it is busy', () => {
    // `loading ? <Spinner/> : rows` would unmount the list on every refetch.
    renderWithProviders(<HeartbeatHistory {...makeProps({ firstLoad: false, loading: true })} />);

    expect(screen.getByText(/Il pleuvra cet après-midi/)).toBeInTheDocument();
    expect(screen.getByRole('list')).toHaveAttribute('aria-busy', 'true');
  });

  it('reports a failure instead of pretending the history is empty', () => {
    renderWithProviders(
      <HeartbeatHistory {...makeProps({ notifications: undefined, error: new Error('boom') })} />
    );

    expect(screen.getByRole('alert')).toHaveTextContent('heartbeat.history.error');
    expect(screen.queryByText('heartbeat.history.empty')).not.toBeInTheDocument();
  });
});

describe('rendering values the frontend was not told about', () => {
  // The sources list already guards this: an unknown label renders raw rather
  // than as `heartbeat.history.source_X`. Priority is the same kind of value —
  // a plain string column, documented as low/medium/high but not constrained
  // by an enum — and it had no guard at all.
  it('never shows a raw i18n key for a priority it does not know', () => {
    renderWithProviders(
      <HeartbeatHistory
        notifications={[notification({ priority: 'urgent' })]}
        total={1}
        firstLoad={false}
        loading={false}
        error={null}
        locale="en"
      />
    );

    expect(screen.queryByText(/heartbeat\.history\.priority_/)).not.toBeInTheDocument();
    // The value itself is more useful than nothing, and honest about what the
    // backend actually said.
    expect(screen.getByText('urgent')).toBeInTheDocument();
  });

  it('still localizes the three it does know', () => {
    renderWithProviders(
      <HeartbeatHistory
        notifications={[notification({ priority: 'high' })]}
        total={1}
        firstLoad={false}
        loading={false}
        error={null}
        locale="en"
      />
    );

    expect(screen.getByText('heartbeat.history.priority_high')).toBeInTheDocument();
  });
});

describe('how the three priorities are told apart', () => {
  /** The rendered marker of the first row. */
  function marker(): HTMLElement {
    const badge = document.querySelector('[data-slot="badge"], .rounded-full');
    if (!badge) throw new Error('no priority marker rendered');
    return badge as HTMLElement;
  }

  it('fills for `high` and only tints for `medium`', () => {
    // Hue alone cannot carry this: `--color-destructive` sits at 27° and
    // `--color-warning` at 50° in OKLCH — 23° apart, indistinguishable at the
    // 10 % opacity both markers used to share. DENSITY is what separates them,
    // and it still works for a reader who cannot tell the two hues apart.
    const { unmount } = renderWithProviders(
      <HeartbeatHistory {...makeProps({ notifications: [notification({ priority: 'high' })] })} />
    );
    const high = marker().className;
    unmount();

    renderWithProviders(
      <HeartbeatHistory {...makeProps({ notifications: [notification({ priority: 'medium' })] })} />
    );
    const medium = marker().className;

    expect(high).not.toBe(medium);
    // The solid fill is the loud one; the tint is the quiet one.
    // A SOLID ground for `high`, a tint for `medium`. `bg-destructive` without
    // a slash is the whole point: `bg-destructive/10` would be another tint.
    expect(high).toMatch(/bg-destructive(?!\/)/);
    expect(medium).toMatch(/bg-warning\/10/);
  });

  it('leaves an unknown priority neutral rather than alarming', () => {
    // A level the backend adds later must not arrive shouting: rendering it
    // red because it is unrecognised would be a claim nobody made.
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({ notifications: [notification({ priority: 'critical' })] })}
      />
    );

    expect(marker().className).not.toMatch(/destructive|red/);
    // And its raw value is shown, never a missing i18n key.
    expect(screen.getByText('critical')).toBeInTheDocument();
  });
});

describe('HeartbeatHistory — what woke the decision (ADR-261)', () => {
  it('marks a notification that answered a Google push', () => {
    renderWithProviders(
      <HeartbeatHistory {...makeProps({ notifications: [notification({ trigger: 'push' })] })} />
    );
    expect(screen.getByText('heartbeat.history.trigger_push')).toBeInTheDocument();
  });

  it('leaves the periodic tick unmarked — it is the norm, not an event', () => {
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({
          notifications: [notification({ trigger: 'tick' }), notification({ id: 'b' })],
        })}
      />
    );
    expect(screen.queryByText('heartbeat.history.trigger_push')).not.toBeInTheDocument();
  });
});

describe('HeartbeatHistory — presentation keeps the delivered words', () => {
  it.each(['panels', 'timeline'] as const)(
    'keeps the complete message, source and verdict as inert text in %s presentation',
    presentation => {
      const content = `${'Une information complète à conserver. '.repeat(20)}\n<img src=x onerror="alert(1)"> Dernière ligne.`;
      const { container } = renderWithProviders(
        <HeartbeatHistory
          {...makeProps({
            presentation,
            notifications: [
              notification({ content, user_feedback: 'thumbs_down', trigger: 'push' }),
            ],
          })}
        />
      );

      expect(
        screen.getByText(content, { exact: true, collapseWhitespace: false, trim: false })
      ).toHaveTextContent('Dernière ligne.');
      expect(screen.getByText('heartbeat.history.feedback_thumbs_down')).toBeInTheDocument();
      expect(screen.getByText('heartbeat.history.source_CURRENT_WEATHER')).toBeInTheDocument();
      expect(screen.getByText('heartbeat.history.trigger_push')).toBeInTheDocument();
      expect(container.querySelector('img')).toBeNull();
      expect(container.querySelector('time')).toHaveAttribute('datetime', '2026-08-01T09:30:00Z');
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    }
  );
});

/** Kept in step with HeartbeatSourceLabel in heartbeat/schemas.py. */
const BACKEND_SOURCE_LABELS = [
  'UPCOMING_CALENDAR_EVENTS',
  'PENDING_TASKS',
  'UNREAD_EMAILS',
  'CURRENT_WEATHER',
  'WEATHER_CHANGES',
  'USER_INTERESTS',
  'USER_MEMORIES',
  'JOURNAL_ENTRIES',
  'HEALTH_SIGNALS',
  'UPCOMING_BIRTHDAYS',
  'OPEN_LOOPS',
  'DEPARTURE_ADVICE',
  'HABITS',
  'WORKBOARD',
  'ANTICIPATED_MOMENT',
];

describe('HeartbeatHistory — canonical sources and timeline reading order', () => {
  it.each(BACKEND_SOURCE_LABELS)('translates the backend source %s', source => {
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({ notifications: [notification({ sources_used: [source] })] })}
      />
    );

    expect(screen.getByText(`heartbeat.history.source_${source}`)).toBeInTheDocument();
    expect(screen.queryByText(source, { exact: true })).not.toBeInTheDocument();
  });

  it('recognizes canonical sources in historical lower-case labels without disguising unknown ones', () => {
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({
          notifications: [
            notification({ sources_used: ['anticipated_moment', 'current_weather', 'newSource'] }),
          ],
        })}
      />
    );

    expect(screen.getByText('heartbeat.history.source_ANTICIPATED_MOMENT')).toBeInTheDocument();
    expect(screen.getByText('heartbeat.history.source_CURRENT_WEATHER')).toBeInTheDocument();
    expect(screen.getByText('newSource')).toBeInTheDocument();
    expect(screen.queryByText('heartbeat.history.source_NEWSOURCE')).not.toBeInTheDocument();
  });

  it('titles the hub row by its date, the priority leading the line of source and verdict below it', () => {
    // Owner request 2026-10-21: the badge is the first element of the line
    // under the date, not the date's neighbour.
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({
          presentation: 'timeline',
          notifications: [notification({ user_feedback: 'thumbs_down' })],
        })}
      />
    );

    const row = screen.getByRole('listitem');
    const date = row.querySelector('time');
    if (date === null) throw new Error('the row has no date');
    const priority = within(row).getByText('heartbeat.history.priority_medium');
    const source = within(row).getByText('heartbeat.history.source_CURRENT_WEATHER');
    const verdict = within(row).getByText('heartbeat.history.feedback_thumbs_down');
    const message = within(row).getByText('Il pleuvra cet après-midi, prends un parapluie.');

    // The date stands alone on its line; the priority opens the next one.
    expect(date.parentElement).not.toContainElement(priority);
    const metaLine = source.parentElement?.parentElement;
    if (!metaLine) throw new Error('the source has no line');
    expect(metaLine).toContainElement(priority);
    expect(metaLine.firstElementChild).toContainElement(priority);
    expect(date.compareDocumentPosition(priority) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(source.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      verdict.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('frames each settings row as its own panel, read in the hub order', () => {
    // Owner request 2026-10-21: one sub-panel per notification, no rule
    // between two — and the same reading order as the hub's rows.
    renderWithProviders(
      <HeartbeatHistory
        {...makeProps({
          notifications: [
            notification({ id: 'n-1' }),
            notification({ id: 'n-2', content: 'Deuxième notification.' }),
          ],
        })}
      />
    );

    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row).toHaveClass('rounded-lg', 'border', 'bg-card');
      expect(row).not.toHaveClass('border-b');
    }
    const [first] = rows;
    const date = first.querySelector('time');
    if (date === null) throw new Error('the row has no date');
    const priority = within(first).getByText('heartbeat.history.priority_medium');
    const source = within(first).getByText('heartbeat.history.source_CURRENT_WEATHER');
    const message = within(first).getByText('Il pleuvra cet après-midi, prends un parapluie.');
    expect(date.parentElement).not.toContainElement(priority);
    expect(date.compareDocumentPosition(priority) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(source.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
