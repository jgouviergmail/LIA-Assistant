/**
 * What a ticket notification offers under its bubble.
 *
 * The row is self-gated on the metadata: mounted on every assistant bubble, it
 * must render NOTHING for the ones that are not workboard notifications. And
 * « finish in the chat » exists for a run that STOPPED needing the person —
 * offering it on a finished run invites a turn with nothing to do.
 */
import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { WorkboardNotificationActions } from '@/components/chat/WorkboardNotificationActions';

const BOARD = 'https://lia.example/dashboard/workboard';
const TICKET = `${BOARD}/8f0e`;
const INTENT = 'https://lia.example/dashboard/chat?intent=finish';

function render(metadata: Record<string, unknown> | undefined) {
  return renderWithProviders(<WorkboardNotificationActions metadata={metadata} />);
}

describe('when the bubble is not a ticket notification', () => {
  it('renders nothing at all', () => {
    // The row is mounted on EVERY assistant bubble; a stray group would put an
    // empty landmark under every answer in the history.
    for (const metadata of [
      undefined,
      {},
      { type: 'proactive_interest' },
      { type: 'proactive_peer_message' },
      { type: 'error' },
    ]) {
      const { container } = render(metadata);
      expect(container).toBeEmptyDOMElement();
    }
  });
});

describe('when it is', () => {
  it('offers the ticket and the board, from the URLs the API composed', () => {
    render({
      type: 'proactive_workboard',
      event: 'run_finished',
      board_url: BOARD,
      ticket_url: TICKET,
    });

    expect(screen.getByRole('link', { name: 'workboard.actions.open_ticket' })).toHaveAttribute(
      'href',
      TICKET
    );
    expect(screen.getByRole('link', { name: 'workboard.actions.open_board' })).toHaveAttribute(
      'href',
      BOARD
    );
  });

  it('offers « finish in the chat » only when the run stopped for the person', () => {
    render({ type: 'proactive_workboard', event: 'run_finished', board_url: BOARD });
    expect(
      screen.queryByRole('link', { name: 'workboard.actions.finish_in_chat' })
    ).not.toBeInTheDocument();

    render({
      type: 'proactive_workboard',
      event: 'waiting',
      board_url: BOARD,
      ticket_url: TICKET,
      intent: INTENT,
    });
    expect(screen.getByRole('link', { name: 'workboard.actions.finish_in_chat' })).toHaveAttribute(
      'href',
      INTENT
    );
  });

  it('skips a link the notification did not carry rather than inventing one', () => {
    // A URL rebuilt here would be a second authority on where a ticket lives.
    render({ type: 'proactive_workboard', event: 'assigned', board_url: BOARD });

    expect(
      screen.queryByRole('link', { name: 'workboard.actions.open_ticket' })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'workboard.actions.open_board' })).toBeInTheDocument();
  });

  it('ignores a field of the wrong shape', () => {
    render({ type: 'proactive_workboard', board_url: 42, ticket_url: '' });

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('names the group so a screen reader can skip it', () => {
    render({ type: 'proactive_workboard', board_url: BOARD });

    expect(
      screen.getByRole('group', { name: 'workboard.notification.actions_label' })
    ).toBeInTheDocument();
  });
});
