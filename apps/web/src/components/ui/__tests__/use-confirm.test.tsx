/**
 * Promise-based confirmation (W4b).
 *
 * This replaces `window.confirm` on nine irreversible admin actions, so the
 * contract has to be airtight in the direction that matters: NOTHING may
 * resolve `true` except an explicit press on the confirming button. Escape,
 * outside-click and cancel are all refusals, and no call site may be left
 * waiting on a promise that never settles.
 */

import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

import { useConfirm } from '../use-confirm';

/**
 * The global i18n stub echoes keys, so the SHARED labels render as their key.
 * Named here rather than inlined, to keep the intent readable.
 */
const CANCEL = 'common.cancel';

/** A harness exposing the resolved value of the last ask. */
function Harness({ onResult }: { onResult: (value: boolean) => void }) {
  const { confirm, confirmDialog } = useConfirm();
  const [asked, setAsked] = useState(0);
  return (
    <div>
      <button
        type="button"
        onClick={async () => {
          setAsked(n => n + 1);
          onResult(
            await confirm({
              title: 'Supprimer le compte ?',
              description: 'Cette action est irréversible.',
              confirmLabel: 'Supprimer',
            })
          );
        }}
      >
        Ouvrir
      </button>
      <span data-testid="asked">{asked}</span>
      {confirmDialog}
    </div>
  );
}

/** Fires two questions back to back, without awaiting the first. */
function DoubleAskHarness({ onResult }: { onResult: (value: boolean) => void }) {
  const { confirm, confirmDialog } = useConfirm();
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          void confirm({ title: 'Première', confirmLabel: 'Premiere' }).then(onResult);
          void confirm({ title: 'Seconde', confirmLabel: 'Seconde' }).then(onResult);
        }}
      >
        Doubler
      </button>
      {confirmDialog}
    </div>
  );
}

describe('useConfirm', () => {
  it('renders nothing until it is asked', () => {
    renderHarness();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('states the question and its consequence', async () => {
    const { user } = renderHarness();
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText('Supprimer le compte ?')).toBeInTheDocument();
    expect(screen.getByText('Cette action est irréversible.')).toBeInTheDocument();
  });

  it('resolves true only on an explicit confirmation', async () => {
    const onResult = vi.fn();
    const { user } = renderHarness(onResult);
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await user.click(await screen.findByRole('button', { name: 'Supprimer' }));

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true));
  });

  it('resolves false on cancel', async () => {
    const onResult = vi.fn();
    const { user } = renderHarness(onResult);
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await user.click(await screen.findByRole('button', { name: CANCEL }));

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false));
  });

  it('treats Escape as a refusal', async () => {
    // Dismissal must never be read as consent on a destructive action.
    const onResult = vi.fn();
    const { user } = renderHarness(onResult);
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await screen.findByRole('alertdialog');
    await user.keyboard('{Escape}');

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false));
  });

  it('closes after answering', async () => {
    const { user } = renderHarness();
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await user.click(await screen.findByRole('button', { name: CANCEL }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('can be asked again after an answer', async () => {
    const onResult = vi.fn();
    const { user } = renderHarness(onResult);

    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await user.click(await screen.findByRole('button', { name: CANCEL }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    await user.click(await screen.findByRole('button', { name: 'Supprimer' }));

    await waitFor(() => expect(onResult).toHaveBeenNthCalledWith(2, true));
  });

  it('never leaves a caller waiting when a second question replaces the first', async () => {
    // Two asks in a row must both settle; an orphaned promise would freeze the
    // first call site forever. The dialog is modal, so this case is reachable
    // only programmatically — which is exactly how a stray call site would hit
    // it.
    const results: boolean[] = [];
    const { user } = renderWithProviders(<DoubleAskHarness onResult={v => results.push(v)} />);

    await user.click(screen.getByRole('button', { name: 'Doubler' }));

    // The superseded question resolved as a refusal, without any interaction.
    await waitFor(() => expect(results).toEqual([false]));

    // The surviving one still answers normally.
    await user.click(await screen.findByRole('button', { name: 'Seconde' }));
    await waitFor(() => expect(results).toEqual([false, true]));
  });

  it('is announced as an alert dialog', async () => {
    // Destructive confirmations must interrupt a screen reader, not sit in the
    // background like an ordinary dialog.
    const { user } = renderHarness();
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
  });

  it('describes itself from the description when there is one', async () => {
    const { user } = renderHarness();
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));

    const dialog = await screen.findByRole('alertdialog');
    const describedBy = dialog.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      'Cette action est irréversible.'
    );
  });

  it('points at nothing rather than at a missing element when there is none', async () => {
    // `alertdialog` requires its description. Two callers ask a one-line
    // question with no consequence to spell out (an admin pricing edit), and
    // the dialog primitive wires `aria-describedby` to a Description element by
    // default — which would then reference an id that is not in the document.
    const { user } = renderWithProviders(<TitleOnlyHarness />);
    await user.click(screen.getByRole('button', { name: 'Ouvrir' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).not.toHaveAttribute('aria-describedby');
  });
});

/** A confirmation carrying a title and nothing else. */
function TitleOnlyHarness() {
  const { confirm, confirmDialog } = useConfirm();
  return (
    <div>
      <button type="button" onClick={() => void confirm({ title: 'Modifier ce tarif ?' })}>
        Ouvrir
      </button>
      {confirmDialog}
    </div>
  );
}

function renderHarness(onResult: (value: boolean) => void = () => {}) {
  return renderWithProviders(<Harness onResult={onResult} />);
}
