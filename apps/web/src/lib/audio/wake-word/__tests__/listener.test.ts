/**
 * WakeListener — one microphone at the engine's rate, fed to one detector.
 *
 *  - the model is loaded BEFORE the microphone opens, and a language without a
 *    usable model never lights the microphone;
 *  - a language change reloads the model and keeps the one capture;
 *  - `pause` releases the microphone and keeps the model; `handOff` gives the
 *    live stream to the recording;
 *  - a detection reaches the caller only while listening;
 *  - calls are serialised, and `dispose` wins over a load in flight.
 */
import { describe, expect, it, vi } from 'vitest';

import type { MicCaptureOptions } from '@/lib/live/mic-capture';

import { CHUNK_SAMPLES, SAMPLE_RATE } from '../engine';
import { WakeListener, type WakeListenerState } from '../listener';
import { FakeCapture, FakeWorker } from './fakes';

function setup(options: { refuse?: Error } = {}) {
  const workers: FakeWorker[] = [];
  const captures: FakeCapture[] = [];
  const states: WakeListenerState[] = [];
  const onDetected = vi.fn();
  const onCommand = vi.fn();
  const openCapture = vi.fn(async (capture: MicCaptureOptions) => {
    if (options.refuse) throw options.refuse;
    const fake = new FakeCapture(capture);
    captures.push(fake);
    return fake;
  });
  const listener = new WakeListener({
    onDetected,
    onCommand,
    onStateChange: state => states.push(state),
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker;
    },
    openCapture,
  });
  /** Let the pending load reach the worker, then answer it. */
  const answer = async (index: number, phrase: string | null) => {
    await vi.waitFor(() => expect(workers[index]).toBeDefined());
    workers[index].answer(
      phrase === null
        ? { type: 'failed', reason: 'manifest' }
        : { type: 'ready', phrase, commands: ['stop'] }
    );
  };
  return { listener, workers, captures, states, onDetected, onCommand, openCapture, answer };
}

