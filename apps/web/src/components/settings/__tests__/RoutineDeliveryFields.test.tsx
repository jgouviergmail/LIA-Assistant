/**
 * How a routine reaches its owner: it asks before running, or it runs and only
 * notifies of something new — never both.
 *
 * What is proven here is what a keyboard and a screen reader meet: each option
 * is described by its hint, and the option the other one rules out stays where
 * the person can reach it and hear why — it refuses by its handler, not by
 * leaving the tab order.
 */
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { RoutineDeliveryFields } from '../RoutineDeliveryFields';

interface Delivery {
  requires_approval: boolean;
  notify_only_when_new: boolean;
}

const STUDIO = 'scheduled_actions.studio';

function Fields({
  initial,
  changed,
  approvalUnavailable = false,
}: {
  initial: Delivery;
  changed: (next: Delivery) => void;
  approvalUnavailable?: boolean;
}) {
  const [delivery, setDelivery] = useState(initial);
  return (
    <RoutineDeliveryFields
      idPrefix="routine"
      approvalUnavailable={approvalUnavailable}
      requiresApproval={delivery.requires_approval}
      notifyOnlyWhenNew={delivery.notify_only_when_new}
      onChange={next => {
        changed(next);
        setDelivery(next);
      }}
    />
  );
}

function rendered(initial: Delivery, approvalUnavailable = false) {
  const changed = vi.fn<(next: Delivery) => void>();
  const view = renderWithProviders(
    <Fields initial={initial} changed={changed} approvalUnavailable={approvalUnavailable} />
  );
  return { ...view, changed };
}

const asksFirst = () => screen.getByRole('switch', { name: `${STUDIO}.requires_approval` });
const onlyWhenNew = () => screen.getByRole('switch', { name: `${STUDIO}.notify_only_when_new` });

describe('RoutineDeliveryFields', () => {
  it('describes each option by its hint, for a screen reader as for the eye', () => {
    rendered({ requires_approval: false, notify_only_when_new: false });

    expect(asksFirst()).toHaveAccessibleDescription(`${STUDIO}.requires_approval_hint`);
    expect(onlyWhenNew()).toHaveAccessibleDescription(`${STUDIO}.notify_only_when_new_hint`);
  });

  it('lets the person choose to hear only of something new', async () => {
    const { user, changed } = rendered({ requires_approval: false, notify_only_when_new: false });

    await user.click(onlyWhenNew());

    expect(changed).toHaveBeenCalledWith({ requires_approval: false, notify_only_when_new: true });
    expect(onlyWhenNew()).toBeChecked();
  });

  it('withdraws « only when new » when the routine is told to ask first', async () => {
    const { user, changed } = rendered({ requires_approval: false, notify_only_when_new: true });

    await user.click(asksFirst());

    expect(changed).toHaveBeenCalledWith({ requires_approval: true, notify_only_when_new: false });
    expect(onlyWhenNew()).not.toBeChecked();
  });

  it('keeps the ruled-out option reachable, and says why it is unavailable', () => {
    rendered({ requires_approval: true, notify_only_when_new: false });

    // Reachable: a control removed from the tab order can tell a keyboard
    // user neither that it exists nor why it cannot be set.
    expect(onlyWhenNew()).toBeEnabled();
    expect(onlyWhenNew()).toHaveAttribute('aria-disabled', 'true');
    expect(onlyWhenNew()).toHaveAccessibleDescription(`${STUDIO}.notify_only_when_new_unavailable`);
  });

  it('refuses the ruled-out option by its handler, by pointer and by keyboard', async () => {
    const { user, changed } = rendered({ requires_approval: true, notify_only_when_new: false });

    await user.click(onlyWhenNew());
    onlyWhenNew().focus();
    await user.keyboard(' ');
    await user.keyboard('{Enter}');

    expect(changed).not.toHaveBeenCalled();
    expect(onlyWhenNew()).not.toBeChecked();
    expect(onlyWhenNew()).toHaveFocus();
  });

  it('says nothing is unavailable once the routine no longer asks first', async () => {
    const { user } = rendered({ requires_approval: true, notify_only_when_new: false });

    await user.click(asksFirst());

    expect(onlyWhenNew()).not.toHaveAttribute('aria-disabled');
    expect(onlyWhenNew()).toHaveAccessibleDescription(`${STUDIO}.notify_only_when_new_hint`);
  });
});

describe('RoutineDeliveryFields — a routine started by calls (ADR-386)', () => {
  it('keeps « ask first » reachable, says why it is unavailable, and refuses it', async () => {
    const { user, changed } = rendered(
      { requires_approval: false, notify_only_when_new: false },
      true
    );

    expect(asksFirst()).toHaveAttribute('aria-disabled', 'true');
    expect(asksFirst()).toHaveAccessibleDescription(`${STUDIO}.requires_approval_unavailable`);
    await user.click(asksFirst());

    expect(changed).not.toHaveBeenCalled();
    expect(asksFirst()).not.toBeChecked();
  });

  it('still lets it hear only of something new', async () => {
    const { user, changed } = rendered(
      { requires_approval: false, notify_only_when_new: false },
      true
    );

    await user.click(onlyWhenNew());

    expect(changed).toHaveBeenLastCalledWith({
      requires_approval: false,
      notify_only_when_new: true,
    });
  });
});
