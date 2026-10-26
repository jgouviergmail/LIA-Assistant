'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Point } from './types';

const KEYS: Readonly<Record<string, Point>> = {
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
};
export function joystickVector(x: number, y: number): Point {
  const length = Math.hypot(x, y);
  if (!Number.isFinite(length) || length <= 7) return { x: 0, y: 0 };
  // Match the game's eight headings, including the two projected floor axes.
  const angle = Math.round(Math.atan2(y, x) / (Math.PI / 4)) * (Math.PI / 4);
  const dx = Math.round(Math.cos(angle)),
    dy = Math.round(Math.sin(angle)) || 0;
  const n = Math.hypot(dx, dy);
  return { x: dx / n, y: dy / n };
}
interface Props {
  label: string;
  onHold(source: string, point: Point): void;
  onRelease(source: string): void;
}
export function WorldJoystick({ label, onHold, onRelease }: Props) {
  const contact = useRef<number | null>(null);
  const origin = useRef<Point>({ x: 0, y: 0 });
  const [thumb, setThumb] = useState<Point>({ x: 0, y: 0 });
  const stop = useCallback(() => {
    contact.current = null;
    setThumb({ x: 0, y: 0 });
    onRelease('joystick');
  }, [onRelease]);
  useEffect(() => {
    const hide = () => {
      if (document.hidden) stop();
    };
    window.addEventListener('blur', stop);
    document.addEventListener('visibilitychange', hide);
    return () => {
      window.removeEventListener('blur', stop);
      document.removeEventListener('visibilitychange', hide);
      onRelease('joystick');
    };
  }, [stop, onRelease]);
  return (
    <button
      type="button"
      className="world-joystick"
      aria-label={label}
      onPointerDown={event => {
        if (contact.current !== null || event.button !== 0) return;
        event.preventDefault();
        contact.current = event.pointerId;
        origin.current = { x: event.clientX, y: event.clientY };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        if (contact.current !== event.pointerId) return;
        const dx = event.clientX - origin.current.x,
          dy = event.clientY - origin.current.y;
        const direction = joystickVector(dx, dy);
        const distance = Math.min(24, Math.hypot(dx, dy));
        setThumb({ x: direction.x * distance, y: direction.y * distance });
        onHold('joystick', direction);
      }}
      onPointerUp={event => {
        if (contact.current === event.pointerId) stop();
      }}
      onPointerCancel={event => {
        if (contact.current === event.pointerId) stop();
      }}
      onLostPointerCapture={event => {
        if (contact.current === event.pointerId) stop();
      }}
      onBlur={stop}
      onKeyDown={event => {
        const direction = KEYS[event.code];
        if (direction) {
          event.preventDefault();
          onHold('joystick', direction);
          setThumb({ x: direction.x * 24, y: direction.y * 24 });
        }
      }}
      onKeyUp={event => {
        if (KEYS[event.code]) {
          event.preventDefault();
          stop();
        }
      }}
    >
      <span className="world-joystick-ring" aria-hidden="true" />
      <span
        className="world-joystick-thumb"
        aria-hidden="true"
        style={{ transform: `translate(${thumb.x}px, ${thumb.y}px)` }}
      />
    </button>
  );
}
