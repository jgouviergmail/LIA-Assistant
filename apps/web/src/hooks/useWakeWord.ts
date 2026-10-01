'use client';

/**
 * The wake word in a component (ADR-329): a `WakeListener` for the life of the
 * component, listening in the interface's language while `enabled`.
 *
 * A language with no model, or a browser without the runtime, is
 * `unavailable` and never asks for the microphone — the caller keeps its
 * button. A refused microphone is exposed as `error` (cleared by the next
 * successful listen). `handOff` gives the live stream to the recording that
 * follows a detection; the caller then disables the hook until it wants the
 * phrase again. A spoken command the model ships (« Stop ») reaches
 * `onCommand`, under the same listening as the phrase.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import type { WakeCommand } from '@/lib/audio/wake-word/commands';
import { WakeListener, type WakeListenerState } from '@/lib/audio/wake-word/listener';
import { wakeLanguageOf } from '@/lib/audio/wake-word/manifest';
import { isWakeWordSupported } from '@/lib/audio/wake-word/support';

/** What the browser offers does not change during a page's life: nothing to subscribe to. */
const noSubscription = () => () => undefined;
/** The server has no browser runtime: it renders `unavailable`, and hydration agrees. */
const notOnServer = () => false;

export interface UseWakeWordOptions {
  /** The interface language (any regional variant): its base code picks the model. */
  language: string;
  /** Listen while true; the microphone is released while false. */
  enabled: boolean;
  onDetected: () => void;
  /** A spoken command was heard; the latest callback is the one called. */
  onCommand?: (command: WakeCommand) => void;
}

export interface UseWakeWord {
  state: WakeListenerState;
  /** The phrase the loaded model listens for (null until one is loaded). */
  phrase: string | null;
  /** The spoken commands the loaded model ships (none until one is loaded). */
  commands: WakeCommand[];
  /** The browser's refusal of the microphone, if the last listen met one. */
  error: Error | null;
  handOff: () => Promise<MediaStream | null>;
}

export function useWakeWord({
  language,
  enabled,
  onDetected,
  onCommand,
}: UseWakeWordOptions): UseWakeWord {
  const [state, setState] = useState<WakeListenerState>('idle');
  const [phrase, setPhrase] = useState<string | null>(null);
  const [commands, setCommands] = useState<WakeCommand[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const listenerRef = useRef<WakeListener | null>(null);
  const onDetectedRef = useRef(onDetected);
  const onCommandRef = useRef(onCommand);
  const supported = useSyncExternalStore(noSubscription, isWakeWordSupported, notOnServer);
  const wakeLanguage = wakeLanguageOf(language);

  useEffect(() => {
    onDetectedRef.current = onDetected;
    onCommandRef.current = onCommand;
  }, [onDetected, onCommand]);

  useEffect(() => {
    if (!supported) return;
    const listener = new WakeListener({
      onDetected: () => onDetectedRef.current(),
      onCommand: command => onCommandRef.current?.(command),
      onStateChange: next => {
        setState(next);
        setPhrase(listener.phrase);
        setCommands(listener.commands);
      },
    });
    listenerRef.current = listener;
    return () => {
      listenerRef.current = null;
      void listener.dispose();
    };
  }, [supported]);

  useEffect(() => {
    const listener = listenerRef.current;
    if (!listener) return;
    if (!enabled || !wakeLanguage) {
      void listener.pause();
      return;
    }
    listener.listen(wakeLanguage).then(
      () => setError(null),
      (reason: unknown) => setError(reason instanceof Error ? reason : new Error(String(reason)))
    );
  }, [enabled, wakeLanguage, supported]);

  const handOff = useCallback(
    async () => (listenerRef.current ? listenerRef.current.handOff() : null),
    []
  );

  const usable = supported && wakeLanguage !== null;
  return {
    state: usable ? state : 'unavailable',
    phrase: usable ? phrase : null,
    commands: usable ? commands : [],
    error,
    handOff,
  };
}
