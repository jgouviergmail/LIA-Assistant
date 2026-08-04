/**
 * SectionToolbar — the unified list-section header (layout program).
 *
 * Under guard: the primary CTA keeps its LABEL at every size (the old bars
 * dropped it on phones while "Delete all" kept its own), secondary actions
 * exist both inline and in the phone "⋯" menu (never amputated below lg),
 * and the destructive action is the only red one.
 */

import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { Download, Plus, Trash2 } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SectionToolbar } from '../SectionToolbar';

function renderToolbar(overrides?: {
  onCreate?: () => void;
  onExport?: () => void;
  onDeleteAll?: () => void;
}) {
  return renderWithProviders(
    <SectionToolbar
      count="12 memories"
      menuLabel="More actions"
      primary={{
        key: 'create',
        label: 'Add',
        icon: Plus,
        onSelect: overrides?.onCreate ?? vi.fn(),
      }}
      secondary={[
        {
          key: 'export',
          label: 'Export',
          icon: Download,
          onSelect: overrides?.onExport ?? vi.fn(),
        },
      ]}
      destructive={{
        key: 'delete-all',
        label: 'Delete all',
        icon: Trash2,
        onSelect: overrides?.onDeleteAll ?? vi.fn(),
      }}
    />
  );
}

describe('SectionToolbar', () => {
  it('shows the count and a labelled primary CTA with no size-gated label', () => {
    renderToolbar();
    expect(screen.getByText('12 memories')).toBeInTheDocument();
    const create = screen.getByRole('button', { name: 'Add' });
    expect(create.textContent).toContain('Add');
    expect(create.innerHTML).not.toContain('hidden sm:inline');
  });

  it('renders secondary actions inline AND in the phone menu', async () => {
    const onExport = vi.fn();
    const user = userEvent.setup();
    renderToolbar({ onExport });

    // Inline rendering (sm+)
    await user.click(screen.getByRole('button', { name: 'Export' }));
    expect(onExport).toHaveBeenCalledTimes(1);

    // Phone menu rendering
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Export' }));
    expect(onExport).toHaveBeenCalledTimes(2);
  });

  it('keeps the destructive action visible, red, and labelled', () => {
    renderToolbar();
    const del = screen.getByRole('button', { name: 'Delete all' });
    expect(del.className).toContain('destructive');
    expect(del.className).not.toContain('hidden');
  });

  it('fires the primary action', async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    renderToolbar({ onCreate });
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });
});
