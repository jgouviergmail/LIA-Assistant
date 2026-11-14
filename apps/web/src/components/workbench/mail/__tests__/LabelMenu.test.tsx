/**
 * LabelMenu — the person's Gmail labels under their own icon, in the reader's toolbar (ADR-369,
 * spec §6.3). Each label states what is true of the messages now, and a choice applies it to all
 * of them, or takes it off all of them when all carried it. The same lines stand under the line
 * of a selection's list (`MailSelectionBar`).
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MailFolder } from '@/lib/workbench/types';

import { LabelMenu, type LabelLinesProps } from '../LabelMenu';

const TITLE = 'workbench.mail.labels_title';
const LABELS: MailFolder[] = [
  { id: 'L1', kind: 'user', role: null, name: 'Work' },
  { id: 'L2', kind: 'user', role: null, name: 'Travel' },
  { id: 'L3', kind: 'user', role: null, name: 'Home' },
];

function draw(over: Partial<LabelLinesProps> = {}) {
  const props: LabelLinesProps = {
    lng: 'en',
    labels: LABELS,
    messages: [{ label_ids: ['L1', 'L2'] }, { label_ids: ['L1'] }],
    onApply: vi.fn(),
    ...over,
  };
  return { ...renderWithProviders(<LabelMenu {...props} />), props };
}

async function open(user: ReturnType<typeof draw>['user']) {
  await user.click(screen.getByRole('button', { name: TITLE }));
  return screen.findAllByRole('menuitemcheckbox');
}

describe('LabelMenu', () => {
  it('states each label on the messages: carried by all, by some, by none', async () => {
    const { user } = draw();

    const lines = await open(user);

    expect(lines.map(line => [line.textContent, line.getAttribute('aria-checked')])).toEqual([
      ['Work', 'true'],
      ['Travel', 'mixed'],
      ['Home', 'false'],
    ]);
  });

  it('applies to all a label some or none carried', async () => {
    const { user, props } = draw();

    const [, travel] = await open(user);
    await user.click(travel!);

    expect(props.onApply).toHaveBeenCalledWith(['L2'], []);
  });

  it('takes off all a label all carried', async () => {
    const { user, props } = draw();

    const [work] = await open(user);
    await user.click(work!);

    expect(props.onApply).toHaveBeenCalledWith([], ['L1']);
  });

  it('takes nothing while an act is on its way, and says so on its icon', async () => {
    const { user, props } = draw({ busy: true });

    expect(screen.getByRole('button', { name: TITLE })).toHaveAttribute('aria-disabled', 'true');
    const [work] = await open(user);
    await user.click(work!);

    expect(props.onApply).not.toHaveBeenCalled();
  });

  it('says a mailbox that has no label yet', async () => {
    const { user } = draw({ labels: [] });

    await user.click(screen.getByRole('button', { name: TITLE }));

    expect(
      await screen.findByRole('menuitem', { name: 'workbench.mail.no_labels' })
    ).toHaveAttribute('aria-disabled', 'true');
  });
});
