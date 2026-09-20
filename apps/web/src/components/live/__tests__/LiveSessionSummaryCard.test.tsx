/**
 * LiveSessionSummaryCard — the closing card: title, translated outcome, the
 * figures, LIA's cost (or the line saying there was nothing to count), and
 * nothing at all on any other row.
 */
import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { LiveSessionSummaryCard } from '../LiveSessionSummaryCard';

const SUMMARY = {
  type: 'live_session_summary',
  live_session_id: 'a'.repeat(32),
  live_summary: { outcome: 'ended', duration_seconds: 125, delegations: 2, voice_turns: 3 },
};

describe('LiveSessionSummaryCard', () => {
  it('renders nothing on a row that is not a summary', () => {
    const { container } = renderWithProviders(
      <LiveSessionSummaryCard metadata={{ type: 'live_turn', live_session_id: 'x' }} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('draws the title, the outcome, the figures and the cost', () => {
    renderWithProviders(<LiveSessionSummaryCard metadata={{ ...SUMMARY, cost_eur: 0.0123 }} />);
    expect(screen.getByText('live.summary.title')).toBeInTheDocument();
    expect(screen.getByText('· live.outcome.ended')).toBeInTheDocument();
    expect(screen.getByText('live.summary.body')).toBeInTheDocument();
    expect(screen.getByText('live.summary.cost')).toBeInTheDocument();
    expect(screen.queryByText('live.summary.no_cost')).not.toBeInTheDocument();
  });

  it('says how many times the session was prolonged, and nothing when never', () => {
    renderWithProviders(
      <LiveSessionSummaryCard
        metadata={{ ...SUMMARY, live_summary: { ...SUMMARY.live_summary, extensions: 2 } }}
      />
    );
    expect(screen.getByText(/live\.summary\.extended/)).toBeInTheDocument();
    renderWithProviders(<LiveSessionSummaryCard metadata={SUMMARY} />);
    expect(screen.getAllByText(/live\.summary\.extended/)).toHaveLength(1);
  });

  it('says there was nothing to count when no request reached LIA', () => {
    renderWithProviders(<LiveSessionSummaryCard metadata={SUMMARY} />);
    expect(screen.getByText('live.summary.no_cost')).toBeInTheDocument();
  });

  it('counts no exchange on a DIRECT session, which archived none (ADR-300 wave 4)', () => {
    renderWithProviders(
      <LiveSessionSummaryCard
        metadata={{
          ...SUMMARY,
          cost_eur: 0.02,
          live_summary: { ...SUMMARY.live_summary, mode: 'direct' },
        }}
      />
    );
    expect(screen.getByText('live.summary.body_direct')).toBeInTheDocument();
    expect(screen.queryByText('live.summary.body')).not.toBeInTheDocument();
    expect(screen.getByText('live.summary.cost')).toBeInTheDocument();
    expect(screen.queryByTestId('live-session-relay')).not.toBeInTheDocument();
  });

  it("says what became of a DIRECT session's words, and nothing on a delegated one (ADR-301)", () => {
    const { unmount } = renderWithProviders(
      <LiveSessionSummaryCard
        metadata={{
          ...SUMMARY,
          live_summary: { ...SUMMARY.live_summary, mode: 'direct', relay: 'waiting' },
        }}
      />
    );
    expect(screen.getByTestId('live-session-relay')).toHaveTextContent(
      'live.summary.relay.waiting'
    );
    unmount();
    renderWithProviders(
      <LiveSessionSummaryCard
        metadata={{ ...SUMMARY, live_summary: { ...SUMMARY.live_summary, relay: 'answered' } }}
      />
    );
    expect(screen.queryByTestId('live-session-relay')).not.toBeInTheDocument();
  });

  it('quotes the recap of words that could not become a turn, so nothing said is lost', () => {
    renderWithProviders(
      <LiveSessionSummaryCard
        metadata={{
          ...SUMMARY,
          live_summary: {
            ...SUMMARY.live_summary,
            mode: 'direct',
            relay: 'busy',
            relay_summary: 'The person asked for a reminder on Thursday.',
          },
        }}
      />
    );
    expect(screen.getByTestId('live-session-relay')).toHaveTextContent('live.summary.relay.busy');
    expect(screen.getByTestId('live-session-recap')).toHaveTextContent(
      'The person asked for a reminder on Thursday.'
    );
  });
});
