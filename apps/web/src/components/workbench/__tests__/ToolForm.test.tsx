/**
 * How every form of the Tools opens and ends (owner, 2026-11-06): the head at the left at every
 * width, « Cancel » in « Delete »'s style, confirmations included, the act last in reading order.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import { buttonVariants } from '@/components/ui/button-variants';

import { CancelButton, ToolActions, ToolDialogHeader, useToolConfirm } from '../ToolForm';

const DELETE_STYLE = buttonVariants({ variant: 'destructive' });

function Question() {
  const { confirm, confirmDialog } = useToolConfirm();
  return (
    <>
      <button type="button" onClick={() => void confirm({ title: 'Delete it?' })}>
        ask
      </button>
      {confirmDialog}
    </>
  );
}

describe('CancelButton', () => {
  it('wears the style of « Delete »', () => {
    renderWithProviders(<CancelButton lng="en" />);

    const cancel = screen.getByRole('button', { name: 'common.cancel' });
    for (const token of DELETE_STYLE.split(' ')) expect(cancel.className).toContain(token);
  });

  it('never submits the form it stands in', async () => {
    const submitted = vi.fn((event: React.FormEvent) => event.preventDefault());
    const left = vi.fn();
    renderWithProviders(
      <form onSubmit={submitted}>
        <CancelButton lng="en" onClick={left} />
      </form>
    );

    await userEvent.setup().click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(left).toHaveBeenCalledTimes(1);
    expect(submitted).not.toHaveBeenCalled();
  });

  it('takes the word of what it takes back', () => {
    renderWithProviders(<CancelButton lng="en" label="Undo" />);

    expect(screen.getByRole('button', { name: 'Undo' })).toBeVisible();
  });
});

describe('ToolDialogHeader', () => {
  it('starts at the left at every width', () => {
    renderWithProviders(<ToolDialogHeader data-testid="head">Title</ToolDialogHeader>);

    const head = screen.getByTestId('head');
    expect(head).toHaveClass('text-left');
    expect(head).not.toHaveClass('text-center');
  });
});

describe('ToolActions', () => {
  it('stacks on a phone with the act first, side by side from `sm`', () => {
    renderWithProviders(<ToolActions data-testid="end">x</ToolActions>);

    expect(screen.getByTestId('end')).toHaveClass('flex-col-reverse', 'sm:flex-row');
  });
});

describe('useToolConfirm', () => {
  it('asks with a « Cancel » like every other, its head at the left', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Question />);

    await user.click(screen.getByRole('button', { name: 'ask' }));

    const cancel = await screen.findByRole('button', { name: 'common.cancel' });
    for (const token of DELETE_STYLE.split(' ')) expect(cancel.className).toContain(token);
    expect(screen.getByText('Delete it?').parentElement).toHaveClass('text-left');
  });
});
