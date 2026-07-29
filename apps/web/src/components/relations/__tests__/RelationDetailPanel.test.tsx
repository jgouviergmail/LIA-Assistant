/**
 * RelationDetailPanel (N-09) — the 360° view of one relationship.
 *
 * What must hold: sections render their items; the best-effort banner shows
 * only on a normalized match; the "prepare 360°" button deep-links a chat
 * ?intent= (ADR-173); back returns to the list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RelationDetail } from '@/hooks/useRelations';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const { useRelationDetail } = vi.hoisted(() => ({ useRelationDetail: vi.fn() }));
vi.mock('@/hooks/useRelations', () => ({ useRelationDetail }));

import { RelationDetailPanel } from '../RelationDetailPanel';

function detail(over: Partial<RelationDetail> = {}): RelationDetail {
  return {
    display_name: 'Gérard Dupont',
    identity_confidence: 'exact',
    open_loops: [
      {
        id: 'l1',
        subject: 'Rendre la perceuse',
        direction: 'user_owes',
        due_hint: null,
        days_open: 4,
      },
    ],
    recent_calls: [
      {
        id: 'c1',
        objective: 'Anniversaire',
        outcome: 'objective_met',
        summary: 'RAS',
        created_at: '2026-07-20T10:00:00Z',
      },
    ],
    memories: [{ id: 'm1', content: 'Aime la randonnée' }],
    ...over,
  };
}

beforeEach(() => {
  push.mockClear();
  useRelationDetail.mockReset();
});

describe('RelationDetailPanel', () => {
  it('renders each populated section', () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderWithProviders(<RelationDetailPanel name="Gérard Dupont" lng="fr" onBack={vi.fn()} />);

    expect(screen.getByText('Rendre la perceuse')).toBeInTheDocument();
    expect(screen.getByText('Anniversaire')).toBeInTheDocument();
    expect(screen.getByText('Aime la randonnée')).toBeInTheDocument();
  });

  it('shows the best-effort banner on a normalized match', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ identity_confidence: 'normalized', memories: [] }),
      loading: false,
      error: false,
    });
    renderWithProviders(<RelationDetailPanel name="Gérard" lng="fr" onBack={vi.fn()} />);
    expect(screen.getByText('relations.identity_best_effort')).toBeInTheDocument();
  });

  it('shows the best-effort banner whenever a memory is attached, even on an exact match', () => {
    // Memories match by name substring — they can over-match even when the
    // loop/call identity is EXACT, so the caveat must show.
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    renderWithProviders(<RelationDetailPanel name="Gérard Dupont" lng="fr" onBack={vi.fn()} />);
    expect(screen.getByText('relations.identity_best_effort')).toBeInTheDocument();
  });

  it('hides the banner on an exact match with no memories', () => {
    useRelationDetail.mockReturnValue({
      detail: detail({ memories: [] }),
      loading: false,
      error: false,
    });
    renderWithProviders(<RelationDetailPanel name="Gérard Dupont" lng="fr" onBack={vi.fn()} />);
    expect(screen.queryByText('relations.identity_best_effort')).not.toBeInTheDocument();
  });

  it('deep-links a 360° preparation as a chat intent (ADR-173)', async () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const { user } = renderWithProviders(
      <RelationDetailPanel name="Gérard Dupont" lng="fr" onBack={vi.fn()} />
    );
    await user.click(screen.getByRole('button', { name: 'relations.prepare_360' }));
    expect((push.mock.calls[0][0] as string).startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('returns to the list', async () => {
    useRelationDetail.mockReturnValue({ detail: detail(), loading: false, error: false });
    const onBack = vi.fn();
    const { user } = renderWithProviders(
      <RelationDetailPanel name="Gérard Dupont" lng="fr" onBack={onBack} />
    );
    await user.click(screen.getByRole('button', { name: 'relations.back' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
