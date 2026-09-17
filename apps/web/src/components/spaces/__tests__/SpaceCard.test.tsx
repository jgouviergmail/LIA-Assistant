/**
 * A space card: a space the person created can be edited and deleted; a
 * space another domain manages by role (meetings, kept answers) keeps its
 * toggle and its rename, says it is managed, and offers no delete — the
 * server refuses it anyway (2026-09-16 design, amending ADR-258).
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import en from '@/../locales/en/translation.json';
import fr from '@/../locales/fr/translation.json';
import type { RAGSpace } from '@/types/rag-spaces';

import { SpaceCard } from '../SpaceCard';

function space(over: Partial<RAGSpace> = {}): RAGSpace {
  return {
    id: 's1',
    name: 'Projets',
    description: null,
    is_active: true,
    kind: null,
    document_count: 2,
    ready_document_count: 2,
    total_size: 4096,
    created_at: '2026-09-02T10:00:00Z',
    updated_at: '2026-09-02T10:00:00Z',
    ...over,
  };
}

function render(over: Partial<RAGSpace> = {}) {
  const handlers = { onClick: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn(), onToggle: vi.fn() };
  const utils = renderWithProviders(<SpaceCard space={space(over)} {...handlers} />);
  return { ...utils, ...handlers };
}

describe('SpaceCard', () => {
  it('lets a space the person created be edited and deleted', async () => {
    const { user, onDelete } = render();
    await user.click(screen.getByTitle('common.delete'));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(screen.getByTitle('common.edit')).toBeInTheDocument();
    expect(screen.queryByText('spaces.managed.hint')).not.toBeInTheDocument();
  });

  it('offers no delete on a space a domain manages, and says so', () => {
    render({ kind: 'bookmarks', name: 'Réponses conservées' });
    expect(screen.queryByTitle('common.delete')).not.toBeInTheDocument();
    expect(screen.getByTitle('common.edit')).toBeInTheDocument();
    expect(screen.getByText('spaces.managed.hint')).toBeInTheDocument();
  });

  it('names the managed hint in English and in French', () => {
    expect(en.spaces.managed.hint).toBe('Managed by LIA');
    expect(fr.spaces.managed.hint).toBe('Géré par LIA');
  });
});
