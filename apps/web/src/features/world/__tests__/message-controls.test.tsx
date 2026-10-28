import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';
import en from '../../../../locales/en/translation.json';
import { WorldMessageControls, type WorldConversationHandle } from '../WorldMessageControls';
import { Activity, createRef } from 'react';
import type { MessageWrite } from '../message-protocol';

const id = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const peer = '5010c2c2-4bd0-4d21-9c08-b4502db25d72';
const mocks = vi.hoisted(() => ({
  user: null as User | null,
  send: vi.fn(),
  sendPublic: vi.fn(),
  publicReady: false,
  sending: 'idle' as 'idle' | 'sending' | 'uncertain',
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
        sending: mocks.sending,
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
  vi.clearAllMocks();
  mocks.sending = 'idle';
  mocks.publicReady = false;
  mocks.sendPublic.mockResolvedValue('accepted');
  mocks.send.mockResolvedValue('accepted');
  mocks.user = makeUser({ id, is_active: true });
});

afterEach(() => document.querySelectorAll('[data-test-chat-host]').forEach(host => host.remove()));

function compactHost() {
  const host = document.createElement('div');
  host.dataset.testChatHost = '';
  document.body.append(host);
  return host;
}

it('selects the nearest peer automatically then public when nobody is near, without opening Discuter', () => {
  mocks.publicReady = true;
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  const recipient = within(host).getByRole('combobox');
  expect(recipient).toHaveDisplayValue('Auto · Private · Peer');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(props.onOpen).toHaveBeenLastCalledWith(false);
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  expect(recipient).toHaveDisplayValue('Auto · Public · Everyone');
  expect(mocks.send).not.toHaveBeenCalled();
  expect(mocks.sendPublic).not.toHaveBeenCalled();
});

it('pins a compact private draft while its peer moves away and shares it with the full panel', async () => {
  mocks.publicReady = true;
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  const field = within(host).getByRole('textbox', { name: 'Your message' });
  fireEvent.focus(field);
  fireEvent.change(field, { target: { value: 'Only for Peer' } });
  fireEvent.blur(field);
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  expect(within(host).getByRole('combobox')).toHaveDisplayValue('Auto · Private · Peer');
  expect(field).toHaveValue('Only for Peer');
  fireEvent.click(within(host).getByRole('button', { name: 'Open full conversation' }));
  expect(await screen.findByRole('textbox', { name: 'Your message' })).toHaveValue('Only for Peer');
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  expect(mocks.sendPublic).not.toHaveBeenCalled();
});

it('allows choosing another peer and keeps private and public drafts separate', () => {
  mocks.publicReady = true;
  const host = compactHost();
  const second = { id: '6010c2c2-4bd0-4d21-9c08-b4502db25d72', alias: 'Second' };
  render(
    <WorldMessageControls
      {...props}
      compactHost={host}
      participants={[...props.participants, second]}
      nearbyParticipants={[...props.participants, second]}
    />
  );
  const recipient = within(host).getByRole('combobox');
  const field = within(host).getByRole('textbox');
  fireEvent.change(field, { target: { value: 'Private words' } });
  fireEvent.change(recipient, { target: { value: second.id } });
  expect(field).toHaveValue('');
  expect(recipient).toHaveDisplayValue('Private · Second');
  fireEvent.change(recipient, { target: { value: '@public' } });
  expect(field).toHaveValue('');
  fireEvent.change(field, { target: { value: 'Public words' } });
  fireEvent.change(recipient, { target: { value: peer } });
  expect(field).toHaveValue('Private words');
});

it('requires explicit translation permission before sending from the compact conversation', async () => {
  const host = compactHost();
  render(
    <WorldMessageControls {...props} compactHost={host} nearbyParticipants={props.participants} />
  );
  fireEvent.change(within(host).getByRole('textbox'), { target: { value: 'Hello Peer' } });
  fireEvent.click(within(host).getByRole('button', { name: 'Send' }));
  expect(mocks.send).not.toHaveBeenCalled();
  const permission = await screen.findByRole('dialog');
  fireEvent.click(within(permission).getByRole('checkbox'));
  fireEvent.keyDown(permission, { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  // The send settles its outcome after the click: let it land inside act.
  await act(async () => {
    fireEvent.click(within(host).getByRole('button', { name: 'Send' }));
  });
  expect(mocks.send).toHaveBeenCalledWith(peer, 'Hello Peer', true);
});

it('keeps a departed recipient draft private and refuses every way of sending until they return', async () => {
  const fine = vi.mocked(window.matchMedia).getMockImplementation();
  vi.mocked(window.matchMedia).mockImplementation(query => ({
    ...(fine?.(query) ?? window.matchMedia(query)),
    matches: query === '(pointer:fine)',
  }));
  try {
    const host = compactHost();
    const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
    const view = render(<WorldMessageControls {...options} />);
    const field = within(host).getByRole('textbox');
    fireEvent.change(field, { target: { value: 'Do not publish' } });
    view.rerender(<WorldMessageControls {...options} participants={[]} nearbyParticipants={[]} />);
    expect(field).toHaveValue('Do not publish');
    const send = within(host).getByRole('button', { name: 'Send' });
    expect(send).toHaveAttribute('aria-disabled', 'true');
    expect(within(host).getByRole('combobox')).toHaveDisplayValue('Auto · Private · Peer');
    fireEvent.click(send);
    fireEvent.keyDown(field, { key: 'Enter', code: 'Enter' });
    const form = field.closest('form');
    if (!form) throw new Error('Missing composer form');
    fireEvent.submit(form);
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.sendPublic).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<WorldMessageControls {...options} />);
    fireEvent.click(within(host).getByRole('button', { name: 'Send' }));
    const permission = await screen.findByRole('dialog');
    fireEvent.click(within(permission).getByRole('checkbox'));
    fireEvent.keyDown(permission, { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    // The dialog hands the focus back on a later task: let it land inside act.
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    await act(async () => {
      fireEvent.keyDown(within(host).getByRole('textbox'), { key: 'Enter', code: 'Enter' });
    });
    expect(mocks.send).toHaveBeenCalledExactlyOnceWith(peer, 'Do not publish', true);
    expect(mocks.sendPublic).not.toHaveBeenCalled();
  } finally {
    if (fine) vi.mocked(window.matchMedia).mockImplementation(fine);
  }
});
it('opens the phone conversation bar with the keyboard in its composer', async () => {
  const host = compactHost();
  const strip = document.createElement('div');
  host.after(strip);
  const options = {
    ...props,
    compactHost: host,
    compactOnDemand: true,
    nearbyParticipants: props.participants,
  };
  const view = render(<WorldMessageControls {...options} />, { container: strip });
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  const launcher = screen.getByRole('button', { name: 'Chat with people' });
  act(() => launcher.focus());
  fireEvent.click(launcher);
  const composer = await within(host).findByRole('textbox', { name: 'Your message' });
  expect(composer).toHaveFocus();
  // A later re-render of the open bar never pulls the focus back.
  act(() => launcher.focus());
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  expect(launcher).toHaveFocus();
  fireEvent.click(within(host).getByRole('button', { name: 'Close quick conversation' }));
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  expect(launcher).toHaveFocus();
});
it('explains translation in one dialog opened by a dialog button, not a toggle', async () => {
  const host = compactHost();
  render(
    <WorldMessageControls {...props} compactHost={host} nearbyParticipants={props.participants} />
  );
  const details = within(host).getByRole('button', { name: 'Translation and usage' });
  expect(details).toHaveAttribute('aria-haspopup', 'dialog');
  expect(details).not.toHaveAttribute('aria-pressed');
  fireEvent.click(details);
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByRole('checkbox')).toBeInTheDocument();
  expect(within(dialog).queryByRole('button', { name: 'Translation and usage' })).toBeNull();
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
});

it('holds an empty focused composer until focus leaves, then resumes automatic selection', () => {
  mocks.publicReady = true;
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  const field = within(host).getByRole('textbox');
  fireEvent.focus(field);
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  expect(within(host).getByRole('combobox')).toHaveDisplayValue('Auto · Private · Peer');
  fireEvent.blur(field);
  expect(within(host).getByRole('combobox')).toHaveDisplayValue('Auto · Public · Everyone');
});

it('does not mark compact history read when collapsed and keeps it collapsed across Discuter', async () => {
  mocks.publicReady = true;
  const host = compactHost();
  render(
    <WorldMessageControls {...props} compactHost={host} nearbyParticipants={props.participants} />
  );
  fireEvent.click(within(host).getByRole('button', { name: 'Hide recent messages' }));
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
  fireEvent.click(within(host).getByRole('button', { name: 'Open full conversation' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(within(host).queryByRole('log')).not.toBeInTheDocument();
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
});

it('opens the same thread in Discuter during uncertain delivery without sending again', async () => {
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  fireEvent.change(within(host).getByRole('textbox'), {
    target: { value: 'Keep this destination' },
  });
  mocks.sending = 'uncertain';
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  expect(await screen.findByRole('textbox', { name: 'Your message' })).toHaveValue(
    'Keep this destination'
  );
  expect(mocks.send).not.toHaveBeenCalled();
});

it('preserves a draft started in Discuter after expansion from an untouched compact composer', async () => {
  mocks.publicReady = true;
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  const field = await screen.findByRole('textbox', { name: 'Your message' });
  fireEvent.change(field, { target: { value: 'Private from full panel' } });
  view.rerender(<WorldMessageControls {...options} nearbyParticipants={[]} />);
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(within(host).getByRole('textbox')).toHaveValue('Private from full panel');
  expect(within(host).getByRole('combobox')).toHaveDisplayValue('Auto · Private · Peer');
});

it('returns focus to the new compact opener after closing the full panel', async () => {
  const host = compactHost();
  render(
    <WorldMessageControls {...props} compactHost={host} nearbyParticipants={props.participants} />
  );
  const expand = within(host).getByRole('button', { name: 'Open full conversation' });
  act(() => expand.focus());
  fireEvent.click(expand);
  fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(within(host).getByRole('button', { name: 'Open full conversation' })).toHaveFocus();
});

it('does not read a compact thread when other controls hide its history', () => {
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const view = render(<WorldMessageControls {...options} />);
  expect(mocks.setReading).toHaveBeenLastCalledWith(true, peer);
  view.rerender(<WorldMessageControls {...options} compactEnabled={false} />);
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
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
  await act(async () => {
    // Drain the send result after checking its synchronous transport invocation.
  });
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

it('distinguishes peers with the same public name in the compact recipient selector', () => {
  const host = compactHost();
  const second = { id: '6010c2c2-4bd0-4d21-9c08-b4502db20002', alias: 'Peer' };
  render(
    <WorldMessageControls
      {...props}
      compactHost={host}
      participants={[...props.participants, second]}
      nearbyParticipants={props.participants}
    />
  );
  const recipient = within(host).getByRole('combobox');
  expect(recipient).toHaveDisplayValue('Auto · Private · Peer #5d72');
  expect(within(recipient).getByRole('option', { name: 'Private · Peer #0002' })).toHaveValue(
    second.id
  );
  fireEvent.change(recipient, { target: { value: second.id } });
  expect(recipient).toHaveDisplayValue('Private · Peer #0002');
});

it('opens the phone composer only from Discuter and keeps its draft when closed and reopened', async () => {
  const host = compactHost();
  const foldControls = vi.fn();
  render(
    <WorldMessageControls
      {...props}
      compactHost={host}
      compactOnDemand
      onCompactOpen={foldControls}
      nearbyParticipants={props.participants}
    />
  );
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  expect(foldControls).toHaveBeenCalledOnce();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  const field = within(host).getByRole('textbox');
  fireEvent.change(field, { target: { value: 'Keep my phone draft' } });
  fireEvent.click(within(host).getByRole('button', { name: 'Hide recent messages' }));
  expect(within(host).queryByRole('log')).not.toBeInTheDocument();
  expect(field).toBeVisible();
  fireEvent.click(within(host).getByRole('button', { name: 'Close quick conversation' }));
  expect(within(host).queryByRole('textbox')).not.toBeInTheDocument();
  expect(mocks.setReading).toHaveBeenLastCalledWith(false, null);
  fireEvent.click(screen.getByRole('button', { name: 'Chat with people' }));
  expect(within(host).getByRole('textbox')).toHaveValue('Keep my phone draft');
  fireEvent.click(within(host).getByRole('button', { name: 'Open full conversation' }));
  expect(await screen.findByRole('textbox', { name: 'Your message' })).toHaveValue(
    'Keep my phone draft'
  );
});
it('keeps a compact draft through a hidden and revealed private subtree without sending it', () => {
  const host = compactHost();
  const options = { ...props, compactHost: host, nearbyParticipants: props.participants };
  const tree = (mode: 'visible' | 'hidden') => (
    <Activity mode={mode}>
      <WorldMessageControls {...options} />
    </Activity>
  );
  const view = render(tree('visible'));
  fireEvent.change(within(host).getByRole('textbox'), { target: { value: 'Not yet' } });
  for (const mode of ['hidden', 'visible', 'hidden', 'visible'] as const) view.rerender(tree(mode));
  expect(within(host).getByRole('textbox')).toHaveValue('Not yet');
  expect(mocks.send).not.toHaveBeenCalled();
  expect(mocks.sendPublic).not.toHaveBeenCalled();
  expect(mocks.translate).not.toHaveBeenCalled();
});
