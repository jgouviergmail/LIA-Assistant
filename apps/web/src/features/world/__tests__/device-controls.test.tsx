import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createRef, useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import type { UseNotificationsOptions } from '@/hooks/useNotifications';
import { WorldDeviceControls, type WorldDeviceHandle } from '../WorldDeviceControls';
import { useWorldPrivateSignals } from '../useWorldPrivateSignals';
const owner = 'ef910df4-a74c-4007-a41c-88dc9a43655d';
const state = vi.hoisted(() => ({
  options: {} as UseNotificationsOptions,
  user: undefined as ReturnType<typeof makeUser> | undefined,
  run: vi.fn(),
  readers: [] as UseNotificationsOptions[],
}));
vi.mock('@/components/theme-toggle', () => ({
  ThemeToggle: () => <button aria-label="Native theme control" />,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: state.user }) }));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (options: UseNotificationsOptions) => {
    state.options = options;
    state.readers.push(options);
    return {};
  },
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { sms_enabled: true } } }),
}));
vi.mock('@/hooks/useSettingsAvailability', () => ({
  useSettingsAvailability: () => ({ radioEnabled: true }),
}));
vi.mock('@/components/radio/RadioControl', () => ({
  useRadioCommand: (enabled: boolean) =>
    enabled ? { onAir: false, busy: false, run: state.run } : null,
}));
vi.mock('next/dynamic', () => ({ default: () => () => <p>Native private message</p> }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      key === 'world.device.phone' ? 'Phone ' + values?.sms + ' ' + values?.reminders : key,
  }),
}));
const props = {
  lng: 'en' as const,
  ownerId: owner,
  enabled: true,
  interactive: true,
  onOpen: vi.fn(),
  onActivity: vi.fn(),
};
beforeEach(() => {
  vi.clearAllMocks();
  state.readers = [];
  state.user = makeUser({ id: owner, is_active: true });
});
const sms = {
  type: 'sms_received' as const,
  user_id: owner,
  message_id: '51bb9a96-5f4f-431e-9887-a5922ac6fa8a',
  occurrence_id: 'ed84f7c8-1a66-4eb7-a606-c5e3ce3253ba',
};
it('keeps the toolbar opener available while interacting with its native photo panel', () => {
  render(
    <>
      <WorldDeviceControls {...props} />
      <div data-world-native-panel>
        <button>Photo format</button>
      </div>
    </>
  );
  const tools = screen.getByRole('button', { name: 'world.device.tools' });
  fireEvent.click(tools);
  expect(tools).toHaveAttribute('aria-expanded', 'true');
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Photo format' }));
  expect(tools).toHaveAttribute('aria-expanded', 'true');
});
it('expanding the widget toolbar keeps sibling actions usable while a private phone panel pauses them', () => {
  function Host() {
    const [privateOpen, setPrivateOpen] = useState(false);
    return (
      <WorldDeviceControls
        {...props}
        onOpen={setPrivateOpen}
        extras={<button disabled={privateOpen}>Photo sibling</button>}
      />
    );
  }
  render(<Host />);
  const sibling = screen.getByRole('button', { name: 'Photo sibling' });
  fireEvent.click(screen.getByRole('button', { name: 'world.device.tools' }));
  expect(sibling).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Phone 0 0' }));
  expect(sibling).toBeDisabled();
});
it('uses one shared World receiver for both the phone and physical object signals', () => {
  function SharedDevices() {
    const signals = useWorldPrivateSignals(owner, true);
    return <WorldDeviceControls {...props} signals={signals} />;
  }
  render(<SharedDevices />);
  expect(new Set(state.readers.map(options => options.onSmsReceived)).size).toBe(1);
  act(() => state.options.onSmsReceived?.(sms));
  fireEvent.click(screen.getByRole('button', { name: 'Phone 1 0' }));
  fireEvent.click(screen.getByRole('button', { name: 'sms.new_received' }));
  expect(screen.getByText('Native private message')).toBeVisible();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
  expect(screen.getByRole('button', { name: 'Phone 0 0' })).toBeVisible();
});
it('returns focus to the scene after a physical reminder reader closes', async () => {
  const deviceRef = createRef<WorldDeviceHandle>();
  const canvas = document.createElement('canvas');
  canvas.className = 'world-canvas';
  canvas.tabIndex = 0;
  document.body.append(canvas);
  try {
    render(<WorldDeviceControls {...props} deviceRef={deviceRef} />);
    act(() =>
      state.options.onNotification?.({
        id: 'reminder',
        type: 'reminder',
        reminder_id: 'reminder',
        content: 'Private reminder',
        timestamp: new Date(),
        read: false,
      })
    );
    canvas.focus();
    act(() => {
      expect(deviceRef.current?.openNotice('reminder:1')).toBe(true);
    });
    expect(screen.getByText('Private reminder')).toBeVisible();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(canvas).toHaveFocus());
  } finally {
    canvas.remove();
  }
});
it('drafts a call only after a deliberate tap and reuses the one native radio command', () => {
  render(<WorldDeviceControls {...props} />);
  expect(props.onActivity).not.toHaveBeenCalled();
  expect(state.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Phone 0 0' }));
  expect(props.onActivity).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'sms.archive' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'world.activities.call' }));
  expect(props.onActivity).toHaveBeenCalledExactlyOnceWith({ kind: 'compose', id: 'call' });
  fireEvent.click(screen.getByRole('button', { name: 'radio.header.start' }));
  expect(state.run).toHaveBeenCalledTimes(1);
});
it('shows two distinct arrival indicators, lets the user choose and renders reminder text safely', () => {
  render(<WorldDeviceControls {...props} />);
  act(() => {
    state.options.onSmsReceived?.(sms);
    state.options.onNotification?.({
      id: 'r',
      type: 'reminder',
      reminder_id: 'r',
      content: '<img src=x onerror=alert(1)>',
      timestamp: new Date(),
      read: false,
    });
  });
  fireEvent.click(screen.getByRole('button', { name: 'Phone 1 1' }));
  expect(screen.getByRole('button', { name: 'sms.new_received' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'world.device.reminder' }));
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
  expect(document.querySelector('img')).toBeNull();
  expect(props.onActivity).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'reminders.settings.title' }));
  expect(props.onActivity).toHaveBeenCalledExactlyOnceWith({ kind: 'native', token: 'reminders' });
});
it('forgets another account inbox and refuses retained notification callbacks after replacement', () => {
  const view = render(<WorldDeviceControls {...props} />);
  act(() => state.options.onSmsReceived?.(sms));
  const stale = state.options.onSmsReceived;
  const next = '3fa13afc-e569-4f66-9e1c-8913e601da15';
  state.user = makeUser({ id: next, is_active: true });
  view.rerender(<WorldDeviceControls {...props} ownerId={next} />);
  act(() => stale?.(sms));
  expect(screen.getByRole('button', { name: 'Phone 0 0' })).toBeVisible();
  view.unmount();
  act(() => state.options.onSmsReceived?.(sms));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('opens the native SMS workspace without needing a received notification', () => {
  render(<WorldDeviceControls {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Phone 0 0' }));
  fireEvent.click(screen.getByRole('button', { name: 'sms.archive' }));
  expect(props.onActivity).toHaveBeenCalledExactlyOnceWith({ kind: 'workspace', id: 'sms' });
});

it('hands proactive notices to the world presenter and fences stale callbacks on account replacement', () => {
  const onProactive = vi.fn();
  const view = render(<WorldDeviceControls {...props} onProactive={onProactive} />);
  const notice = {
    id: 'opening',
    type: 'proactive_discussion' as const,
    content: 'Private opening',
    timestamp: new Date(),
    read: false,
  };
  act(() => state.options.onNotification?.(notice));
  expect(onProactive).toHaveBeenCalledTimes(1);
  const stale = state.options.onNotification;
  const next = '3fa13afc-e569-4f66-9e1c-8913e601da15';
  state.user = makeUser({ id: next, is_active: true });
  view.rerender(<WorldDeviceControls {...props} ownerId={next} onProactive={onProactive} />);
  act(() => stale?.(notice));
  expect(onProactive).toHaveBeenCalledTimes(1);
});
