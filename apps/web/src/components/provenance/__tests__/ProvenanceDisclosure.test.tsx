/**
 * ProvenanceDisclosure — "why does LIA think this?"
 *
 * A journal entry showed a confidence dot and two counters ("✓3 / ✗1"): how
 * MANY signals, never WHICH. Three confirmations a reader cannot see are not
 * an explanation, and a conclusion they cannot examine is one they cannot
 * argue with.
 *
 * The rules a reader would notice being broken:
 *
 *  - folded costs nothing (the query fires when they ask, not on a list of
 *    forty entries);
 *  - a deleted source reads as a TOMBSTONE — a date and the fact that it is
 *    gone, never the words they deleted;
 *  - the cap is stated, so "5 signals" cannot read as "all of them";
 *  - "Correct" is offered, because provenance without a way to act on what it
 *    reveals is a read-only apology.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ProvenancePayload } from '../ProvenanceDisclosure';

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

import { ProvenanceDisclosure } from '../ProvenanceDisclosure';

function answer(payload: ProvenancePayload | undefined, over: Record<string, unknown> = {}) {
  useApiQuery.mockReturnValue({
    data: payload,
    loading: payload === undefined,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

const LIVE: ProvenancePayload = {
  references: [
    {
      id: 'r1',
      outcome: 'origin',
      captured_at: '2026-07-30T09:00:00Z',
      conversation_id: 'c1',
      excerpt: 'Je préfère toujours un résumé écrit.',
      is_tombstone: false,
    },
    {
      id: 'r2',
      outcome: 'contradiction',
      captured_at: '2026-08-01T09:00:00Z',
      conversation_id: null,
      excerpt: null,
      is_tombstone: true,
    },
  ],
  total: 2,
  kept_at_most: 5,
};

function render(over: Partial<React.ComponentProps<typeof ProvenanceDisclosure>> = {}) {
  return renderWithProviders(
    <ProvenanceDisclosure endpoint="/journals/j1/provenance" locale="fr-FR" {...over} />
  );
}

beforeEach(() => {
  useApiQuery.mockReset();
  answer(undefined, { loading: false });
});

describe('ProvenanceDisclosure', () => {
  it('costs nothing while folded', () => {
    render();

    expect(useApiQuery).toHaveBeenCalledWith(
      '/journals/j1/provenance',
      expect.objectContaining({ enabled: false })
    );
    // Folded means UNMOUNTED — not merely hidden.
    expect(screen.queryByText('provenance.empty')).toBeNull();
  });

  it('asks only once the reader opens it', async () => {
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    await waitFor(() =>
      expect(useApiQuery).toHaveBeenLastCalledWith(
        '/journals/j1/provenance',
        expect.objectContaining({ enabled: true })
      )
    );
  });

  it('shows a live signal with its own words', async () => {
    answer(LIVE);
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('Je préfère toujours un résumé écrit.')).toBeInTheDocument();
    expect(screen.getByText('provenance.outcome.origin')).toBeInTheDocument();
  });

  it('reads a deleted source as a tombstone, never as its text', async () => {
    // The one promise of the design: a deletion elsewhere is not undone here.
    answer(LIVE);
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('provenance.source_deleted')).toBeInTheDocument();
    // …and the entry is still dated, which is what a tombstone says.
    expect(screen.getByText('provenance.outcome.contradiction')).toBeInTheDocument();
  });

  it('states the cap next to the count', async () => {
    // "5 signals" must not read as "all of them" (ADR-184).
    answer(LIVE);
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('provenance.count|total=2|cap=5')).toBeInTheDocument();
  });

  it('says nothing was recorded rather than staying blank', async () => {
    answer({ references: [], total: 0, kept_at_most: 5 });
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('provenance.empty')).toBeInTheDocument();
  });

  it('reports a failed read BEFORE claiming there is no signal', async () => {
    // "LIA concluded this out of nothing" is a claim, and it may be false.
    answer(undefined, { loading: false, error: new Error('boom') });
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByRole('alert')).toHaveTextContent('provenance.error');
    expect(screen.queryByText('provenance.empty')).toBeNull();
  });

  it('offers the correction where the surface can host one', async () => {
    const onCorrect = vi.fn();
    answer(LIVE);
    const { user } = render({ onCorrect });

    await user.click(screen.getByText('provenance.title'));
    await user.click(screen.getByRole('button', { name: 'provenance.correct' }));

    expect(onCorrect).toHaveBeenCalledTimes(1);
  });

  it('offers no correction where there is no editor to open', async () => {
    // A control that leads nowhere is worse than an absent one.
    answer(LIVE);
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.queryByRole('button', { name: 'provenance.correct' })).toBeNull();
  });

  it('degrades to "nothing recorded" on a payload it did not expect', async () => {
    // This block renders INSIDE other panels (a journal entry, a memory, an
    // interest). Reading `.references.length` on a payload without the field
    // threw and took the whole surrounding list down through the error
    // boundary — measured while wiring the interests panel, 2026-08-04. A
    // surprising shape must degrade, never crash its host.
    useApiQuery.mockReturnValue({
      data: { unexpected: true },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('provenance.empty')).toBeInTheDocument();
  });

  it('renders an unknown outcome raw rather than as a missing key', async () => {
    answer({
      references: [
        {
          id: 'r3',
          outcome: 'reinforcement',
          captured_at: '2026-08-02T09:00:00Z',
          conversation_id: 'c9',
          excerpt: 'Encore une fois.',
          is_tombstone: false,
        },
      ],
      total: 1,
      kept_at_most: 5,
    });
    const { user } = render();

    await user.click(screen.getByText('provenance.title'));

    expect(screen.getByText('reinforcement')).toBeInTheDocument();
    expect(screen.queryByText('provenance.outcome.reinforcement')).toBeNull();
  });
});

describe('where the block is offered', () => {
  it('is withheld below the `sm` breakpoint', () => {
    // Owner call: on a phone this block — a list of dated signals — pushed the
    // memory or the journal entry the reader came for off the screen. CSS, not
    // an unmount: the disclosure already renders nothing while closed, and a
    // JS-driven variant would make the server and the first client paint
    // disagree.
    const { container } = renderWithProviders(
      <ProvenanceDisclosure endpoint="/memories/abc/provenance" locale="fr" />
    );

    const root = container.querySelector('details');
    expect(root).toHaveClass('hidden');
    expect(root).toHaveClass('sm:block');
  });
});
