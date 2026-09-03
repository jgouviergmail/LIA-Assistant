/**
 * Moving documents to another space (ADR-259): the other spaces with their
 * counts, a submit refused until one is chosen, and an honest empty state
 * when there is nowhere to move to.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RAGSpace } from '@/types/rag-spaces';

import { MoveDocumentsDialog } from '../MoveDocumentsDialog';

function space(over: Partial<RAGSpace> = {}): RAGSpace {
  return {
    id: 's2',
    name: 'Archives',
    description: null,
    is_active: true,
    document_count: 4,
    ready_document_count: 4,
    total_size: 100,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  };
}

function render(over: Partial<React.ComponentProps<typeof MoveDocumentsDialog>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  const utils = renderWithProviders(
    <MoveDocumentsDialog
      open
      onOpenChange={onOpenChange}
      spaces={[space(), space({ id: 's3', name: 'Perso', document_count: 0 })]}
      count={2}
      isMoving={false}
      onSubmit={onSubmit}
      {...over}
    />
  );
  return { ...utils, onSubmit, onOpenChange };
}

describe('MoveDocumentsDialog', () => {
  it('refuses to submit until a target is chosen, then submits the chosen space', async () => {
    const { user, onSubmit } = render();
    expect(
      screen.getByRole('dialog', { name: 'spaces.documents.move_dialog.title' })
    ).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'spaces.documents.move_dialog.submit' });
    expect(submit).toHaveAttribute('aria-disabled', 'true');
    await user.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole('combobox', { name: 'spaces.documents.move_dialog.target_label' })
    );
    await user.click(await screen.findByRole('option', { name: /Archives/ }));
    expect(submit).toHaveAttribute('aria-disabled', 'false');
    await user.click(submit);
    expect(onSubmit).toHaveBeenCalledWith('s2');
  });

  it('says so when there is no other space to move to', () => {
    render({ spaces: [] });
    expect(screen.getByText('spaces.documents.move_dialog.none_available')).toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'spaces.documents.move_dialog.target_label' })
    ).not.toBeInTheDocument();
  });

  it('does not submit twice while moving', async () => {
    const { user, onSubmit } = render({ isMoving: true });
    await user.click(
      screen.getByRole('button', { name: /spaces\.documents\.move_dialog\.submit/ })
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
