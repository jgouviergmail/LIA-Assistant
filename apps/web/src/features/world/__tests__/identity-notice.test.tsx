import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useWorldIdentityNotice } from '../useWorldIdentityNotice';

class Channel {
  static instances: Channel[] = [];
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  postMessage = vi.fn();
  close = vi.fn();
  constructor(readonly name: string) {
    Channel.instances.push(this);
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  Channel.instances = [];
});

it('rechecks the server cookie when another world document announces itself, without exchanging an identity', () => {
  vi.stubGlobal('BroadcastChannel', Channel);
  const verify = vi.fn().mockResolvedValue(undefined);
  const hook = renderHook(() => useWorldIdentityNotice('owner-one', verify));
  const channel = Channel.instances[0];
  expect(channel.postMessage).toHaveBeenCalledExactlyOnceWith({ type: 'verify', version: 1 });
  act(() =>
    channel.onmessage?.(new MessageEvent('message', { data: { type: 'verify', version: 1 } }))
  );
  expect(verify).toHaveBeenCalledTimes(1);
  hook.rerender();
  expect(Channel.instances).toHaveLength(1);
  hook.unmount();
  expect(channel.close).toHaveBeenCalledTimes(1);
  expect(channel.onmessage).toBeNull();
});

it('ignores unrelated messages and still works in browsers without channels', () => {
  vi.stubGlobal('BroadcastChannel', Channel);
  const verify = vi.fn().mockResolvedValue(undefined);
  const hook = renderHook(() => useWorldIdentityNotice('one', verify));
  const channel = Channel.instances[0];
  for (const data of [
    null,
    'verify',
    {},
    { type: 'verify', version: 2 },
    { type: 'unrelated', version: 1 },
  ])
    act(() => channel.onmessage?.(new MessageEvent('message', { data })));
  expect(verify).not.toHaveBeenCalled();
  hook.unmount();
  vi.stubGlobal('BroadcastChannel', undefined);
  expect(() => renderHook(() => useWorldIdentityNotice('one', verify))).not.toThrow();
});
