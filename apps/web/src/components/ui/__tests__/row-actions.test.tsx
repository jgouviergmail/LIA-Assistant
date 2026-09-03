/**
 * RowActions — the unified row-action pattern (layout program, 2026-08-05).
 *
 * The contract under guard: every action is reachable WITHOUT a hover (the
 * pattern this component replaced tabbed keyboard users onto invisible
 * `opacity-0` buttons), the destructive action carries its red at rest, and
 * the phone path is a menu whose trigger names the row.
 */

import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Pencil, Trash2 } from 'lucide-react';
import { RowActions } from '../row-actions';

function makeActions(overrides?: { onEdit?: () => void; onDelete?: () => void }) {
  return [
    {
      key: 'edit',
      label: 'Edit Standup',
      icon: Pencil,
      onSelect: overrides?.onEdit ?? vi.fn(),
    },
    {
      key: 'delete',
      label: 'Delete Standup',
      icon: Trash2,
      tone: 'destructive' as const,
      onSelect: overrides?.onDelete ?? vi.fn(),
    },
  ];
}

describe('RowActions', () => {
  it('renders one always-visible icon button per action, never hover-gated', () => {
    renderWithProviders(<RowActions actions={makeActions()} menuLabel="Actions — Standup" />);
    const edit = screen.getByRole('button', { name: 'Edit Standup' });
    const del = screen.getByRole('button', { name: 'Delete Standup' });
    expect(edit.className).not.toContain('opacity-0');
    expect(del.className).not.toContain('opacity-0');
  });

  it('carries the destructive red at rest, not on hover only', () => {
    renderWithProviders(<RowActions actions={makeActions()} menuLabel="Actions — Standup" />);
    expect(screen.getByRole('button', { name: 'Delete Standup' }).className).toContain(
      'text-destructive'
    );
    expect(screen.getByRole('button', { name: 'Edit Standup' }).className).not.toContain(
      'text-destructive'
    );
  });

  it('fires onSelect from the icon button', async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<RowActions actions={makeActions({ onEdit })} menuLabel="A" />);
    await user.click(screen.getByRole('button', { name: 'Edit Standup' }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it('exposes the phone path as a named menu listing every action', async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <RowActions actions={makeActions({ onDelete })} menuLabel="Actions — Standup" />
    );

    await user.click(screen.getByRole('button', { name: 'Actions — Standup' }));
    const deleteItem = await screen.findByRole('menuitem', { name: 'Delete Standup' });
    expect(screen.getByRole('menuitem', { name: 'Edit Standup' })).toBeInTheDocument();
    expect(deleteItem.className).toContain('text-destructive');

    await user.click(deleteItem);
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('disables both renderings of a disabled or loading action', () => {
    const actions = [
      { key: 'edit', label: 'Edit', icon: Pencil, onSelect: vi.fn(), disabled: true },
      { key: 'delete', label: 'Delete', icon: Trash2, onSelect: vi.fn(), loading: true },
    ];
    renderWithProviders(<RowActions actions={actions} menuLabel="A" />);
    expect(screen.getByRole('button', { name: 'Edit' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();
  });
});

describe('RowActions — link actions (ADR-259)', () => {
  it('renders an href action as a real link on both paths, named like the others', async () => {
    renderWithProviders(
      <RowActions
        actions={[
          {
            key: 'download',
            label: 'Download Standup',
            icon: Pencil,
            href: 'https://api.test/documents/d1/download',
            onSelect: vi.fn(),
          },
        ]}
        menuLabel="Actions — Standup"
      />
    );
    const link = screen.getByRole('link', { name: 'Download Standup' });
    expect(link).toHaveAttribute('href', 'https://api.test/documents/d1/download');
    expect(link).toHaveAttribute('download');

    await userEvent.click(screen.getByRole('button', { name: 'Actions — Standup' }));
    const item = await screen.findByRole('menuitem', { name: 'Download Standup' });
    expect(item.tagName).toBe('A');
    expect(item).toHaveAttribute('href', 'https://api.test/documents/d1/download');
  });
});

describe('RowActions — blocked actions', () => {
  it('states a blocked action with aria-disabled, keeps it focusable and still fires it', async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <RowActions
        actions={[{ key: 'add', label: 'Add Standup', icon: Pencil, onSelect, blocked: true }]}
        menuLabel="Actions — Standup"
      />
    );
    const button = screen.getByRole('button', { name: 'Add Standup' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).not.toBeDisabled();
    button.focus();
    expect(button).toHaveFocus();
    await userEvent.click(button);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
