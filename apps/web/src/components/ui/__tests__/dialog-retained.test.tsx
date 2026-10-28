import { Activity, useEffect, useState } from 'react';
import { act, fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { expect, it, vi } from 'vitest';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';

it('retains a suspended private workspace, releases modal locks and restores focus', async () => {
  const start = vi.fn(),
    stop = vi.fn();
  function Reader() {
    useEffect(() => {
      start();
      return () => {
        stop();
      };
    }, []);
    return <input aria-label="Retained draft" defaultValue="" />;
  }
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open workspace</button>
        <Activity mode={open ? 'visible' : 'hidden'}>
          <Dialog open onOpenChange={setOpen}>
            <DialogContent>
              <DialogTitle>Private workspace</DialogTitle>
              <DialogDescription>Retained owner content</DialogDescription>
              <Reader />
            </DialogContent>
          </Dialog>
        </Activity>
      </>
    );
  }
  renderWithProviders(<Harness />);
  const open = screen.getByRole('button', { name: 'Open workspace' });
  open.focus();
  fireEvent.click(open);
  const draft = await screen.findByRole('textbox', { name: 'Retained draft' });
  fireEvent.change(draft, { target: { value: 'Owner draft' } });
  expect(start).toHaveBeenCalledOnce();
  fireEvent.keyDown(draft, { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(stop).toHaveBeenCalledOnce();
  expect(document.body.style.pointerEvents).not.toBe('none');
  await waitFor(() => expect(open).toHaveFocus());
  await act(async () => {});
  fireEvent.click(open);
  expect(await screen.findByRole('textbox', { name: 'Retained draft' })).toHaveValue('Owner draft');
  expect(start).toHaveBeenCalledTimes(2);
});
