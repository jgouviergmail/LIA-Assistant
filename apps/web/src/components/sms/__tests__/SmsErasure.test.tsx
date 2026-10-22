import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { SmsEraseButton, SmsErasureProvider } from '../SmsErasure';
import { SmsMessageList } from '../SmsMessageList';
import type { SmsMessage } from '@/types/sms';

const message: SmsMessage = {
  id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  sender: '+33612345678',
  display_name: 'Alice',
  identity_source: 'contact',
  identity_state: 'resolved',
  relation_key: null,
  body: 'Literal SMS',
  received_at: '2026-10-25T12:00:00Z',
  date_kind: 'captured',
  origin: 'iphone',
};

it('proposes only the selected message and a complete account day across DST', () => {
  const request = vi.fn();
  render(
    <SmsErasureProvider value={{ busy: false, request }}>
      <SmsMessageList messages={[message]} lng="en" timezone="Europe/Paris" eraseDays />
    </SmsErasureProvider>
  );
  fireEvent.click(screen.getByRole('button', { name: /sms.erase_message/ }));
  expect(request).toHaveBeenLastCalledWith({ message_ids: [message.id] });
  fireEvent.click(screen.getByRole('button', { name: /sms.erase_day/ }));
  expect(request).toHaveBeenLastCalledWith({
    from_ts: '2026-10-24T22:00:00.000Z',
    to_ts: '2026-10-25T23:00:00.000Z',
  });
  expect(screen.queryByText('sms.captured')).not.toBeInTheDocument();
});

it('keeps the single-message delete icon named without a visible button label', () => {
  render(
    <SmsErasureProvider value={{ busy: false, request: vi.fn() }}>
      <SmsMessageList messages={[message]} lng="en" timezone="UTC" />
    </SmsErasureProvider>
  );
  const button = screen.getByRole('button', { name: /sms.erase_message/ });
  expect(button).toHaveTextContent(/^$/);
  expect(button).toHaveAttribute('title', 'sms.erase_message');
});

it.each([false, true])(
  'restores focus after removal without overriding another control (%s)',
  async moved => {
    const request = vi.fn();
    function View({ retained }: { retained: boolean }) {
      return (
        <>
          <input aria-label="Other control" />
          <details open>
            <summary>Messages</summary>
            <SmsErasureProvider value={{ busy: false, request }}>
              <SmsMessageList messages={retained ? [message] : []} lng="en" timezone="UTC" />
            </SmsErasureProvider>
          </details>
        </>
      );
    }
    const view = render(<View retained />);
    const button = screen.getByRole('button', { name: /sms.erase_message/ });
    button.focus();
    fireEvent.click(button);
    const other = screen.getByRole('textbox', { name: 'Other control' });
    if (moved) other.focus();
    view.rerender(<View retained={false} />);
    await waitFor(() => expect(moved ? other : screen.getByText('Messages')).toHaveFocus());
  }
);

it.each([
  ['sender', false],
  ['sender', true],
  ['day', false],
  ['day', true],
] as const)(
  'returns the focus once a grouped erasure removed its group (%s, moved: %s)',
  async (kind, moved) => {
    const request = vi.fn();
    const scope = () =>
      kind === 'sender'
        ? { sender_id: message.id }
        : { from_ts: '2026-10-24T22:00:00.000Z', to_ts: '2026-10-25T23:00:00.000Z' };
    function View({ retained }: { retained: boolean }) {
      return (
        <SmsErasureProvider value={{ busy: false, request }}>
          <input aria-label="Other control" />
          <details open>
            <summary>Archive</summary>
            {retained && (
              <details open>
                <summary>Group</summary>
                <SmsEraseButton kind={kind} target="Alice" scope={scope} />
              </details>
            )}
          </details>
        </SmsErasureProvider>
      );
    }
    const view = render(<View retained />);
    const button = screen.getByRole('button', { name: new RegExp(`sms.erase_${kind}`) });
    button.focus();
    fireEvent.click(button);
    expect(request).toHaveBeenCalledWith(scope());
    // The confirmation dialog closes first and hands the focus back to the
    // button, which still exists at that moment…
    button.focus();
    const other = screen.getByRole('textbox', { name: 'Other control' });
    if (moved) other.focus();
    // …then the refresh removes the whole group, the button with it.
    view.rerender(<View retained={false} />);
    await waitFor(() => expect(moved ? other : screen.getByText('Archive')).toHaveFocus());
  }
);

it('does not offer destructive controls on read-only surfaces and guards a busy proposal', () => {
  const request = vi.fn();
  const view = render(<SmsMessageList messages={[message]} lng="en" timezone="UTC" />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  view.rerender(
    <SmsErasureProvider value={{ busy: true, request }}>
      <SmsMessageList messages={[message]} lng="en" timezone="UTC" eraseDays />
    </SmsErasureProvider>
  );
  fireEvent.click(screen.getByRole('button', { name: /sms.erase_message/ }));
  expect(request).not.toHaveBeenCalled();
});
