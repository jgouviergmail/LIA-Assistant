/**
 * useWakeWord — the wake listener's lifecycle in a component (ADR-329).
 *
 *  - it listens in the interface's language while enabled, and pauses when not;
 *  - a language with no model, or a browser without the runtime, is
 *    `unavailable` and never asks for the microphone;
 *  - a refused microphone is exposed as an error, cleared by the next success;
 *  - the latest `onDetected` is called, and unmounting disposes the listener.
 */
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { FakeListener, support } = vi.hoisted(() => {
  type State = 'idle' | 'loading' | 'listening' | 'unavailable';
  class FakeListener {
    static instances: FakeListener[] = [];
    listen = vi.fn(async (_language: string): Promise<State> => {
      this.options.onStateChange?.('listening');
      return 'listening';
    });
    pause = vi.fn(async () => undefined);
    handOff = vi.fn(async () => ({ id: 'stream' }) as unknown as MediaStream);
    dispose = vi.fn(async () => undefined);
    phrase: string | null = 'Dis LIA';
    commands: string[] = ['stop'];
    constructor(
      readonly options: {
        onDetected: () => void;
        onCommand?: (command: string) => void;
        onStateChange?: (state: State) => void;
      }
    ) {
      FakeListener.instances.push(this);
    }
  }
  return { FakeListener, support: { supported: true } };
});

vi.mock('@/lib/audio/wake-word/listener', () => ({ WakeListener: FakeListener }));
vi.mock('@/lib/audio/wake-word/support', () => ({
  isWakeWordSupported: () => support.supported,
}));

import { useWakeWord } from '../useWakeWord';

const last = () => FakeListener.instances.at(-1)!;

describe('useWakeWord', () => {
  beforeEach(() => {
    FakeListener.instances = [];
    support.supported = true;
  });

  it('listens in the interface language while enabled and reports the phrase', async () => {
    const { result } = renderHook(() =>
      useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn() })
    );
    await waitFor(() => expect(result.current.state).toBe('listening'));
    expect(last().listen).toHaveBeenCalledWith('fr');
    expect(result.current.phrase).toBe('Dis LIA');
  });

  it('maps a regional interface code to its language model', async () => {
    renderHook(() => useWakeWord({ language: 'fr-CA', enabled: true, onDetected: vi.fn() }));
    await waitFor(() => expect(last().listen).toHaveBeenCalledWith('fr'));
  });

  it('pauses while disabled and listens again when re-enabled', async () => {
    const { rerender } = renderHook(
      ({ enabled }) => useWakeWord({ language: 'fr', enabled, onDetected: vi.fn() }),
      { initialProps: { enabled: false } }
    );
    await waitFor(() => expect(last().pause).toHaveBeenCalled());
    expect(last().listen).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() => expect(last().listen).toHaveBeenCalledWith('fr'));
    rerender({ enabled: false });
    await waitFor(() => expect(last().pause).toHaveBeenCalledTimes(2));
  });

  it('follows a language change', async () => {
    const { rerender } = renderHook(
      ({ language }) => useWakeWord({ language, enabled: true, onDetected: vi.fn() }),
      { initialProps: { language: 'fr' } }
    );
    await waitFor(() => expect(last().listen).toHaveBeenCalledWith('fr'));
    // An interface language no model ships for stops the listening ...
    rerender({ language: 'it' });
    await waitFor(() => expect(last().pause).toHaveBeenCalled());
    expect(last().listen).not.toHaveBeenCalledWith('it');
    // ... and coming back to one that has a model listens again.
    rerender({ language: 'fr-BE' });
    await waitFor(() => expect(last().listen).toHaveBeenCalledTimes(2));
    expect(last().listen).toHaveBeenLastCalledWith('fr');
  });

  it('is unavailable, without asking for the microphone, in a language with no model', async () => {
    const { result } = renderHook(() =>
      useWakeWord({ language: 'pt', enabled: true, onDetected: vi.fn() })
    );
    expect(result.current.state).toBe('unavailable');
    expect(result.current.phrase).toBeNull();
    await waitFor(() => expect(last().pause).toHaveBeenCalled());
    expect(last().listen).not.toHaveBeenCalled();
  });

  it('is unavailable, and builds nothing, in a browser without the runtime', async () => {
    support.supported = false;
    const { result } = renderHook(() =>
      useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn() })
    );
    expect(result.current.state).toBe('unavailable');
    expect(FakeListener.instances).toHaveLength(0);
    await expect(result.current.handOff()).resolves.toBeNull();
  });

  it('renders unavailable on the server, so the first client render hydrates the same', () => {
    // The browser check is true here (jsdom + the mock); the SERVER snapshot
    // must still say no runtime, or the badge text would differ at hydration.
    const Probe = () => useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn() }).state;
    expect(renderToString(createElement(Probe))).toBe('unavailable');
  });

  it('exposes a refused microphone, and clears it on the next success', async () => {
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const { result, rerender } = renderHook(
      ({ enabled }) => useWakeWord({ language: 'fr', enabled, onDetected: vi.fn() }),
      { initialProps: { enabled: true } }
    );
    await waitFor(() => expect(last().listen).toHaveBeenCalled());
    last().listen.mockRejectedValueOnce(denied);
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.error).toBe(denied));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.error).toBeNull());
  });

  it('calls the latest onDetected', async () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ onDetected }) => useWakeWord({ language: 'fr', enabled: true, onDetected }),
      { initialProps: { onDetected: first } }
    );
    await waitFor(() => expect(last().listen).toHaveBeenCalled());
    rerender({ onDetected: second });
    act(() => last().options.onDetected());
    expect(second).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });

  it('reports the spoken commands the model ships, and calls the latest onCommand', async () => {
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender } = renderHook(
      ({ onCommand }) =>
        useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn(), onCommand }),
      { initialProps: { onCommand: first } }
    );
    await waitFor(() => expect(result.current.commands).toEqual(['stop']));
    rerender({ onCommand: second });
    act(() => last().options.onCommand?.('stop'));
    expect(second).toHaveBeenCalledWith('stop');
    expect(first).not.toHaveBeenCalled();
  });

  it('offers no command where the wake word is unavailable', async () => {
    support.supported = false;
    const { result } = renderHook(() =>
      useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn(), onCommand: vi.fn() })
    );
    expect(result.current.commands).toEqual([]);
  });

  it('hands the live stream over, and disposes the listener on unmount', async () => {
    const { result, unmount } = renderHook(() =>
      useWakeWord({ language: 'fr', enabled: true, onDetected: vi.fn() })
    );
    await waitFor(() => expect(result.current.state).toBe('listening'));
    await expect(result.current.handOff()).resolves.toEqual({ id: 'stream' });
    const listener = last();
    unmount();
    expect(listener.dispose).toHaveBeenCalled();
  });
});
