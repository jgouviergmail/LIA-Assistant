/**
 * CardItemRow / CardItemActions — one row of a briefing card.
 *
 * Two defects of the previous shape, both reported from use:
 *
 * 1. **Several action chips truncated the item.** Each chip is 26 px wide, so
 *    two or three of them (plus the Drive link on documents) took 82 to 110 px
 *    of a row whose usable width is ~330-365 px in the 2- and 3-column grids —
 *    a quarter to a third, and the title `truncate`d. ONE trigger now takes a
 *    fixed 26 px whatever the number of actions, so every row of every card
 *    reserves the same width and the text column is identical throughout.
 *
 * 2. **The full label was unreachable.** The row's accessible name is the
 *    INTENT sentence ("prepare me for X"), never the raw title, so a
 *    screen-reader user never heard it and a sighted one only saw the
 *    truncation. Hovering — or focusing — now shows it in a bubble, which is
 *    also an `aria-describedby` on the row.
 */

import { describe, it, expect, vi } from 'vitest';
import { Check, ExternalLink, Pencil } from 'lucide-react';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { CardItemRow } from '../CardItemRow';
import type { CardItemAction } from '../CardItemActions';
import { runCardAction as runAction } from './card-actions-harness';

const ACTIONS_LABEL = 'dashboard.briefing.actions.more';
const FULL_LABEL = 'Comité de pilotage trimestriel avec la direction financière';

function row(over: Partial<React.ComponentProps<typeof CardItemRow>> = {}) {
  return renderWithProviders(
    <ul>
      <CardItemRow
        ariaLabel="Prépare-moi la réunion de 10h"
        tooltip="Comité de pilotage trimestriel avec la direction financière"
        onSelect={vi.fn()}
        actions={[]}
        {...over}
      >
        <span>Comité de pilotage…</span>
      </CardItemRow>
    </ul>
  );
}

function actionsFixture(over: Partial<CardItemAction>[] = []): CardItemAction[] {
  const base: CardItemAction[] = [
    { icon: Check, label: 'Marquer comme fait', onSelect: vi.fn() },
    { icon: Pencil, label: 'Modifier', onSelect: vi.fn() },
  ];
  return over.length ? base.map((a, i) => ({ ...a, ...over[i] })) : base;
}

