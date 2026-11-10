/** Background space reads must not replace an open form's draft. */
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RAGSpace } from '@/types/rag-spaces';
import { EditSpaceDialog } from '../EditSpaceDialog';

function space(overrides: Partial<RAGSpace> = {}): RAGSpace {
  return {
    id: 'space-1',
    name: 'Projects',
    description: 'Original description',
    is_active: true,
    kind: null,
    is_favorite: false,
    document_count: 2,
    ready_document_count: 2,
    total_size: 2048,
    created_at: '2026-11-09T10:00:00Z',
    updated_at: '2026-11-09T10:00:00Z',
    ...overrides,
  };
}

function props(): ComponentProps<typeof EditSpaceDialog> {
  return {
    open: true,
    space: space(),
    onOpenChange: vi.fn(),
    onSubmit: vi.fn().mockResolvedValue(undefined),
  };
}

describe('EditSpaceDialog', () => {
  it('preserves draft text and focus when a background read returns a new space object', async () => {
    const initial = props();
    const { user, rerender } = renderWithProviders(<EditSpaceDialog {...initial} />);
    const name = screen.getByRole('textbox', { name: 'spaces.name_label' });
    const description = screen.getByRole('textbox', { name: /spaces.description_label/ });
    await user.clear(name);
    await user.type(name, 'My draft');
    await user.clear(description);
    await user.type(description, 'Still editing');

    rerender(<EditSpaceDialog {...initial} space={space({ document_count: 3 })} />);

    expect(name).toHaveValue('My draft');
    expect(description).toHaveValue('Still editing');
    expect(description).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(initial.onSubmit).toHaveBeenCalledWith('My draft', 'Still editing');
  });

  it('submits only the fields edited since opening, preserving a concurrent description change', async () => {
    const initial = props();
    const { user, rerender } = renderWithProviders(<EditSpaceDialog {...initial} />);
    const name = screen.getByRole('textbox', { name: 'spaces.name_label' });
    await user.clear(name);
    await user.type(name, 'My draft');

    rerender(<EditSpaceDialog {...initial} space={space({ description: 'Updated elsewhere' })} />);
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    expect(initial.onSubmit).toHaveBeenCalledWith('My draft', undefined);
  });

  it('opens a fresh draft from the latest values after closing or switching spaces', async () => {
    const initial = props();
    const { user, rerender } = renderWithProviders(<EditSpaceDialog {...initial} />);
    await user.type(screen.getByRole('textbox', { name: 'spaces.name_label' }), ' unsaved');
    rerender(<EditSpaceDialog {...initial} open={false} />);
    rerender(<EditSpaceDialog {...initial} space={space({ name: 'Latest name' })} />);
    expect(screen.getByRole('textbox', { name: 'spaces.name_label' })).toHaveValue('Latest name');

    rerender(
      <EditSpaceDialog {...initial} space={space({ id: 'space-2', name: 'Another space' })} />
    );
    expect(screen.getByRole('textbox', { name: 'spaces.name_label' })).toHaveValue('Another space');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(initial.onSubmit).not.toHaveBeenCalled();
    expect(initial.onOpenChange).toHaveBeenCalledWith(false);
  });
});
