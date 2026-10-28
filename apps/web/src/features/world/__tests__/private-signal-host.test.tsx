import { renderHook } from '@testing-library/react';
import { createRef } from 'react';
import { expect, it, vi } from 'vitest';
import { useWorldSignalHost } from '../useWorldSignalHost';
import type { WorldPrivateSignalsControl } from '../useWorldPrivateSignals';
import type { WorldFunctionHandle } from '../WorldFunctionControls';
import type { WorldDeviceHandle } from '../WorldDeviceControls';
import { WORLD } from '../definition';
const control = (signals: WorldPrivateSignalsControl['signals']): WorldPrivateSignalsControl => ({
  connected: true,
  signals,
  presentation: [],
  entries: [],
  authorized: true,
  smsEnabled: true,
  remindersUncertain: false,
  acknowledge: vi.fn(),
  read: () => null,
  lifetime: { ownerId: 'owner' },
});

it('opens the exact needs-me ticket and falls back to a trusted native workspace on unavailable data', () => {
  const openDestination = vi.fn(() => true);
  const openScene = vi.fn(() => true);
  const functions = createRef<WorldFunctionHandle>();
  const devices = createRef<WorldDeviceHandle>();
  functions.current = { openDestination, openPlace: () => true, openScene, canOpen: () => true };
  const desk = WORLD.props.find(
    prop => prop.kind === 'writingdesk' && prop.activity === 'workboard'
  );
  if (!desk) throw new Error('Missing authored workboard desk');
  const ready = control([
    {
      propId: desk.id,
      kind: 'workboard',
      count: 1,
      status: 'ready',
      target: { kind: 'workboard', ticketId: 'current-ticket' },
    },
  ]);
  const { result, rerender } = renderHook(
    ({ current }) => useWorldSignalHost(current, functions, devices),
    { initialProps: { current: ready } }
  );
  expect(result.current(desk.id)).toBe(true);
  expect(openDestination).toHaveBeenCalledWith({
    kind: 'workboard',
    filters: {},
    ticketId: 'current-ticket',
  });
  rerender({
    current: control([
      { propId: desk.id, kind: 'workboard', count: null, status: 'unavailable', target: null },
    ]),
  });
  expect(result.current(desk.id)).toBe(true);
  expect(openScene).toHaveBeenCalledWith({ kind: 'workspace', id: 'workboard' });
  expect(openDestination).toHaveBeenCalledOnce();
  functions.current = null;
  expect(result.current(desk.id)).toBe(false);
  rerender({
    current: control([
      {
        propId: 'unknown-prop',
        kind: 'workboard',
        count: null,
        status: 'unavailable',
        target: null,
      },
    ]),
  });
  expect(result.current('unknown-prop')).toBe(false);
});
it('late-binds native targets and only acknowledges an accepted gallery', () => {
  const openDestination = vi.fn(() => true);
  const functions = createRef<WorldFunctionHandle>();
  const devices = createRef<WorldDeviceHandle>();
  const openNotice = vi.fn(() => true);
  functions.current = {
    openDestination,
    openPlace: () => true,
    openScene: () => true,
    canOpen: () => true,
  };
  devices.current = { openNotice };
  const first = control([
    {
      propId: 'phone',
      kind: 'sms',
      count: 1,
      status: 'ready',
      target: { kind: 'notice', noticeKey: 'private-key' },
    },
  ]);
  const { result, rerender } = renderHook(
    ({ current }) => useWorldSignalHost(current, functions, devices),
    { initialProps: { current: first } }
  );
  const activate = result.current;
  expect(activate('missing')).toBeNull();
  expect(activate('phone')).toBe(true);
  expect(openNotice).toHaveBeenCalledWith('private-key');
  const next = control([
    {
      propId: 'easel',
      kind: 'images',
      count: 2,
      status: 'ready',
      target: { kind: 'gallery', tab: 'images' },
    },
  ]);
  rerender({ current: next });
  expect(result.current).toBe(activate);
  expect(activate('phone')).toBeNull();
  openDestination.mockReturnValueOnce(false);
  expect(activate('easel')).toBe(false);
  expect(next.acknowledge).not.toHaveBeenCalled();
  expect(activate('easel')).toBe(true);
  expect(openDestination).toHaveBeenLastCalledWith({ kind: 'gallery', tab: 'images' });
  expect(next.acknowledge).toHaveBeenCalledWith('easel');
  functions.current = null;
  expect(activate('easel')).toBe(false);
  rerender({ current: first });
  devices.current = null;
  expect(activate('phone')).toBe(false);
  rerender({ current: control([]) });
  expect(activate('easel')).toBeNull();
});