describe('WakeListener', () => {
  it('loads the model, then opens the microphone at the engine rate and feeds the detector', async () => {
    const { listener, workers, captures, states, onDetected, openCapture, answer } = setup();
    const listening = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await expect(listening).resolves.toBe('listening');
    expect(openCapture).toHaveBeenCalledOnce();
    expect(captures[0].options).toMatchObject({
      sampleRate: SAMPLE_RATE,
      chunkSamples: CHUNK_SAMPLES,
    });
    expect(captures[0].options.pcm).not.toBe(false);
    expect(listener.phrase).toBe('Dis LIA');
    expect(states).toEqual(['loading', 'listening']);

    const chunk = captures[0].emit();
    expect(workers[0].posted.at(-1)).toEqual({
      message: { type: 'audio', samples: chunk },
      transfer: [chunk],
    });
    workers[0].answer({ type: 'detected', score: 0.95 });
    expect(onDetected).toHaveBeenCalledOnce();
  });

  it('never opens the microphone for a language without a usable model', async () => {
    const { listener, openCapture, states, answer } = setup();
    const listening = listener.listen('de');
    await answer(0, null);
    await expect(listening).resolves.toBe('unavailable');
    expect(openCapture).not.toHaveBeenCalled();
    expect(states.at(-1)).toBe('unavailable');
  });

  it('listening again in the same language reloads nothing and opens nothing', async () => {
    const { listener, workers, openCapture, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    await expect(listener.listen('fr')).resolves.toBe('listening');
    expect(workers).toHaveLength(1);
    expect(openCapture).toHaveBeenCalledOnce();
  });

  it('a language change reloads the model and keeps the one capture', async () => {
    const { listener, workers, captures, openCapture, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    const second = listener.listen('it');
    await answer(1, 'Ehi LIA');
    await expect(second).resolves.toBe('listening');
    expect(workers[0].terminated).toBe(true);
    expect(listener.phrase).toBe('Ehi LIA');
    expect(openCapture).toHaveBeenCalledOnce();
    expect(captures[0].stopped).toBe(false);
  });

  it('a language change to one without a model releases the microphone', async () => {
    const { listener, captures, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    const second = listener.listen('zh');
    await answer(1, null);
    await expect(second).resolves.toBe('unavailable');
    expect(captures[0].stopped).toBe(true);
  });

  it('pause releases the microphone and keeps the model; listen reopens it', async () => {
    const { listener, workers, captures, openCapture, states, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    await listener.pause();
    expect(captures[0].stopped).toBe(true);
    expect(workers[0].posted.at(-1)?.message).toEqual({ type: 'reset' });
    expect(states.at(-1)).toBe('idle');
    await expect(listener.listen('fr')).resolves.toBe('listening');
    expect(workers).toHaveLength(1);
    expect(openCapture).toHaveBeenCalledTimes(2);
  });

  it('handOff gives the live stream away, untouched', async () => {
    const { listener, captures, states, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    await expect(listener.handOff()).resolves.toBe(captures[0].stream);
    expect(captures[0].detached).toBe(true);
    expect(captures[0].stopped).toBe(false);
    expect(states.at(-1)).toBe('idle');
    await expect(listener.handOff()).resolves.toBeNull();
  });

  it('a detection that arrives after pause is not reported', async () => {
    const { listener, workers, onDetected, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    const pausing = listener.pause();
    workers[0].answer({ type: 'detected', score: 0.99 });
    await pausing;
    expect(onDetected).not.toHaveBeenCalled();
  });

  it('a spoken command reaches the caller while listening, never after a pause', async () => {
    const { listener, workers, onCommand, onDetected, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    expect(listener.commands).toEqual(['stop']);
    workers[0].answer({ type: 'command', command: 'stop' });
    expect(onCommand).toHaveBeenCalledWith('stop');
    expect(onDetected).not.toHaveBeenCalled();
    const pausing = listener.pause();
    workers[0].answer({ type: 'command', command: 'stop' });
    await pausing;
    expect(onCommand).toHaveBeenCalledTimes(1);
  });

  it('a runtime that fails while listening releases the microphone and says unavailable', async () => {
    const { listener, workers, captures, states, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    workers[0].answer({ type: 'failed', reason: 'runtime' });
    await vi.waitFor(() => expect(captures[0].stopped).toBe(true));
    expect(states.at(-1)).toBe('unavailable');
    // The next listen tries the model again.
    const again = listener.listen('fr');
    await answer(1, 'Dis LIA');
    await expect(again).resolves.toBe('listening');
  });

  it('a capture that fails to release still leaves the listener idle', async () => {
    const { listener, captures, states, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    captures[0].stop = async () => {
      throw new DOMException('closed', 'InvalidStateError');
    };
    await expect(listener.pause()).resolves.toBeUndefined();
    expect(states.at(-1)).toBe('idle');
  });

  it('a refused microphone rejects with the browser error and a later listen retries', async () => {
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const { listener, states, answer } = setup({ refuse: denied });
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await expect(first).rejects.toBe(denied);
    expect(states.at(-1)).toBe('idle');
    await expect(listener.listen('fr')).rejects.toBe(denied);
  });

  it('dispose during a load opens no microphone afterwards', async () => {
    const { listener, workers, openCapture } = setup();
    const listening = listener.listen('fr');
    await vi.waitFor(() => expect(workers[0]).toBeDefined());
    await listener.dispose();
    await expect(listening).resolves.toBe('idle');
    workers[0].answer({ type: 'ready', phrase: 'Dis LIA', commands: [] });
    expect(openCapture).not.toHaveBeenCalled();
    expect(workers[0].terminated).toBe(true);
    await expect(listener.listen('fr')).resolves.toBe('idle');
  });

  it('dispose releases an open microphone', async () => {
    const { listener, captures, answer } = setup();
    const first = listener.listen('fr');
    await answer(0, 'Dis LIA');
    await first;
    await listener.dispose();
    expect(captures[0].stopped).toBe(true);
  });

  it('a pause asked while the model loads runs after it, and leaves nothing open', async () => {
    const { listener, captures, answer } = setup();
    const listening = listener.listen('fr');
    const pausing = listener.pause();
    await answer(0, 'Dis LIA');
    await listening;
    await pausing;
    expect(captures[0].stopped).toBe(true);
    expect(listener.currentState).toBe('idle');
  });
});
