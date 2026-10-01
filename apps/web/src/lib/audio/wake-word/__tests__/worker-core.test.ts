import { describe, expect, it, vi } from 'vitest';

import type { WakeWordRuntime } from '../engine';
import { ManifestError } from '../manifest';
import { IntegrityError } from '../ort-runtime';
import type { FromWorker } from '../protocol';
import { createWorkerHandler } from '../worker-core';

const sha = (c: string) => c.repeat(64);
const policyFields = {
  patience: 1,
  refractory_chunks: 25,
  warmup_chunks: 25,
};
const stopCommand = (language: string) => ({
  phrase: 'Stop',
  threshold: 0.5,
  ...policyFields,
  classifier: { url: `/models/wake/v1/${language}/s.onnx`, sha256: sha('d'), bytes: 1 },
});
const manifest = (language: string, threshold = 0.5, commands?: Record<string, unknown>) => ({
  version: 'v1',
  language,
  phrase: 'Dis LIA',
  sample_rate: 16000,
  chunk_samples: 1280,
  threshold,
  patience: 1,
  refractory_chunks: 25,
  warmup_chunks: 25,
  files: {
    melspectrogram: { url: '/models/wake/v1/shared/m.onnx', sha256: sha('a'), bytes: 1 },
    embedding: { url: '/models/wake/v1/shared/e.onnx', sha256: sha('b'), bytes: 1 },
    classifier: { url: `/models/wake/v1/${language}/c.onnx`, sha256: sha('c'), bytes: 1 },
  },
  ...(commands ? { commands } : {}),
});

/** A runtime whose classifier returns `score` for every window (`commandScore` for a command's). */
const runtime = (score: number, commandScore = 0): WakeWordRuntime => ({
  melspectrogram: async samples =>
    new Float32Array((1 + Math.floor((samples.length - 512) / 160)) * 32),
  embed: async () => new Float32Array(96),
  classify: async () => score,
  classifyCommand: async () => commandScore,
});

function setup(
  options: {
    score?: number;
    fetchJson?: (url: string) => Promise<unknown>;
    createRuntime?: () => Promise<WakeWordRuntime>;
  } = {}
) {
  const posted: FromWorker[] = [];
  const fetchJson = vi.fn(
    options.fetchJson ?? (async (url: string) => manifest(url.split('/')[4]))
  );
  const handle = createWorkerHandler({
    post: message => posted.push(message),
    fetchJson,
    createRuntime: options.createRuntime ?? (async () => runtime(options.score ?? 0)),
  });
  return { handle, posted, fetchJson };
}

const chunks = (n: number) => new Int16Array(1280 * n).buffer;

describe('createWorkerHandler', () => {
  it('loads the language manifest and answers ready with its phrase', async () => {
    const { handle, posted, fetchJson } = setup();
    await handle({ type: 'load', language: 'fr' });
    expect(fetchJson).toHaveBeenCalledWith('/models/wake/v1/fr/manifest.json');
    expect(posted).toEqual([{ type: 'ready', phrase: 'Dis LIA', commands: [] }]);
  });

  it('answers ready with the spoken commands its model ships, and posts each one heard', async () => {
    const { handle, posted } = setup({
      fetchJson: async () => manifest('fr', 0.5, { stop: stopCommand('fr') }),
      createRuntime: async () => runtime(0, 0.99),
    });
    await handle({ type: 'load', language: 'fr' });
    await handle({ type: 'audio', samples: chunks(30) });
    expect(posted).toEqual([
      { type: 'ready', phrase: 'Dis LIA', commands: ['stop'] },
      { type: 'command', command: 'stop' },
    ]);
  });

  it.each([
    ['manifest', () => Promise.reject(new ManifestError('missing')), undefined],
    ['integrity', undefined, () => Promise.reject(new IntegrityError('classifier'))],
    ['runtime', undefined, () => Promise.reject(new Error('wasm refused'))],
  ] as const)('answers failed: %s', async (reason, fetchJson, createRuntime) => {
    const { handle, posted } = setup({ fetchJson, createRuntime });
    await handle({ type: 'load', language: 'fr' });
    expect(posted).toEqual([{ type: 'failed', reason }]);
  });

  it('ignores audio before ready, then posts each detection', async () => {
    const { handle, posted } = setup({ score: 0.99 });
    await handle({ type: 'audio', samples: chunks(30) });
    expect(posted).toEqual([]);
    await handle({ type: 'load', language: 'fr' });
    await handle({ type: 'audio', samples: chunks(30) });
    expect(posted.filter(m => m.type === 'detected')).toEqual([{ type: 'detected', score: 0.99 }]);
  });

  it('a newer load supersedes one still in flight', async () => {
    let release: (value: unknown) => void = () => undefined;
    const slow = new Promise(resolve => {
      release = resolve;
    });
    const fetchJson = vi
      .fn()
      .mockImplementationOnce(async () => {
        await slow;
        return manifest('fr');
      })
      .mockImplementationOnce(async () => manifest('de'));
    const { handle, posted } = setup({ fetchJson });
    const first = handle({ type: 'load', language: 'fr' });
    await handle({ type: 'load', language: 'de' });
    release(undefined);
    await first;
    expect(posted).toEqual([{ type: 'ready', phrase: 'Dis LIA', commands: [] }]);
    expect(fetchJson).toHaveBeenCalledTimes(2);
  });

  it('says nothing for the audio of an engine a newer load replaced', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    let gated = true;
    const slow: WakeWordRuntime = {
      ...runtime(0.99),
      classify: async () => {
        if (gated) await gate;
        return 0.99;
      },
    };
    const { handle, posted } = setup({ createRuntime: async () => slow });
    await handle({ type: 'load', language: 'fr' });
    const stale = handle({ type: 'audio', samples: chunks(30) });
    gated = false;
    await handle({ type: 'load', language: 'fr' });
    release();
    await stale;
    expect(posted.filter(m => m.type === 'detected')).toEqual([]);
  });

  it('a runtime that fails mid-stream is reported once and stops listening', async () => {
    let calls = 0;
    const flaky: WakeWordRuntime = {
      ...runtime(0),
      classify: async () => {
        calls += 1;
        if (calls === 3) throw new Error('wasm trap');
        return 0;
      },
    };
    const { handle, posted } = setup({ createRuntime: async () => flaky });
    await handle({ type: 'load', language: 'fr' });
    await handle({ type: 'audio', samples: chunks(5) });
    await handle({ type: 'audio', samples: chunks(5) });
    expect(posted).toEqual([
      { type: 'ready', phrase: 'Dis LIA', commands: [] },
      { type: 'failed', reason: 'runtime' },
    ]);
  });
});
