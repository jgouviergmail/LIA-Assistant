import { act, renderHook } from '@testing-library/react';
import { expect, it } from 'vitest';
import { useWorldActivityState } from '../useWorldActivityState';

it('keeps bounded typed payload history and discards dashboard state when the seat changes', () => {
  const { result, rerender } = renderHook(({ seatKey }) => useWorldActivityState(seatKey), {
    initialProps: { seatKey: 'seat-one' as string | null },
  });
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  expect(result.current.dashboardStarted).toBe(true);
  act(() => result.current.navigate('lia', { draft: 'Hello Alice' }));
  expect(result.current.history).toEqual([{ selection: 'world-dashboard' }]);
  act(() => result.current.back());
  expect(result.current.entry.selection).toBe('world-dashboard');
  act(() => result.current.close());
  expect(result.current.dashboardStarted).toBe(true);
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  const obsoleteNavigate = result.current.navigate;
  rerender({ seatKey: null });
  expect(result.current.entry.selection).toBeNull();
  expect(result.current.dashboardStarted).toBe(false);
  rerender({ seatKey: 'seat-one' });
  expect(result.current.dashboardStarted).toBe(false);
  act(() => obsoleteNavigate('lia', { draft: 'Obsolete seating' }));
  expect(result.current.entry.selection).toBeNull();
  act(() => result.current.activate({ selection: 'catalogue' }));
  for (let i = 0; i < 20; i++) {
    act(() => result.current.navigate(i % 2 ? 'lia' : 'world-workboard', { draft: 'Draft ' + i }));
  }
  expect(result.current.history).toHaveLength(16);
  act(() => result.current.back());
  expect(result.current.entry.draft).toBe('Draft 18');
});
it('a completion can close only the activity that still owns it', () => {
  const { result } = renderHook(() => useWorldActivityState(null));
  act(() => result.current.activate({ selection: 'world-avatar' }));
  act(() => result.current.activate({ selection: 'catalogue' }));
  act(() => result.current.complete('world-avatar'));
  expect(result.current.entry.selection).toBe('catalogue');
  act(() => result.current.complete('catalogue'));
  expect(result.current.entry.selection).toBeNull();
});
it('refuses a dashboard without a current seat and removes its history while preserving another active workspace', () => {
  const { result, rerender } = renderHook(({ seatKey }) => useWorldActivityState(seatKey), {
    initialProps: { seatKey: null as string | null },
  });
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  act(() => result.current.navigate('world-dashboard'));
  expect(result.current.entry.selection).toBeNull();
  expect(result.current.dashboardStarted).toBe(false);
  act(() => result.current.back());
  expect(result.current.entry.selection).toBe('catalogue');
  rerender({ seatKey: 'table' });
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  act(() => result.current.navigate('world-sms', { smsMessageId: 'private-sms' }));
  act(() => result.current.navigate('world-sms', { smsMessageId: 'next-sms' }));
  expect(result.current.history).toHaveLength(1);
  const oldClose = result.current.close;
  rerender({ seatKey: null });
  expect(result.current.history).toEqual([]);
  expect(result.current.entry).toEqual({ selection: 'world-sms', smsMessageId: 'next-sms' });
  act(() => oldClose());
  expect(result.current.entry.selection).toBe('world-sms');
});
it('closes the open activity on a loss of authority but keeps the seated dashboard retained', () => {
  const { result, rerender } = renderHook(
    ({ enabled }) => useWorldActivityState('seat-one', enabled),
    { initialProps: { enabled: true } }
  );
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  act(() => result.current.close());
  act(() => result.current.activate({ selection: 'catalogue' }));
  act(() => result.current.navigate('lia', { draft: 'Kept only while enabled' }));
  const obsolete = result.current.navigate;
  rerender({ enabled: false });
  expect(result.current.entry).toEqual({ selection: null });
  expect(result.current.history).toEqual([]);
  expect(result.current.dashboardStarted).toBe(true);
  // A transition captured before the loss can never reopen anything.
  act(() => obsolete('world-workboard'));
  expect(result.current.entry.selection).toBeNull();
  rerender({ enabled: true });
  expect(result.current.entry.selection).toBeNull();
  expect(result.current.dashboardStarted).toBe(true);
  act(() => result.current.activate({ selection: 'world-dashboard' }));
  expect(result.current.entry.selection).toBe('world-dashboard');
});
