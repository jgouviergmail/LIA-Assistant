import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';
import en from '../../../../locales/en/translation.json';
import { WorldMessageControls, type WorldConversationHandle } from '../WorldMessageControls';
import { createRef } from 'react';
import type { MessageWrite } from '../message-protocol';

const id = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const peer = '5010c2c2-4bd0-4d21-9c08-b4502db25d72';
const mocks = vi.hoisted(() => ({
  user: null as User | null,
  send: vi.fn(),
  sendPublic: vi.fn(),
  publicReady: false,
  translate: vi.fn(),
  check: vi.fn(),
  discard: vi.fn(),
  retry: vi.fn(),
  setReading: vi.fn(),
  accepted: null as ((intent: Readonly<MessageWrite>) => void) | null,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      let value: unknown = en;
      for (const segment of key.split('.'))
        value =
          value && typeof value === 'object' && segment in value
            ? Reflect.get(value, segment)
            : undefined;
      return typeof value === 'string' ? value : key;
    },
  }),
}));
vi.mock('../useWorldMessages', () => ({
  useWorldMessages: (
    _owner: string,
    _enabled: boolean,
    _scope: unknown,
    accepted: (intent: Readonly<MessageWrite>) => void
  ) => {
    mocks.accepted = accepted;
    return {
      ...mocks,
      state: {
        status: 'online',
        sending: 'idle',
        unread: 1,
        unreadByRecipient: { [peer]: 1 },
        operation: null,
        mailbox: {
          server_time: 1000,
          ttl_seconds: 1800,
          truncated: false,
          ...(mocks.publicReady
            ? { public_available: true, public_messages: [], public_truncated: false }
            : {}),
          messages: [
            {
              id,
              sender_id: peer,
              sender_alias: 'Peer',
              recipient_id: id,
              recipient_alias: 'You',
              outgoing: false,
              original: '<img src=x onerror=alert(1)>',
              text: null,
              language: 'en',
              status: 'pending',
              created_at: 999,
              expires_at: 2799,
              receipt: null,
            },
          ],
        },
      },
    };
  },
}));
const props = {
  lng: 'en' as const,
  ownerId: id,
  enabled: true,
  canOpen: true,
  canSend: true,
  participants: [{ id: peer, alias: 'Peer' }],
  getScope: () => ({ epoch: id, controller: 'c'.repeat(43) }),
  onOpen: vi.fn(),
};

beforeEach(() => {
  mocks.publicReady = false;
  mocks.sendPublic.mockResolvedValue('accepted');
  mocks.send.mockResolvedValue('accepted');
  mocks.user = makeUser({ id, is_active: true });
});

it('keeps the original hidden until explicitly requested and renders it as literal text', async () => {
  const view = render(<WorldMessageControls {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  expect(screen.queryByText('<img src=x onerror=alert(1)>')).not.toBeInTheDocument();
  expect(screen.queryByRole('log')).not.toBeInTheDocument();
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
  fireEvent.click(await screen.findByRole('button', { name: /^Peer/ }));
  fireEvent.click(await screen.findByText('Show original'));
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
  expect(document.querySelector('img')).toBeNull();
  fireEvent.change(screen.getByRole('textbox', { name: 'Your message' }), {
    target: { value: 'Draft kept across a transient reconnect' },
  });
  view.rerender(<WorldMessageControls {...props} enabled={false} />);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  view.rerender(<WorldMessageControls {...props} />);
  expect(await screen.findByRole('textbox', { name: 'Your message' })).toHaveValue(
    'Draft kept across a transient reconnect'
  );
});

it('cannot open a private conversation for a different authenticated account', () => {
  render(<WorldMessageControls {...props} ownerId="different-owner" />);
  expect(screen.getByRole('button', { name: 'Chat with people' })).toBeDisabled();
});

it('opens the selected person without sending and keeps drafts bound to their recipient', async () => {
  const second = '6010c2c2-4bd0-4d21-9c08-b4502db25d72';
  const handle = createRef<WorldConversationHandle>();
  render(
    <WorldMessageControls
      {...props}
      conversationRef={handle}
      participants={[...props.participants, { id: second, alias: 'Second' }]}
    />
  );
  act(() => {
    expect(handle.current?.openFor(peer)).toBe(true);
  });
  const field = await screen.findByRole('textbox', { name: 'Your message' });
  fireEvent.change(field, { target: { value: 'Same words, two different people' } });
  act(() => {
    expect(handle.current?.openFor(second)).toBe(true);
  });
  expect(field).toHaveValue('');
  fireEvent.change(field, { target: { value: 'Same words, two different people' } });
  act(() => {
    mocks.accepted?.({
      ...props.getScope(),
      id,
      recipient: peer,
      created_at: 1000,
      text: 'Same words, two different people',
      translation_consent: true,
    });
  });
  expect(field).toHaveValue('Same words, two different people');
  act(() => {
    handle.current?.openFor(peer);
  });
  expect(field).toHaveValue('');
  act(() => {
    handle.current?.openFor(second);
  });
  expect(field).toHaveValue('Same words, two different people');
  expect(mocks.send).not.toHaveBeenCalled();
});

it('refuses a missing person or a stale-owner scene command', () => {
  const handle = createRef<WorldConversationHandle>();
  const view = render(<WorldMessageControls {...props} conversationRef={handle} />);
  act(() => {
    expect(handle.current?.openFor('missing')).toBe(false);
  });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  view.rerender(
    <WorldMessageControls {...props} conversationRef={handle} ownerId="different-owner" />
  );
  act(() => {
    expect(handle.current?.openFor(peer)).toBe(false);
  });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('returns focus to the scene after switching recipients inside the conversation', async () => {
  const handle = createRef<WorldConversationHandle>();
  render(
    <>
      <canvas tabIndex={0} aria-label="Scene" />
      <WorldMessageControls {...props} conversationRef={handle} />
    </>
  );
  const canvas = screen.getByLabelText('Scene');
  canvas.focus();
  act(() => {
    handle.current?.openFor(peer);
  });
  const field = await screen.findByRole('textbox', { name: 'Your message' });
  field.focus();
  act(() => {
    handle.current?.openFor(peer);
  });
  fireEvent.keyDown(field, { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(canvas).toHaveFocus();
});

it('keeps public drafts and translation permission separate from private conversations', async () => {
  mocks.publicReady = true;
  render(<WorldMessageControls {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  fireEvent.click(await screen.findByRole('button', { name: /^Everyone/ }));
  const field = await screen.findByRole('textbox', { name: 'Your message' });
  fireEvent.change(field, { target: { value: 'Hello everyone' } });
  const permission = screen.getByRole('checkbox');
  fireEvent.click(permission);
  fireEvent.click(screen.getByRole('button', { name: /^Peer/ }));
  expect(field).toHaveValue('');
  expect(permission).not.toBeChecked();
  fireEvent.change(field, { target: { value: 'Private draft' } });
  fireEvent.click(screen.getByRole('button', { name: /^Everyone/ }));
  expect(field).toHaveValue('Hello everyone');
  expect(permission).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(mocks.sendPublic).toHaveBeenCalledWith('Hello everyone', true);
  act(() =>
    mocks.accepted?.({
      ...props.getScope(),
      audience: 'public',
      id,
      created_at: 1000,
      text: 'Hello everyone',
      translation_consent: true,
    })
  );
  expect(field).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: /^Peer/ }));
  expect(field).toHaveValue('Private draft');
});
