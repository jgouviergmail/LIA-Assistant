/**
 * BriefingCard — honest freshness rendering (D-04).
 *
 * What must hold:
 *  - an ERROR with a stale payload renders THAT payload (dimmed) instead of a
 *    hole, dates it with the badge, and states the last attempt;
 *  - an ERROR without stale data keeps the historical bare-error body;
 *  - a cache-served OK section says "cache" next to its age — freshness is
 *    never implied to be live when it is not.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { AgendaData, CardSection } from '@/types/briefing';

import { BriefingCard } from '../BriefingCard';

function section(overrides: Partial<CardSection<AgendaData>> = {}): CardSection<AgendaData> {
  return {
    status: 'ok',
    data: { events: [{ title: 'Réunion', start_local: '14:00', end_local: null, location: null }] },
    generated_at: '2026-07-29T06:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
    ...overrides,
  };
}

function renderCard(cardSection: CardSection<AgendaData>, onErrorCta = vi.fn()) {
  return renderWithProviders(
    <BriefingCard<AgendaData>
      titleKey="dashboard.briefing.cards.agenda.title"
      icon={<span />}
      tone="sky"
      section={cardSection}
      isRefreshing={false}
      onRefresh={vi.fn()}
      emptyStateKey="dashboard.briefing.cards.agenda.empty"
      onErrorCta={onErrorCta}
      renderContent={data => <div data-testid="card-content">{data.events[0]?.title}</div>}
    />
  );
}

describe('BriefingCard — stale-while-error (D-04)', () => {
  const ERRORED_WITH_STALE = section({
    status: 'error',
    error_code: 'connector_network',
    error_message: 'Connecteur injoignable',
    stale_generated_at: '2026-07-29T05:00:00Z',
    last_attempt_at: '2026-07-29T07:00:00Z',
  });

  it('renders the stale payload instead of a hole', () => {
    renderCard(ERRORED_WITH_STALE);
    expect(screen.getByTestId('card-content')).toHaveTextContent('Réunion');
    // The error is still stated — stale data softens the failure, never hides it.
    expect(screen.getByText('Connecteur injoignable')).toBeInTheDocument();
  });

  it('dates the stale payload with the badge, labeled as cache', () => {
    renderCard(ERRORED_WITH_STALE);
    const time = document.querySelector('time');
    expect(time).not.toBeNull();
    expect(time).toHaveAttribute('dateTime', '2026-07-29T05:00:00Z');
    expect(time?.textContent).toContain('dashboard.briefing.from_cache_suffix');
  });

  it('states the age of the data and the last attempt', () => {
    renderCard(ERRORED_WITH_STALE);
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('dashboard.briefing.stale_data_age');
    expect(status).toHaveTextContent('dashboard.briefing.last_attempt_ago');
  });

  it('keeps the retry CTA wired on network errors', async () => {
    const onErrorCta = vi.fn();
    const { user } = renderCard(ERRORED_WITH_STALE, onErrorCta);
    await user.click(screen.getByRole('button', { name: 'dashboard.briefing.actions.retry' }));
    expect(onErrorCta).toHaveBeenCalledTimes(1);
  });

  it('without stale data, the error body stays bare (no invented content)', () => {
    renderCard(
      section({
        status: 'error',
        data: null,
        error_code: 'connector_network',
        last_attempt_at: '2026-07-29T07:00:00Z',
      })
    );
    expect(screen.queryByTestId('card-content')).not.toBeInTheDocument();
    expect(document.querySelector('time')).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('dashboard.briefing.last_attempt_ago');
  });
});

describe('BriefingCard — from_cache honesty (D-04)', () => {
  it('labels a cache-served OK section', () => {
    renderCard(section({ from_cache: true }));
    expect(document.querySelector('time')?.textContent).toContain(
      'dashboard.briefing.from_cache_suffix'
    );
  });

  it('does not label a live OK section', () => {
    renderCard(section());
    expect(document.querySelector('time')?.textContent).not.toContain(
      'dashboard.briefing.from_cache_suffix'
    );
  });
});
