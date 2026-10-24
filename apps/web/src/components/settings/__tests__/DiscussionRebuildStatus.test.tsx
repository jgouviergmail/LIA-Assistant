import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { Language } from '@/i18n/settings';
import type { DiscussionActivity, DiscussionSettings } from '@/types/proactive-discussions';
import { DiscussionRebuildStatus } from '../DiscussionRebuildStatus';

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string) => {
      const strings: Record<string, string> = Object.fromEntries(
        Object.entries((lng === 'fr' ? fr : en).discussions)
          .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
          .map(([name, value]) => [`discussions.${name}`, value])
      );
      return strings[key] ?? key;
    },
  }),
}));

const ready: DiscussionSettings = {
  policy: {
    enabled: true,
    start_hour: 9,
    end_hour: 20,
    timezone: 'Europe/Paris',
    daily_max: 2,
    sources: ['calendar'],
    sensitive_topics: [],
    forbidden_topics: [],
    paused_until: null,
    revision: 1,
  },
  sources: [{ key: 'calendar', operations: ['recent'], indivisible: false, dependencies: [] }],
  producer_enabled: true,
  budget_configured: true,
  pause_hours: 24,
};

describe.each(['en', 'fr'] as const)('reconstruction status in %s', lng => {
  const messages = (lng === 'fr' ? fr : en).discussions;

  it('states all three cost-limit scopes even before a request, then clears the blocker when configured', () => {
    const { rerender } = render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={{ ...ready, budget_configured: false }}
        requested={false}
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_budget_blocked);
    expect(screen.queryByText(messages.rebuild_pending)).not.toBeInTheDocument();
    rerender(<DiscussionRebuildStatus lng={lng} settings={ready} requested />);
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_pending);
    expect(screen.queryByText(messages.rebuild_budget_blocked)).not.toBeInTheDocument();
  });

  it('does not announce pending work without a request when the producer is ready', () => {
    render(<DiscussionRebuildStatus lng={lng} settings={ready} requested={false} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('prioritizes a stopped producer over the missing budgets', () => {
    render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={{ ...ready, producer_enabled: false, budget_configured: false }}
        requested
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_producer_blocked);
  });

  it('explains an empty source selection when generation is otherwise available', () => {
    render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={{ ...ready, policy: { ...ready.policy, sources: [] } }}
        requested
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_sources_missing);
  });

  it('does not assert that a request can run while settings are unavailable', () => {
    render(<DiscussionRebuildStatus lng={lng} settings={undefined} requested />);
    expect(screen.getByRole('status')).toHaveTextContent(messages.load_error);
    expect(screen.queryByText(messages.rebuild_pending)).not.toBeInTheDocument();
  });
});

describe.each(['en', 'fr'] as const)('reconstruction progress in %s', lng => {
  const messages = (lng === 'fr' ? fr : en).discussions;
  const activity = (overrides: Partial<DiscussionActivity>): DiscussionActivity => ({
    rebuild: 'idle',
    obstacle: null,
    last_rebuild: null,
    last_update: null,
    last_run: null,
    budget: { configured: true, reached: null, resets_at: null },
    awaiting_reply: null,
    ...overrides,
  });

  it('announces a running rebuild with a decorative spinner', () => {
    const { container } = render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={ready}
        activity={activity({ rebuild: 'running' })}
        requested
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_running);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('names the server-side obstacle that holds a requested rebuild', () => {
    render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={ready}
        activity={activity({ rebuild: 'requested', obstacle: 'controls_over_budget' })}
        requested
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_controls_over_budget);
  });

  it('says a requested rebuild waits while a ceiling stops every run', () => {
    render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={ready}
        activity={activity({
          rebuild: 'requested',
          obstacle: 'ceiling_reached',
          budget: { configured: true, reached: 'owner_day', resets_at: '2026-10-22T00:00:00Z' },
        })}
        requested
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_ceiling_blocked);
    expect(screen.queryByText(messages.rebuild_pending)).not.toBeInTheDocument();
  });

  it('reads a pending rebuild from the server even before the context page reloads', () => {
    render(
      <DiscussionRebuildStatus
        lng={lng}
        settings={ready}
        activity={activity({ rebuild: 'requested' })}
        requested={false}
      />
    );
    expect(screen.getByRole('status')).toHaveTextContent(messages.rebuild_pending);
  });
});
