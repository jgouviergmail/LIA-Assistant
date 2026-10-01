import { describe, expect, it, vi } from 'vitest';

import { WakeWordDetector } from '../detector';
import { FakeWorker } from './fakes';

function setup() {
  const workers: FakeWorker[] = [];
  const onDetected = vi.fn();
  const onCommand = vi.fn();
  const states: string[] = [];
  const detector = new WakeWordDetector({
    onDetected,
    onCommand,
    onStateChange: state => states.push(state),
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker;
    },
  });
  return { detector, workers, onDetected, onCommand, states };
}

describe('WakeWordDetector', () => {
  it('asks the worker for the language and settles ready with the phrase', async () => {
    const { detector, workers, states } = setup();
    const loading = detector.load('fr');
    expect(workers[0].posted[0].message).toEqual({ type: 'load', language: 'fr' });
    workers[0].answer({ type: 'ready', phrase: 'Dis LIA', commands: [] });
    await expect(loading).resolves.toBe('ready');
    expect(detector.phrase).toBe('Dis LIA');
    expect(states).toEqual(['loading', 'ready']);
  });

  it('settles unavailable on a coded failure and when the worker cannot start', async () => {
    const failing = setup();
    const a = failing.detector.load('de');
    failing.workers[0].answer({ type: 'failed', reason: 'integrity' });
    await expect(a).resolves.toBe('unavailable');

    const broken = setup();
    const b = broken.detector.load('de');
    broken.workers[0].onerror?.({} as ErrorEvent);
    await expect(b).resolves.toBe('unavailable');
  });

  it('transfers audio only once ready, and reports detections', async () => {
    const { detector, workers, onDetected } = setup();
    const loading = detector.load('en');
    detector.push(new ArrayBuffer(2560));
    expect(workers[0].posted).toHaveLength(1); // the load only
    workers[0].answer({ type: 'ready', phrase: 'Hey LIA', commands: [] });
    await loading;
    const buffer = new ArrayBuffer(2560);
    detector.push(buffer);
    expect(workers[0].posted[1]).toEqual({
      message: { type: 'audio', samples: buffer },
      transfer: [buffer],
    });
    workers[0].answer({ type: 'detected', score: 0.97 });
    expect(onDetected).toHaveBeenCalledTimes(1);
  });

  it('knows the spoken commands its model ships, and reports each one heard once ready', async () => {
    const { detector, workers, onDetected, onCommand } = setup();
    const loading = detector.load('fr');
    workers[0].answer({ type: 'command', command: 'stop' });
    expect(onCommand).not.toHaveBeenCalled();
    workers[0].answer({ type: 'ready', phrase: 'Dis LIA', commands: ['stop'] });
    await loading;
    expect(detector.commands).toEqual(['stop']);
    workers[0].answer({ type: 'command', command: 'stop' });
    expect(onCommand).toHaveBeenCalledWith('stop');
    expect(onDetected).not.toHaveBeenCalled();
    detector.dispose();
    expect(detector.commands).toEqual([]);
  });

  it('a reload terminates the previous worker and ignores what it still says', async () => {
    const { detector, workers, onDetected } = setup();
    const first = detector.load('fr');
    const second = detector.load('it');
    await expect(first).resolves.toBe('idle');
    expect(workers[0].terminated).toBe(true);
    workers[0].answer({ type: 'ready', phrase: 'Dis LIA', commands: [] });
    workers[0].answer({ type: 'detected', score: 1 });
    expect(detector.currentState).toBe('loading');
    workers[1].answer({ type: 'ready', phrase: 'Ehi LIA', commands: [] });
    await expect(second).resolves.toBe('ready');
    expect(detector.phrase).toBe('Ehi LIA');
    expect(onDetected).not.toHaveBeenCalled();
  });

  it('dispose() ends the worker and settles a pending load', async () => {
    const { detector, workers, states } = setup();
    const loading = detector.load('zh');
    detector.dispose();
    await expect(loading).resolves.toBe('idle');
    expect(workers[0].terminated).toBe(true);
    expect(states.at(-1)).toBe('idle');
  });

  it('reset() tells the worker the stream restarts', async () => {
    const { detector, workers } = setup();
    const loading = detector.load('es');
    workers[0].answer({ type: 'ready', phrase: 'Oye LIA', commands: [] });
    await loading;
    detector.reset();
    expect(workers[0].posted.at(-1)?.message).toEqual({ type: 'reset' });
  });
});
