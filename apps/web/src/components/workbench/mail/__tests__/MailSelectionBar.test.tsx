/**
 * MailSelectionBar — what selected messages can become, on one line (ADR-369 amendment
 * 2026-11-11): marking read and the folder's own way out as icons, the rest behind « … », the
 * deletion last. Each act says itself in the reader's words, and what the folder does not offer
 * is not drawn.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { MAIL_INBOX, MAIL_SPAM, MAIL_TRASH, movesFrom } from '@/lib/workbench/mail';
import type { MailFolder, MailSummary } from '@/lib/workbench/types';

import { MailSelectionBar, type MailSelectionBarProps } from '../MailSelectionBar';

const MORE = 'common.more_actions';
const mail = (key: string) => `workbench.mail.${key}`;

function row(id: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: id,
    sender: { name: `Sender ${id}`, address: `${id}@example.org` },
    subject: `Subject ${id}`,
    snippet: `Snippet ${id}`,
    received_at: '2026-10-30T08:00:00Z',
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
    ...overrides,
  };
}

const LABELS: MailFolder[] = [
  { id: 'L1', kind: 'user', role: null, name: 'Work' },
  { id: 'L2', kind: 'user', role: null, name: 'Travel' },
];

function draw(over: Partial<MailSelectionBarProps> = {}) {
  const props: MailSelectionBarProps = {
    lng: 'en',
    selected: [row('m1'), row('m2')],
    pageState: 'some',
    bulkMax: 50,
    labels: undefined,
    busy: null,
    moves: movesFrom(MAIL_INBOX, undefined, false),
    onSelectAll: vi.fn(),
    onClear: vi.fn(),
    onRead: vi.fn(),
    onStar: vi.fn(),
    onLabels: vi.fn(),
    onSend: vi.fn(),
    onMove: vi.fn(),
    onForever: vi.fn(),
    ...over,
  };
  return { ...renderWithProviders(<MailSelectionBar {...props} />), props };
}

const bar = () => within(screen.getByRole('region', { name: mail('selection_region') }));

/** The bar's buttons as it draws them, the way out of the selection set aside. */
function drawn(): (string | null)[] {
  return bar()
    .getAllByRole('button')
    .map(button => button.getAttribute('aria-label'))
    .filter(name => name !== mail('clear_selection'));
}

type User = ReturnType<typeof draw>['user'];

async function listed(user: User): Promise<(string | null)[]> {
  await user.click(bar().getByRole('button', { name: MORE }));
  return (await screen.findAllByRole('menuitem')).map(line => line.textContent);
}

async function fromList(user: User, key: string) {
  await user.click(bar().getByRole('button', { name: MORE }));
  await user.click(await screen.findByRole('menuitem', { name: mail(key) }));
}

