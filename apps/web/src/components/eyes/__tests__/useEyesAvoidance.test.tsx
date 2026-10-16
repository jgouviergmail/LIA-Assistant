import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useEyesAvoidance } from '../useEyesAvoidance';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  document.body.replaceChildren();
});

function box(left: number, top: number, width: number, height: number) {
  return new DOMRect(left, top, width, height);
}

describe('companion control avoidance lifecycle', () => {
  it('reacts to a newly mounted action and releases its pending observation on unmount', async () => {
    vi.useFakeTimers();
    const widget = document.createElement('div');
    widget.getBoundingClientRect = () => box(246, 500, 120, 140);
    document.body.append(widget);
    const root = { current: widget };
    const view = renderHook(() => useEyesAvoidance(root, true));
    await act(() => vi.advanceTimersByTimeAsync(30));
    expect(view.result.current.position).toEqual({ left: 246, top: 500 });
    const action = document.createElement('button');
    action.getBoundingClientRect = () => box(200, 480, 190, 220);
    document.body.append(action);
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(view.result.current.position?.left).toBeGreaterThanOrEqual(398);
    window.dispatchEvent(new Event('resize'));
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('protects the header from an absolute toolbar beyond the body frame', async () => {
    vi.useFakeTimers();
    const header = document.createElement('header');
    header.className = 'lia-dashboard-header';
    header.getBoundingClientRect = () => box(0, 0, innerWidth, 80);
    const widget = document.createElement('div');
    widget.getBoundingClientRect = () => box(100, 100, 120, 140);
    const toolbar = document.createElement('div');
    toolbar.className = 'lia-eyes-toolbar';
    toolbar.getBoundingClientRect = () => box(100, 60, 120, 44);
    widget.append(toolbar);
    document.body.append(header, widget);
    const root = { current: widget };
    const view = renderHook(() => useEyesAvoidance(root, true));
    await act(() => vi.advanceTimersByTimeAsync(30));
    expect(view.result.current.position?.top).toBeGreaterThanOrEqual(120);
    view.unmount();
  });
});

it('keeps a saved position transient and falls back to a compact presence when only 44px fit', async () => {
  vi.useFakeTimers();
  const widget = document.createElement('div');
  widget.getBoundingClientRect = () => box(10, 100, 120, 140);
  const obstacle = document.createElement('input');
  obstacle.getBoundingClientRect = () => box(0, 120, innerWidth, innerHeight - 120);
  document.body.append(widget, obstacle);
  const preferred = { left: 10, top: 100 };
  const root = { current: widget };
  const view = renderHook(() => useEyesAvoidance(root, true, preferred));
  await act(() => vi.advanceTimersByTimeAsync(30));
  expect(view.result.current.compact).toBe(true);
  expect(view.result.current.position).not.toBeNull();
  expect((view.result.current.position?.top ?? 0) + 44).toBeLessThanOrEqual(112);
  expect(preferred).toEqual({ left: 10, top: 100 });
  obstacle.remove();
  await act(() => vi.advanceTimersByTimeAsync(200));
  expect(view.result.current.compact).toBe(false);
  expect(view.result.current.position).toEqual(preferred);
});

it('never folds when compact is refused: no free spot leaves the face whole and click-through', async () => {
  vi.useFakeTimers();
  const widget = document.createElement('div');
  widget.getBoundingClientRect = () => box(10, 100, 120, 140);
  const obstacle = document.createElement('input');
  obstacle.getBoundingClientRect = () => box(0, 120, innerWidth, innerHeight - 120);
  document.body.append(widget, obstacle);
  const preferred = { left: 10, top: 100 };
  const root = { current: widget };
  const view = renderHook(() => useEyesAvoidance(root, true, preferred, { compact: 'never' }));
  await act(() => vi.advanceTimersByTimeAsync(30));
  expect(view.result.current).toEqual({
    position: null,
    blocked: true,
    compact: false,
    compactSize: null,
  });
  obstacle.remove();
  await act(() => vi.advanceTimersByTimeAsync(200));
  expect(view.result.current.blocked).toBe(false);
  expect(view.result.current.position).toEqual(preferred);
});

it('reserves the whole mobile toolbar in compact mode without covering an input or header', async () => {
  vi.useFakeTimers();
  const header = document.createElement('header');
  header.className = 'lia-dashboard-header';
  header.getBoundingClientRect = () => box(0, 0, innerWidth, 80);
  const widget = document.createElement('div');
  widget.getBoundingClientRect = () => box(10, 100, 200, 180);
  const toolbar = document.createElement('div');
  toolbar.className = 'lia-eyes-toolbar';
  toolbar.getBoundingClientRect = () => box(64, 88, 92, 44);
  widget.append(toolbar);
  const input = document.createElement('input');
  input.getBoundingClientRect = () => box(0, 160, innerWidth, innerHeight - 160);
  document.body.append(header, widget, input);
  const root = { current: widget };
  const view = renderHook(() => useEyesAvoidance(root, true, { left: 10, top: 100 }));
  await act(() => vi.advanceTimersByTimeAsync(30));
  expect(view.result.current.compact).toBe(true);
  expect(view.result.current.compactSize).toEqual({ width: 92, height: 56 });
  expect(view.result.current.position?.top).toBeGreaterThanOrEqual(80);
  expect((view.result.current.position?.top ?? 0) + 56).toBeLessThanOrEqual(152);
  expect(view.result.current.blocked).toBe(false);
});
