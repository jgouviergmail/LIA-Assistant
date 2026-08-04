/**
 * Reaching a briefing card's per-item actions, from a test.
 *
 * The actions used to be visible icon chips, so a test named one directly.
 * They now sit behind ONE trigger per row (they truncated the item's words —
 * see `CardItemActions`), so reaching them takes a click first. That click is
 * the ONLY thing that changed: every assertion about what an action does is
 * unchanged, and must stay so.
 *
 * Shared rather than copied into each card's suite: five suites need it, and
 * the fifth copy is where a divergence would hide.
 */

import type { UserEvent } from '@testing-library/user-event';

import { screen } from '@/__tests__/test-utils';

/** Accessible name of every row's actions trigger. */
export const CARD_ACTIONS_TRIGGER = 'dashboard.briefing.actions.more';

/**
 * Open the actions menu of one row.
 *
 * @param user - The suite's user-event instance.
 * @param index - Which row, in DOM order. Defaults to the first.
 */
export async function openCardActions(user: UserEvent, index = 0): Promise<void> {
  const triggers = screen.getAllByRole('button', { name: CARD_ACTIONS_TRIGGER });
  await user.click(triggers[index]);
}

/**
 * Open a row's menu and activate the action whose name matches.
 *
 * @param user - The suite's user-event instance.
 * @param name - Accessible name of the menu item.
 * @param index - Which row, in DOM order. Defaults to the first.
 */
export async function runCardAction(
  user: UserEvent,
  name: string | RegExp,
  index = 0
): Promise<void> {
  await openCardActions(user, index);
  await user.click(screen.getByRole('menuitem', { name }));
}