describe('CardItemRow', () => {
  it('names the row after what the click does, not after the item', () => {
    row();

    expect(
      screen.getByRole('button', { name: 'Prépare-moi la réunion de 10h' })
    ).toBeInTheDocument();
  });

  it('shows the item label in a bubble on hover', async () => {
    const { user } = row();

    // The "before" assertion is what makes this test non-vacuous: were the
    // label always in the DOM, the one below would pass with no tooltip at all.
    expect(screen.queryByText(FULL_LABEL)).toBeNull();

    await user.hover(screen.getByRole('button', { name: 'Prépare-moi la réunion de 10h' }));

    await waitFor(() => expect(screen.getAllByText(FULL_LABEL).length).toBeGreaterThan(0));
  });

  it('shows it on keyboard focus too — hover is not an input method for everyone', async () => {
    const { user } = row();
    expect(screen.queryByText(FULL_LABEL)).toBeNull();

    await user.tab();

    await waitFor(() => expect(screen.getAllByText(FULL_LABEL).length).toBeGreaterThan(0));
  });

  it('describes the row with the bubble, so the label is announced too', async () => {
    // The row's own name is the intent sentence; without this wiring the
    // item's words would still reach nobody using a screen reader.
    const { user } = row();
    const button = screen.getByRole('button', { name: 'Prépare-moi la réunion de 10h' });

    await user.hover(button);

    await waitFor(() => expect(button).toHaveAttribute('aria-describedby'));
    expect(button).toHaveAccessibleDescription(FULL_LABEL);
  });

  it('renders no actions trigger when the row has no action', () => {
    row();

    expect(screen.queryByRole('button', { name: ACTIONS_LABEL })).toBeNull();
  });

  it('renders ONE trigger, whatever the number of actions', () => {
    row({ actions: actionsFixture() });

    expect(screen.getAllByRole('button', { name: ACTIONS_LABEL })).toHaveLength(1);
    // The actions themselves are not chips any more: nothing is rendered for
    // them until the menu opens, which is what frees the row's width.
    expect(screen.queryByRole('button', { name: 'Modifier' })).toBeNull();
  });

  it('keeps a single trigger even for exactly one action', () => {
    // Deliberate (owner arbitration 2026-08-03): a uniform reserved width is
    // what makes the text column identical on every row of every card. A chip
    // here and a menu there would bring back the variable width this closes.
    row({ actions: [{ icon: Check, label: 'Annuler le rappel', onSelect: vi.fn() }] });

    expect(screen.getByRole('button', { name: ACTIONS_LABEL })).toBeInTheDocument();
  });

  it('lists every action in the menu and runs the chosen one', async () => {
    const done = vi.fn();
    const { user } = row({ actions: actionsFixture([{ onSelect: done }]) });

    await user.click(screen.getByRole('button', { name: ACTIONS_LABEL }));

    expect(screen.getByRole('menuitem', { name: 'Modifier' })).toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Marquer comme fait' }));

    expect(done).toHaveBeenCalledTimes(1);
  });

  it('opening the menu never triggers the row itself', async () => {
    const select = vi.fn();
    const { user } = row({ onSelect: select, actions: actionsFixture() });

    await user.click(screen.getByRole('button', { name: ACTIONS_LABEL }));

    expect(select).not.toHaveBeenCalled();
  });

  it('renders an external action as a real link, not a click handler', async () => {
    // A document's "open in Drive" is navigation: an anchor gives the browser
    // its middle-click, its context menu and its status-bar preview, none of
    // which a button can offer.
    const { user } = row({
      actions: [
        {
          icon: ExternalLink,
          label: 'Ouvrir dans Drive',
          href: 'https://drive.example/doc',
        },
      ],
    });

    await user.click(screen.getByRole('button', { name: ACTIONS_LABEL }));

    const link = screen.getByRole('menuitem', { name: 'Ouvrir dans Drive' });
    expect(link).toHaveAttribute('href', 'https://drive.example/doc');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('states a busy action without removing it from the keyboard', async () => {
    // `aria-disabled`, never `disabled`: the attribute on a FOCUSED control
    // blurs it and drops it from the tab order. The handler guard is what
    // prevents the double submit.
    const busy = vi.fn();
    const { user } = row({
      actions: [{ icon: Check, label: 'Marquer comme fait', onSelect: busy, busy: true }],
    });

    await user.click(screen.getByRole('button', { name: ACTIONS_LABEL }));
    const item = screen.getByRole('menuitem', { name: 'Marquer comme fait' });

    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).not.toHaveAttribute('disabled');
    await user.click(item);
    expect(busy).not.toHaveBeenCalled();
  });

  it('leaves focus where a chosen action put it', async () => {
    // Radix restores focus to its trigger when the menu closes. That trigger
    // lives INSIDE the row, and several actions REMOVE the row (closing a
    // commitment, cancelling a reminder) — the restore then lands on a
    // detached node and the keyboard user is dropped on <body>. It also fights
    // the card's own anchor, which deliberately takes focus while the row
    // still exists.
    //
    // So: an action that ran owns the focus. Every one of them moves it
    // (the card's named region, an autofocused editor, an alert dialog, or a
    // navigation away); a dismissal without a choice keeps Radix's restore,
    // which is exactly right there — see the test below.
    const elsewhere = document.createElement('button');
    elsewhere.textContent = 'ailleurs';
    document.body.appendChild(elsewhere);

    const { user } = row({
      actions: [
        {
          icon: Check,
          label: 'Marquer comme fait',
          // ASYNCHRONOUS on purpose — this is what the real cards do: they
          // await the write, then take focus. A synchronous move would land
          // before Radix's restore and the test would pass on the ordering
          // rather than on the rule.
          onSelect: () => {
            void Promise.resolve().then(() => elsewhere.focus());
          },
        },
      ],
    });

    await runAction(user, 'Marquer comme fait');

    // Wait for the menu to be GONE first: Radix restores focus as part of its
    // close, so asserting earlier would pass on a race rather than on the rule.
    await waitFor(() =>
      expect(screen.queryByRole('menuitem', { name: 'Marquer comme fait' })).toBeNull()
    );
    expect(elsewhere).toHaveFocus();
    elsewhere.remove();
  });

  it('returns focus to the trigger when the menu closes', async () => {
    // The row can disappear under the reader (cancelling a reminder); focus
    // must at least come back to where it left, never to <body>.
    const { user } = row({ actions: actionsFixture() });
    const trigger = screen.getByRole('button', { name: ACTIONS_LABEL });

    await user.click(trigger);
    await user.keyboard('{Escape}');

    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
