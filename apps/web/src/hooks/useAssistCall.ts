'use client';

/**
 * One call to LIA from a screen (ADR-372).
 *
 * One at a time: a newer call replaces the one on its way, and leaving, or closing the panel, stops
 * it. It belongs to what it was asked about (`scope`): moving to another thing stops it and shows
 * nothing of it. A late answer never lands on what moved on. Nothing is asked again by itself: a
 * model costs, and a failure is the person's to retry (ADR-221).
 */
import {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from 'react';

import { AuthContext } from '@/lib/auth';
import apiClient from '@/lib/api-client';
import { ASSIST_TIMEOUT_MS } from '@/lib/workbench/assist';
import { workbenchRefusal, type WorkbenchRefusal } from '@/lib/workbench/errors';

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
export type AssistTransport<T> = (path: string, body: object, signal: AbortSignal) => Promise<T>;

export function useAssistCall<T>(
  scope: string | null = null,
  transport?: AssistTransport<T>
): AssistCall<T> {
  const auth = useContext(AuthContext);
  const owner = auth?.user?.id;
  const identity = useMemo(() => ({ scope, owner }), [scope, owner]);
  const lifetime = useRef<object | null>(null);
  const [held, setHeld] = useState<{ identity: object; state: AssistState<T> }>({
    identity,
    state: IDLE,
  });
  const onItsWay = useRef<AbortController | null>(null);
  const last = useRef<{ path: string; body: object } | null>(null);

  const stop = useCallback(() => {
    if (lifetime.current !== identity) return;
    onItsWay.current?.abort();
    onItsWay.current = null;
    last.current = null;
    setHeld(previous => ({ ...previous, state: IDLE }));
  }, [identity]);

  useLayoutEffect(() => {
    lifetime.current = identity;
    return () => {
      lifetime.current = null;
      onItsWay.current?.abort();
      onItsWay.current = null;
      last.current = null;
    };
  }, [identity]);

  const run = useCallback(
    async (path: string, body: object): Promise<T | null> => {
      if (lifetime.current !== identity) return null;
      onItsWay.current?.abort();
      const controller = new AbortController();
      onItsWay.current = controller;
      last.current = { path, body };
      setHeld({ identity, state: { status: 'running' } });
      try {
        const value = await (transport
          ? transport(path, body, controller.signal)
          : apiClient.post<T>(path, body, {
              signal: controller.signal,
              timeout: ASSIST_TIMEOUT_MS,
            }));
        if (onItsWay.current !== controller || lifetime.current !== identity) return null;
        onItsWay.current = null;
        setHeld({ identity, state: { status: 'done', value } });
        return value;
      } catch (error: unknown) {
        if (onItsWay.current !== controller || lifetime.current !== identity) return null;
        onItsWay.current = null;
        setHeld({ identity, state: { status: 'failed', refusal: workbenchRefusal(error) } });
        return null;
      }
    },
    [identity, transport]
  );

  const retry = useCallback(
    async () =>
      lifetime.current === identity && last.current
        ? run(last.current.path, last.current.body)
        : null,
    [run, identity]
  );

  return { state: held.identity === identity ? held.state : IDLE, run, stop, retry };
}
