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
