/**
 * DropdownMenu — the wrapper's own decisions (audit AC-040: it re-entered the
 * coverage measure): non-modal by default, so opening a menu never locks the
 * page's scroll (which hid the sticky header), modal on request, and the inset
 * variant that aligns an entry without an icon.
 */

import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '../dropdown-menu';

function Menu({ modal }: { modal?: boolean }) {
  return (
    <DropdownMenu modal={modal}>
      <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel inset>Section</DropdownMenuLabel>
        <DropdownMenuItem>Plain</DropdownMenuItem>
        <DropdownMenuItem inset>Aligned</DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger inset>More</DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuItem>Nested</DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** A modal dialog holding a menu, and its way out. */
function DialogWithMenu() {
  const [open, setOpen] = useState(true);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogTitle>A form</DialogTitle>
        <DialogDescription>Its fields</DialogDescription>
        <Menu />
        <button type="button" onClick={() => setOpen(false)}>
          Leave
        </button>
      </DialogContent>
    </Dialog>
  );
}

async function open(modal?: boolean): Promise<HTMLElement> {
  const { user } = renderWithProviders(<Menu modal={modal} />);
  await user.click(screen.getByRole('button', { name: 'Actions' }));
  return screen.findByRole('menu');
}

describe('DropdownMenu', () => {
  it('opens without locking the page scroll by default', async () => {
    const menu = await open();

    expect(within(menu).getByRole('menuitem', { name: 'Plain' })).toBeInTheDocument();
    expect(document.body).not.toHaveAttribute('data-scroll-locked');
  });

  it('locks the page scroll when the caller asks for a modal menu', async () => {
    await open(true);

    expect(document.body).toHaveAttribute('data-scroll-locked');
  });

  it('stays open inside a modal dialog, whose focus trap would otherwise close it', async () => {
    const { user } = renderWithProviders(<DialogWithMenu />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));

    const line = await screen.findByRole('menuitem', { name: 'Plain' });
    expect(line).toBeVisible();
    expect(screen.getByRole('button', { name: 'Actions', hidden: true })).toHaveAttribute(
      'aria-expanded',
      'true'
    );

    await user.click(line);
    await user.click(await screen.findByRole('button', { name: 'Leave' }));

    // The page answers a pointer again: neither layer took that with it.
    await waitFor(() => expect(document.body.style.pointerEvents).not.toBe('none'));
    expect(document.body).not.toHaveAttribute('data-scroll-locked');
  });

  it('keeps the caller’s word inside a dialog', async () => {
    const { user } = renderWithProviders(
      <Dialog open modal={false}>
        <DialogContent>
          <DialogTitle>A panel</DialogTitle>
          <DialogDescription>Beside the page</DialogDescription>
          <Menu />
        </DialogContent>
      </Dialog>
    );

    await user.click(screen.getByRole('button', { name: 'Actions' }));

    expect(await screen.findByRole('menuitem', { name: 'Plain' })).toBeVisible();
    expect(document.body).not.toHaveAttribute('data-scroll-locked');
  });

  it('indents an inset item, label and sub-trigger, and nothing else', async () => {
    const menu = await open();

    expect(within(menu).getByRole('menuitem', { name: 'Aligned' })).toHaveClass('pl-8');
    expect(within(menu).getByRole('menuitem', { name: 'More' })).toHaveClass('pl-8');
    expect(within(menu).getByText('Section')).toHaveClass('pl-8');
    expect(within(menu).getByRole('menuitem', { name: 'Plain' })).not.toHaveClass('pl-8');
  });
});
