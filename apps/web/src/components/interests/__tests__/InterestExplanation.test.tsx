/**
 * InterestExplanation — the reason, not a score.
 *
 * The panel showed "46 %" and a date. Someone deciding whether to BLOCK a
 * subject could see the number and nothing about why: not how many signals,
 * not how old they were, not which conversation started it.
 *
 * What must hold:
 *
 *  - folded costs nothing (a list of thirty interests must not fire thirty
 *    queries to render thirty closed headings);
 *  - the uncertainty is stated in WORDS when the evidence is thin — that is
 *    what decides whether to keep or block a subject;
 *  - the coefficients are published, so the number can be rebuilt rather than
 *    trusted;
 *  - nothing on screen is a rank, a level or a comparison.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { InterestExplanationPayload } from '../InterestExplanation';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

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

import { InterestExplanation } from '../InterestExplanation';

const RICH: InterestExplanationPayload = {
  positive_signals: 6,
  negative_signals: 1,
  prior_alpha: 2,
  prior_beta: 1,
  base_weight: 0.8,
  decay_rate_per_day: 0.005,
  decay_floor: 0.1,
  days_since_last_mention: 20,
  effective_weight: 0.72,
  last_mentioned_at: '2026-07-15T09:00:00Z',
  last_notified_at: '2026-07-20T09:00:00Z',
  status: 'active',
  dormant_since: null,
};

/**
 * Answer per ENDPOINT, not once for everything.
 *
 * This block nests the shared provenance disclosure, which calls the same hook
 * with a different URL: a single blanket answer hands it an explanation
 * payload and it renders someone else's data.
 */
function answer(
  payload: InterestExplanationPayload | undefined,
  over: Record<string, unknown> = {}
) {
  useApiQuery.mockImplementation((endpoint: string) => {
    if (endpoint.endsWith('/provenance')) {
      return {
        data: { references: [], total: 0, kept_at_most: 5 },
        loading: false,
        error: null,
        refetch: vi.fn(),
      };
    }
    return {
      data: payload,
      loading: payload === undefined,
      error: null,
      refetch: vi.fn(),
      ...over,
    };
  });
}

function render() {
  return renderWithProviders(<InterestExplanation interestId="i1" locale="fr-FR" />);
}

/** Open the explanation block (folded by design). */
async function open(user: ReturnType<typeof render>['user']) {
  await user.click(screen.getByText('interests.explanation.title'));
}

beforeEach(() => {
  useApiQuery.mockReset();
  answer(undefined, { loading: false });
});

describe('InterestExplanation', () => {
  it('fetches nothing while folded', () => {
    render();

    expect(useApiQuery).toHaveBeenCalledWith(
      '/interests/i1/explanation',
      expect.objectContaining({ enabled: false })
    );
  });

  it('asks only once the reader opens it', async () => {
    const { user } = render();

    await open(user);

    await waitFor(() =>
      expect(useApiQuery).toHaveBeenCalledWith(
        '/interests/i1/explanation',
        expect.objectContaining({ enabled: true })
      )
    );
  });

  it('leads with the reason, carrying the signals and the applied weight', async () => {
    answer(RICH);
    const { user } = render();

    await open(user);

    expect(
      screen.getByText(/explanation\.summary\|positives=6\|negatives=1\|days=20\|weight=72 %/)
    ).toBeInTheDocument();
  });

  it('says in WORDS when the evidence is thin', async () => {
    // "Few signals, so this is still a guess" is what a reader deciding
    // whether to block a subject actually needs.
    answer({ ...RICH, positive_signals: 1, negative_signals: 0 });
    const { user } = render();

    await open(user);

    expect(screen.getByText('interests.explanation.low_confidence')).toBeInTheDocument();
  });

  it('stays quiet about confidence once the evidence is real', async () => {
    answer(RICH);
    const { user } = render();

    await open(user);

    expect(screen.queryByText('interests.explanation.low_confidence')).toBeNull();
  });

  it('publishes the coefficients so the number can be rebuilt', async () => {
    // ADR-184: an enforced constant the reader cannot see is a trap.
    answer(RICH);
    const { user } = render();

    await open(user);

    expect(
      screen.getByText(/explanation\.formula\|alpha=2\|beta=1\|rate=0\.5\|floor=10 %/)
    ).toBeInTheDocument();
  });

  it('says a never-notified interest was never notified', async () => {
    answer({ ...RICH, last_notified_at: null });
    const { user } = render();

    await open(user);

    expect(screen.getByText(/never_notified/)).toBeInTheDocument();
  });

  it('reports a failed read instead of an empty explanation', async () => {
    answer(undefined, { loading: false, error: new Error('boom') });
    const { user } = render();

    await open(user);

    expect(screen.getByRole('alert')).toHaveTextContent('interests.explanation.error');
  });

  it('shows no rank, level or comparison anywhere', async () => {
    // Explicit product rule: explaining the uncertainty, never competing.
    answer(RICH);
    const { user } = render();

    await open(user);

    const text = document.body.textContent ?? '';
    for (const forbidden of ['rank', 'level', 'score', 'percentile', 'badge', 'streak']) {
      expect(text.toLowerCase()).not.toContain(forbidden);
    }
  });

  it('offers the same provenance block the rest of the product uses', async () => {
    answer(RICH);
    const { user } = render();

    await open(user);

    expect(screen.getByText('provenance.title')).toBeInTheDocument();
  });
});

describe('where the explanation is offered', () => {
  it('is withheld below the `sm` breakpoint', () => {
    // Same owner call as the provenance block: six coefficients and four dates
    // are more than a phone should spend on an interest the reader is only
    // scrolling past.
    const { container } = renderWithProviders(
      <InterestExplanation interestId="abc" locale="fr" />
    );

    const root = container.querySelector('details');
    expect(root).toHaveClass('hidden');
    expect(root).toHaveClass('sm:block');
  });
});
