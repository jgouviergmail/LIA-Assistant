import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogClose } from '../dialog';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
} from '../alert-dialog';

function Harness({
  alert = false,
  redirect = false,
  modal = true,
  complete = false,
}: {
  alert?: boolean;
  redirect?: boolean;
  modal?: boolean;
  complete?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const Root = alert ? AlertDialog : Dialog;
  const Content = alert ? AlertDialogContent : DialogContent;
  const Title = alert ? AlertDialogTitle : DialogTitle;
  const Description = alert ? AlertDialogDescription : DialogDescription;
  const Close = alert ? AlertDialogCancel : DialogClose;
  return (
    <>
      <button onClick={() => setOpen(true)}>Open manually</button>
      <button id="next-step">Next step</button>
      <Root open={open} onOpenChange={setOpen} modal={modal}>
        <Content
          onCloseAutoFocus={
            redirect
              ? event => {
                  event.preventDefault();
                  document.getElementById('next-step')?.focus();
                }
              : undefined
          }
        >
          <Title>Confirmation</Title>
          <Description>Details</Description>
          <Close>Cancel</Close>
          {complete && (
            <Close
              onClick={async () => {
                await Promise.resolve();
                document.getElementById('next-step')?.focus();
              }}
            >
              Complete
            </Close>
          )}
        </Content>
      </Root>
    </>
  );
}

describe.each([false, true])('manual modal opener, alert=%s', alert => {
  it('returns keyboard focus to the opener when no Radix Trigger owns it', async () => {
    const { user } = renderWithProviders(<Harness alert={alert} />);
    const opener = screen.getByRole('button', { name: 'Open manually' });
    opener.focus();
    await user.keyboard('{Enter}');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it('preserves the caller’s explicit focus destination', async () => {
    const { user } = renderWithProviders(<Harness alert={alert} redirect />);
    screen.getByRole('button', { name: 'Open manually' }).focus();
    await user.keyboard('{Enter}');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Next step' })).toHaveFocus());
  });

  it('preserves a completed action’s focus destination outside the closing modal', async () => {
    const { user } = renderWithProviders(<Harness alert={alert} complete />);
    await user.click(screen.getByRole('button', { name: 'Open manually' }));
    await user.click(screen.getByRole('button', { name: 'Complete' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Next step' })).toHaveFocus());
  });
});

it('leaves non-modal outside-click focus on the chosen outside control', async () => {
  const { user } = renderWithProviders(<Harness modal={false} />);
  await user.click(screen.getByRole('button', { name: 'Open manually' }));
  const outside = screen.getByRole('button', { name: 'Next step' });
  await user.click(outside);
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(outside).toHaveFocus();
});
