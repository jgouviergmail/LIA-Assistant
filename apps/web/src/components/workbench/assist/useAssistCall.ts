'use client';

/**
 * One call to LIA from a screen (ADR-372).
 *
 * One at a time: a newer call replaces the one on its way, and leaving, or closing the panel, stops
 * it. It belongs to what it was asked about (`scope`): moving to another thing stops it and shows
 * nothing of it. A late answer never lands on what moved on. Nothing is asked again by itself: a
 * model costs, and a failure is the person's to retry (ADR-221).
 */
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

import apiClient from '@/lib/api-client';
import { workbenchRefusal, type WorkbenchRefusal } from '@/lib/workbench/errors';

/** What a click may wait for: under the 90 s the web proxy allows, so the page says it first. */
const ASSIST_TIMEOUT_MS = 85_000;

export type AssistState<T> =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; value: T }
  | { status: 'failed'; refusal: WorkbenchRefusal | null };

export interface AssistCall<T> {
  state: AssistState<T>;
  /** Asks; resolves to the answer, or to null when there is none to act on. */
  run: (path: string, body: object) => Promise<T | null>;
  /** Stops what is on its way and forgets what was answered. */
  stop: () => void;
  /** Asks what was asked last. */
  retry: () => Promise<T | null>;
}

const IDLE = { status: 'idle' } as const;

/**
 * An answer can take long enough for the person to change what it was about: what the field holds
 * then is what decides whether it may land.
 *
 * @param value - What the screen holds.
 * @returns What it holds now, for whoever waited.
 */
export function useLatest<T>(value: T): RefObject<T> {
  const latest = useRef(value);
  useEffect(() => {
    latest.current = value;
  });
  return latest;
}

/**
 * @param scope - What the call is about (a message's id); another one starts from nothing.
 * @returns The call, and what became of it.
 */
export function useAssistCall<T>(scope: string | null = null): AssistCall<T> {
  const [held, setHeld] = useState<{ scope: string | null; state: AssistState<T> }>({
    scope,
    state: IDLE,
  });
  const onItsWay = useRef<AbortController | null>(null);
  const last = useRef<{ path: string; body: object } | null>(null);

  const stop = useCallback(() => {
    onItsWay.current?.abort();
    onItsWay.current = null;
    setHeld(previous => ({ ...previous, state: IDLE }));
  }, []);

  useEffect(
    () => () => {
      onItsWay.current?.abort();
      onItsWay.current = null;
      // Coming back to it finds it left, never a wait nobody is answering any more.
      setHeld(previous =>
        previous.scope === scope && previous.state.status === 'running'
          ? { scope, state: IDLE }
          : previous
      );
    },
    [scope]
  );

  const run = useCallback(
    async (path: string, body: object): Promise<T | null> => {
      onItsWay.current?.abort();
      const controller = new AbortController();
      onItsWay.current = controller;
      last.current = { path, body };
      setHeld({ scope, state: { status: 'running' } });
      try {
        const value = await apiClient.post<T>(path, body, {
          signal: controller.signal,
          timeout: ASSIST_TIMEOUT_MS,
        });
        if (onItsWay.current !== controller) return null;
        onItsWay.current = null;
        setHeld({ scope, state: { status: 'done', value } });
        return value;
      } catch (error: unknown) {
        if (onItsWay.current !== controller) return null;
        onItsWay.current = null;
        setHeld({ scope, state: { status: 'failed', refusal: workbenchRefusal(error) } });
        return null;
      }
    },
    [scope]
  );

  const retry = useCallback(
    async () => (last.current ? run(last.current.path, last.current.body) : null),
    [run]
  );

  return { state: held.scope === scope ? held.state : IDLE, run, stop, retry };
}
