import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { joystickVector, WorldJoystick } from '../WorldJoystick';

describe('touch joystick', () => {
  it('has a dead zone, follows the finger and bounds diagonal speed', () => {
    expect(joystickVector(2, 2)).toEqual({ x: 0, y: 0 });
    expect(joystickVector(18, 0)).toEqual({ x: 1, y: 0 });
    expect(joystickVector(0.001, -18)).toEqual({ x: 0, y: -1 });
    const diagonal = joystickVector(100, -100);
    expect(Math.hypot(diagonal.x, diagonal.y)).toBeCloseTo(1);
    expect(diagonal.x).toBeGreaterThan(0);
    expect(diagonal.y).toBeLessThan(0);
    expect(joystickVector(NaN, Infinity)).toEqual({ x: 0, y: 0 });
  });
  it('owns one contact and releases movement on cancellation, blur and unmount', () => {
    const onHold = vi.fn(),
      onRelease = vi.fn();
    const view = render(<WorldJoystick label="Move" onHold={onHold} onRelease={onRelease} />);
    const pad = screen.getByRole('button', { name: 'Move' });
    pad.setPointerCapture = vi.fn();
    pad.hasPointerCapture = () => false;
    fireEvent.pointerDown(pad, { pointerId: 1, button: 0, clientX: 44, clientY: 44 });
    fireEvent.pointerMove(pad, { pointerId: 1, clientX: 80, clientY: 44 });
    expect(onHold).toHaveBeenCalledWith('joystick', { x: 1, y: 0 });
    fireEvent.pointerDown(pad, { pointerId: 2, button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerUp(pad, { pointerId: 2 });
    expect(onRelease).not.toHaveBeenCalled();
    fireEvent.pointerCancel(pad, { pointerId: 1 });
    expect(onRelease).toHaveBeenCalledWith('joystick');
    fireEvent.keyDown(pad, { code: 'ArrowUp' });
    expect(onHold).toHaveBeenLastCalledWith('joystick', { x: 0, y: -1 });
    fireEvent.blur(window);
    expect(onRelease).toHaveBeenCalledTimes(2);
    view.unmount();
    expect(onRelease).toHaveBeenCalledTimes(3);
  });
  it('ignores stray contacts and stops on loss of capture or a hidden document', () => {
    const onHold = vi.fn(),
      onRelease = vi.fn();
    const view = render(<WorldJoystick label="Move" onHold={onHold} onRelease={onRelease} />);
    const pad = screen.getByRole('button', { name: 'Move' });
    pad.setPointerCapture = vi.fn();
    fireEvent.pointerMove(pad, { pointerId: 5, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(pad, { pointerId: 5, button: 2 });
    fireEvent.pointerMove(pad, { pointerId: 5, clientX: 100, clientY: 100 });
    expect(onHold).not.toHaveBeenCalled();
    fireEvent.pointerDown(pad, { pointerId: 1, button: 0, clientX: 44, clientY: 44 });
    fireEvent.pointerMove(pad, { pointerId: 1, clientX: 45, clientY: 44 });
    expect(onHold).toHaveBeenLastCalledWith('joystick', { x: 0, y: 0 });
    fireEvent.lostPointerCapture(pad, { pointerId: 2 });
    expect(onRelease).not.toHaveBeenCalled();
    fireEvent.lostPointerCapture(pad, { pointerId: 1 });
    expect(onRelease).toHaveBeenCalledTimes(1);
    fireEvent.pointerDown(pad, { pointerId: 2, button: 0, clientX: 44, clientY: 44 });
    fireEvent.pointerUp(pad, { pointerId: 2 });
    fireEvent.keyDown(pad, { code: 'ArrowLeft' });
    fireEvent.keyUp(pad, { code: 'ArrowLeft' });
    fireEvent.keyDown(pad, { code: 'KeyX' });
    fireEvent.keyUp(pad, { code: 'KeyX' });
    expect(onHold).toHaveBeenLastCalledWith('joystick', { x: -1, y: 0 });
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    fireEvent(document, new Event('visibilitychange'));
    expect(onRelease).toHaveBeenCalledTimes(3);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    fireEvent(document, new Event('visibilitychange'));
    fireEvent.blur(pad);
    expect(onRelease).toHaveBeenCalledTimes(5);
    view.unmount();
    vi.restoreAllMocks();
  });
});
