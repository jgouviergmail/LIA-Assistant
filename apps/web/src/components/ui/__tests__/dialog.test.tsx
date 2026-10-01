/**
 * DialogContent — Escape belongs to an open suggestion list first.
 *
 * Radix listens for Escape in the CAPTURE phase, before the focused field: a
 * combobox whose list is open inside a dialog would lose its Escape to the
 * dialog, and the person their whole form. The primitive gives it back; a
 * caller's own `onEscapeKeyDown` still runs.
 */

import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';

function Harness({
  expanded,
  onEscapeKeyDown,
}: {
  expanded: boolean;
  onEscapeKeyDown?: (event: KeyboardEvent) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent onEscapeKeyDown={onEscapeKeyDown}>
        <DialogTitle>Title</DialogTitle>
        <DialogDescription>Description</DialogDescription>
        <input
          aria-label="field"
          role="combobox"
          aria-expanded={expanded}
          aria-controls="suggestions"
        />
        <ul id="suggestions" role="listbox" aria-label="suggestions" />
      </DialogContent>
    </Dialog>
  );
}

describe('DialogContent — Escape', () => {
  it('leaves the dialog open when it closes an expanded combobox', async () => {
    const { user } = renderWithProviders(<Harness expanded />);
    screen.getByRole('combobox', { name: 'field' }).focus();

    await user.keyboard('{Escape}');

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes the dialog from a collapsed combobox, and still calls the caller', async () => {
    const onEscapeKeyDown = vi.fn();
    const { user } = renderWithProviders(
      <Harness expanded={false} onEscapeKeyDown={onEscapeKeyDown} />
    );
    screen.getByRole('combobox', { name: 'field' }).focus();

    await user.keyboard('{Escape}');

    expect(onEscapeKeyDown).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
