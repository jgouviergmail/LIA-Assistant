/**
 * The journal's last intervention reads like the proactive discussions' last
 * run (owner request 2026-10-21): what ran and when, then the chat meter's own
 * figures — the cache reads apart from IN, as the meter counts them.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { JournalLastCost } from '../JournalLastCost';
import type { JournalCostInfo } from '@/hooks/useJournals';

const cost: JournalCostInfo = {
  tokens_in: 1200,
  tokens_cache: 4357,
  tokens_out: 69,
  cost_eur: 0.0004,
  timestamp: '2026-10-21T08:30:00Z',
  source: 'extraction',
};

describe('JournalLastCost', () => {
  it('states what ran, when, and its figures in the meter vocabulary', () => {
    renderWithProviders(<JournalLastCost lng="fr" cost={cost} emoji="💬" />);

    const section = screen.getByRole('region', { name: 'journals.lastCost' });
    expect(within(section).getByText('journals.lastCostSources.extraction')).toBeInTheDocument();
    expect(section.querySelector('time')).toHaveAttribute('datetime', cost.timestamp);
    // The cache reads stand apart from IN, never folded into it.
    expect(section).toHaveTextContent('1 200 IN');
    expect(section).toHaveTextContent('4 357 CACHE');
    expect(section).toHaveTextContent('69 OUT');
    expect(section).toHaveTextContent('0,000400 €');
  });

  it('names a periodic consolidation', () => {
    renderWithProviders(
      <JournalLastCost lng="fr" cost={{ ...cost, source: 'consolidation' }} emoji="🔄" />
    );

    expect(screen.getByText('journals.lastCostSources.consolidation')).toBeInTheDocument();
  });

  it('draws nothing before the billing has written a snapshot', () => {
    renderWithProviders(
      <JournalLastCost
        lng="fr"
        cost={{
          tokens_in: null,
          tokens_cache: null,
          tokens_out: null,
          cost_eur: null,
          timestamp: null,
          source: null,
        }}
        emoji="💬"
      />
    );

    expect(screen.queryByRole('region')).toBeNull();
  });
});
