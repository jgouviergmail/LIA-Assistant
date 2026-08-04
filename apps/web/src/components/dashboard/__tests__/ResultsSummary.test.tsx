/**
 * ResultsSummary — what the assistant achieved, before what it consumed.
 *
 * The dashboard led with messages, tokens, Google requests and cost. Useful for
 * administration, but not the story of what the product is for. This block puts
 * outcomes first; the volumes move behind a "Consumption" disclosure.
 *
 * The oracle that matters most is the one about honesty: an instance that does
 * not measure outcomes must SAY so, never render four zeros — "you achieved
 * nothing" and "nothing is being measured" are different statements and only
 * one of them would be true.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ResultsSummary } from '../ResultsSummary';
import type { PersonalResults } from '@/hooks/usePersonalResults';

function results(over: Partial<PersonalResults> = {}): PersonalResults {
  return {
    cycle_start: '2026-08-01T00:00:00Z',
    useful_results: 12,
    actions: 5,
    automations: 3,
    commitments_closed: 2,
    measured: true,
    ...over,
  };
}

function makeProps(over: Partial<React.ComponentProps<typeof ResultsSummary>> = {}) {
  return { results: results(), firstLoad: false, error: null, locale: 'fr', ...over };
}

describe('ResultsSummary — outcomes first', () => {
  it('states each achievement with its own figure', () => {
    renderWithProviders(<ResultsSummary {...makeProps()} />);

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders a quiet cycle as real zeros', () => {
    // Zero is a true answer when measurement IS on.
    renderWithProviders(
      <ResultsSummary
        {...makeProps({
          results: results({
            useful_results: 0,
            actions: 0,
            automations: 0,
            commitments_closed: 0,
          }),
        })}
      />
    );

    expect(screen.getAllByText('0')).toHaveLength(4);
    expect(screen.queryByText('dashboard.results.not_measured')).not.toBeInTheDocument();
  });

  it('says nothing is measured rather than showing four zeros', () => {
    renderWithProviders(
      <ResultsSummary {...makeProps({ results: results({ measured: false }) })} />
    );

    expect(screen.getByText('dashboard.results.not_measured')).toBeInTheDocument();
    expect(screen.queryByText('12')).not.toBeInTheDocument();
  });

  it('never invents a figure the product does not measure', () => {
    // "Time saved" has no source here; it must not appear under any wording.
    renderWithProviders(<ResultsSummary {...makeProps()} />);

    expect(screen.queryByText(/time_saved|temps_gagne/i)).not.toBeInTheDocument();
  });
});

describe('ResultsSummary — states', () => {
  it('shows a loading indicator on FIRST load only', () => {
    renderWithProviders(<ResultsSummary {...makeProps({ results: undefined, firstLoad: true })} />);

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders nothing at all when the figures cannot be loaded', () => {
    // Better absent than wrong: a results block showing zeros because of a
    // failed request would misreport the reader's month.
    const { container } = renderWithProviders(
      <ResultsSummary {...makeProps({ results: undefined, error: new Error('boom') })} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
