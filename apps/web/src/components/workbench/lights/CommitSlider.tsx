'use client';

/**
 * CommitSlider — a range that is SENT when it is released (ADR-369, mock-ups
 * « Lumières »: « a setting applies when you release the slider »).
 *
 * While it moves, the slider only draws the value it is at (React's `onChange`
 * follows every `input`); the native `change` event — fired when a pointer or
 * a touch releases — is what commits. A key is the exception: the browser
 * fires `change` at every step, so a key held down commits once, when it is
 * released (or when the slider loses the focus first) — one drag by keyboard
 * is one request, never one per step against the bridge's window. The value
 * being committed is held as a draft: it stays drawn while the act runs, and
 * when the act is refused the draft is dropped, so the previous value is
 * drawn again.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { Label } from '@/components/ui/label';

export interface CommitSliderProps {
  /** Its word on the screen, and its name unless `name` says more. */
  label: string;
  /** What the ear is told, where the card around it names what the word is about. */
  name?: string;
  /** The value the bridge holds. */
  value: number;
  min: number;
  max: number;
  step?: number;
  /** The value as words (« 62 % », « 2 750 K »). */
  format: (value: number) => string;
  /** Send the released value; resolves once sent and re-read, rejects when refused. */
  onCommit: (value: number) => Promise<void>;
}

export function CommitSlider({
  label,
  name,
  value,
  min,
  max,
  step = 1,
  format,
  onCommit,
}: CommitSliderProps) {
  const id = useId();
  const slider = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<number | null>(null);
  // The value when a key went down; null while no key is held.
  const keyFrom = useRef<number | null>(null);
  const shown = draft ?? value;

  const send = useCallback(
    (released: number) => {
      setDraft(released);
      onCommit(released)
        .catch(() => undefined)
        .finally(() => setDraft(null));
    },
    [onCommit]
  );

  useEffect(() => {
    const element = slider.current;
    if (!element) return;
    const release = () => {
      if (keyFrom.current === null) send(Number(element.value));
    };
    element.addEventListener('change', release);
    return () => element.removeEventListener('change', release);
  }, [send]);

  const releaseKey = (element: HTMLInputElement) => {
    const from = keyFrom.current;
    keyFrom.current = null;
    const to = Number(element.value);
    if (from !== null && to !== from) send(to);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <Label id={`${id}-label`} htmlFor={id}>
          {label}
        </Label>
        <span className="tabular-nums text-muted-foreground" aria-hidden="true">
          {format(shown)}
        </span>
      </div>
      <input
        ref={slider}
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={shown}
        aria-label={name}
        aria-labelledby={name ? undefined : `${id}-label`}
        aria-valuetext={format(shown)}
        onChange={event => setDraft(Number(event.target.value))}
        onKeyDown={event => {
          keyFrom.current ??= Number(event.currentTarget.value);
        }}
        onKeyUp={event => releaseKey(event.currentTarget)}
        onBlur={event => releaseKey(event.currentTarget)}
        className="h-2 w-full cursor-pointer accent-primary"
      />
    </div>
  );
}
