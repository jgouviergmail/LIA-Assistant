/**
 * The conversation of the open message (ADR-369, lot 8.1).
 *
 * A message alone says nothing; a longer exchange is one line, opened on demand, that keeps
 * its place while the person walks it. The number is exact or it is stated as the latest
 * ones; a conversation that could not be read says so; the open message is marked and every
 * row stays a link, so the focus survives the walk.
 */

import { describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { MailSummary } from '@/lib/workbench/types';

import { ConversationBand, type ConversationBandProps } from '../ConversationBand';
import type { ConversationState } from '../useMailScreen';

function row(id: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: 't1',
    sender: { name: `Sender ${id}`, address: `${id}@example.org` },
    subject: 'Budget',
    snippet: `Snippet ${id}`,
    received_at: '2026-10-30T08:00:00Z',
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
    ...overrides,
  };
}

function band(
  conversation: Partial<ConversationState>,
  overrides: Partial<ConversationBandProps> = {}
) {
  const props: ConversationBandProps = {
    lng: 'en',
    conversation: {
      rows: [],
      truncated: false,
      failed: false,
      expanded: false,
      setExpanded: vi.fn(),
      refresh: vi.fn(),
      ...conversation,
    },
    openId: 'm2',
    whenOf: message => message.received_at && 'Yesterday',
    hrefOf: message => `/mail?id=${message.id}`,
    onOpen: vi.fn(),
    ...overrides,
  };
  return { ...renderWithProviders(<ConversationBand {...props} />), props };
}

const expanded = { rows: [row('m1'), row('m2')], expanded: true };
const list = () => screen.getByRole('list', { name: 'workbench.mail.conversation_title' });

describe('ConversationBand', () => {
  it('says nothing of a message alone', () => {
    band({ rows: [row('m2')] });

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('says nothing before it is read', () => {
    band({ rows: [] });

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('is one line until the person opens it', async () => {
    const setExpanded = vi.fn();
    const { user } = band({ rows: [row('m1'), row('m2')], setExpanded });

    const opener = screen.getByRole('button', { name: 'workbench.mail.conversation_count' });
    expect(opener).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('list')).not.toBeInTheDocument();

    await user.click(opener);

    expect(setExpanded).toHaveBeenCalledWith(true);
  });

  it('states a cut instead of a total', () => {
    band({ rows: [row('m1'), row('m2')], truncated: true });

    expect(
      screen.getByRole('button', { name: 'workbench.mail.conversation_latest' })
    ).toBeInTheDocument();
  });

  it('tells who, when and a line of each, the open message marked', () => {
    band(expanded);

    const open = within(list()).getByRole('link', { name: /Sender m2/ });
    expect(open).toHaveAttribute('aria-current', 'true');
    expect(open).toHaveTextContent('Yesterday');
    expect(open).toHaveTextContent('Snippet m2');
    expect(within(list()).getByRole('link', { name: /Sender m1/ })).not.toHaveAttribute(
      'aria-current'
    );
  });

  it('names a message with no sender', () => {
    band({ rows: [row('m1', { sender: null }), row('m2')], expanded: true });

    expect(
      within(list()).getByRole('link', { name: /workbench.mail.unknown_sender/ })
    ).toBeInTheDocument();
  });

  it('opens a message in place on a plain click', async () => {
    const { user, props } = band(expanded);

    await user.click(within(list()).getByRole('link', { name: /Sender m1/ }));

    expect(props.onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'm1' }));
  });

  it('leaves a click with a modifier to the browser', () => {
    const { props } = band(expanded);

    fireEvent.click(within(list()).getByRole('link', { name: /Sender m1/ }), { ctrlKey: true });

    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it('points each row at its message', () => {
    band(expanded);

    expect(within(list()).getByRole('link', { name: /Sender m1/ })).toHaveAttribute(
      'href',
      '/mail?id=m1'
    );
  });

  it('says a conversation it could not read', () => {
    band({ failed: true });

    expect(screen.getByRole('status')).toHaveTextContent('workbench.mail.conversation_failed');
  });
});
