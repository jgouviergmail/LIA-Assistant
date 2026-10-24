/**
 * DropdownMenu — the wrapper's own decisions (audit AC-040: it re-entered the
 * coverage measure): non-modal by default, so opening a menu never locks the
 * page's scroll (which hid the sticky header), modal on request, and the inset
 * variant that aligns an entry without an icon.
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
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

  it('indents an inset item, label and sub-trigger, and nothing else', async () => {
    const menu = await open();

    expect(within(menu).getByRole('menuitem', { name: 'Aligned' })).toHaveClass('pl-8');
    expect(within(menu).getByRole('menuitem', { name: 'More' })).toHaveClass('pl-8');
    expect(within(menu).getByText('Section')).toHaveClass('pl-8');
    expect(within(menu).getByRole('menuitem', { name: 'Plain' })).not.toHaveClass('pl-8');
  });
});