describe('MailSelectionBar', () => {
  it('draws marking read and archiving, the rest behind « … », the deletion last', async () => {
    const { user } = draw({ labels: LABELS });

    expect(drawn()).toEqual([mail('mark_read'), mail('archive'), MORE, mail('trash')]);
    expect(await listed(user)).toEqual([
      mail('mark_unread'),
      mail('star'),
      mail('move_to'),
      mail('report_spam'),
      mail('labels_title'),
    ]);
  });

  it('offers no labels where the mailbox has none', async () => {
    const { user } = draw();

    expect(await listed(user)).not.toContain(mail('labels_title'));
  });

  it('draws the way back out of the trash, and deletes for good where the mailbox can', async () => {
    const { user } = draw({ moves: movesFrom(MAIL_TRASH, undefined, true) });

    expect(drawn()).toEqual([mail('mark_read'), mail('restore'), MORE, mail('delete_forever')]);
    expect(await listed(user)).toEqual([mail('mark_unread'), mail('star')]);
  });

  it('deletes nothing from a trash it cannot empty by hand', () => {
    draw({ moves: movesFrom(MAIL_TRASH, undefined, false) });

    expect(drawn()).toEqual([mail('mark_read'), mail('restore'), MORE]);
  });

  it('draws the way back out of the spam', () => {
    draw({ moves: movesFrom(MAIL_SPAM, undefined, false) });

    expect(drawn()).toEqual([mail('mark_read'), mail('not_spam'), MORE, mail('trash')]);
  });

  it('runs each act of the bar on the selection', async () => {
    const { user, props } = draw();

    await user.click(bar().getByRole('button', { name: mail('mark_read') }));
    await user.click(bar().getByRole('button', { name: mail('archive') }));
    await user.click(bar().getByRole('button', { name: mail('trash') }));

    expect(props.onRead).toHaveBeenCalledWith(true);
    expect(vi.mocked(props.onSend).mock.calls).toEqual([['archive'], ['trash']]);
  });

  it('runs each act of the list on the selection', async () => {
    const { user, props } = draw();

    await fromList(user, 'mark_unread');
    await fromList(user, 'star');
    await fromList(user, 'move_to');
    await fromList(user, 'report_spam');

    expect(props.onRead).toHaveBeenCalledWith(false);
    expect(props.onStar).toHaveBeenCalledWith(true);
    expect(props.onMove).toHaveBeenCalledTimes(1);
    expect(props.onSend).toHaveBeenCalledWith('spam');
  });

  it('takes the star off a selection that all carries it', async () => {
    const { user, props } = draw({
      selected: [row('m1', { is_starred: true }), row('m2', { is_starred: true })],
    });

    await fromList(user, 'unstar');

    expect(props.onStar).toHaveBeenCalledWith(false);
  });

  it('deletes for good through its own door', async () => {
    const { user, props } = draw({ moves: movesFrom(MAIL_TRASH, undefined, true) });

    await user.click(bar().getByRole('button', { name: mail('delete_forever') }));

    expect(props.onForever).toHaveBeenCalledTimes(1);
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it('states each label on the selection, and applies the one chosen to all of it', async () => {
    const { user, props } = draw({
      labels: LABELS,
      selected: [row('m1', { label_ids: ['L1', 'L2'] }), row('m2', { label_ids: ['L1'] })],
    });

    await listed(user);
    screen.getByRole('menuitem', { name: mail('labels_title') }).focus();
    await user.keyboard('{ArrowRight}');
    const work = await screen.findByRole('menuitemcheckbox', { name: 'Work' });
    const travel = screen.getByRole('menuitemcheckbox', { name: 'Travel' });
    expect(work).toHaveAttribute('aria-checked', 'true');
    expect(travel).toHaveAttribute('aria-checked', 'mixed');
    travel.focus();
    await user.keyboard('{Enter}');

    expect(props.onLabels).toHaveBeenCalledWith(['L2'], []);
  });

  it('sends nothing past the published bound, and says so', async () => {
    const { user, props } = draw({ bulkMax: 1 });

    expect(screen.getByRole('status')).toHaveTextContent(mail('over_bulk'));
    await user.click(bar().getByRole('button', { name: mail('mark_read') }));
    await user.click(bar().getByRole('button', { name: mail('trash') }));

    expect(props.onRead).not.toHaveBeenCalled();
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it('says the act on its way where it stands, and holds the others', async () => {
    const { user, props } = draw({ busy: 'archive' });

    expect(bar().getByRole('button', { name: mail('archive') })).toHaveAttribute(
      'aria-busy',
      'true'
    );
    await user.click(bar().getByRole('button', { name: mail('mark_read') }));

    expect(props.onRead).not.toHaveBeenCalled();
  });

  it('empties the selection from the icon beside the count', async () => {
    const { user, props } = draw();

    expect(bar().getByText(mail('selected'))).toBeInTheDocument();
    await user.click(bar().getByRole('button', { name: mail('clear_selection') }));

    expect(props.onClear).toHaveBeenCalledTimes(1);
  });
});
