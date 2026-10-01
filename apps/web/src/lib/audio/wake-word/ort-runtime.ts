/**
 * The three wake-word stages on ONNX Runtime Web (ADR-329).
 *
 * Single-threaded WASM, no proxy worker: the engine already runs in its own
 * worker, and a single thread needs neither `SharedArrayBuffer` nor
 * cross-origin isolation — the reason the previous engine was unavailable on
 * iOS and in the native shells. The runtime binary is served from
 * `/ort/<version>/` (copied there from the package by
 * `scripts/copy-ort-runtime.mjs`, never from a CDN: a self-hosted install calls
 * no third party); the version in the path lets it be cached as immutable.
 *
 * Every model file is fetched, checked against the size and SHA-256 its
 * manifest states, and only then handed to the runtime: a file that does not
 * match is refused, never run — a spoken command's classifier included.
 */
import * as ort from 'onnxruntime-web/wasm';

import { WAKE_COMMANDS, type WakeCommand } from './commands';
import { EMBEDDING_DIM, EMBEDDINGS, MEL_BINS, MEL_WINDOW, type WakeWordRuntime } from './engine';
import type { WakeFile, WakeManifest } from './manifest';

/** Where the browser finds the ONNX Runtime WASM binary of the bundled release. */
export const ORT_WASM_BASE = `/ort/${ort.env.versions.web}/`;

export class IntegrityError extends Error {
  /** @param what The model, as a person reads it (`classifier`, `stop classifier`). */
  constructor(what: string) {
    super(`the ${what} model does not match its manifest`);
    this.name = 'IntegrityError';
  }
}

export interface OrtRuntimeOptions {
  /** Fetches a model file (the browser's `fetch` by default). */
  fetchBytes?: (url: string) => Promise<ArrayBuffer>;
  /** Where the WASM binary lives (a file URL under Node, for the tests). */
  wasmPaths?: string;
}

async function defaultFetch(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`model fetch ${response.status}`);
  return response.arrayBuffer();
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

async function verified(
  what: string,
  file: WakeFile,
  fetchBytes: (url: string) => Promise<ArrayBuffer>
): Promise<Uint8Array> {
  const bytes = await fetchBytes(file.url);
  if (bytes.byteLength !== file.bytes || (await sha256Hex(bytes)) !== file.sha256) {
    throw new IntegrityError(what);
  }
  return new Uint8Array(bytes);
}

async function session(bytes: Uint8Array): Promise<ort.InferenceSession> {
  return ort.InferenceSession.create(bytes, {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'all',
  });
}

async function run(
  model: ort.InferenceSession,
  data: Float32Array,
  dims: readonly number[]
): Promise<Float32Array> {
  const output = await model.run({ [model.inputNames[0]]: new ort.Tensor('float32', data, dims) });
  return Float32Array.from(output[model.outputNames[0]].data as Float32Array);
}

/** The runtime of a manifest's models (its three stages, its commands), every file verified first. */
export async function createOrtRuntime(
  manifest: WakeManifest,
  options: OrtRuntimeOptions = {}
): Promise<WakeWordRuntime> {
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = options.wasmPaths ?? ORT_WASM_BASE;
  const fetchBytes = options.fetchBytes ?? defaultFetch;
  const commands = WAKE_COMMANDS.flatMap(command => {
    const model = manifest.commands[command];
    return model ? [{ command, file: model.classifier }] : [];
  });
  const [melBytes, embeddingBytes, classifierBytes, ...commandBytes] = await Promise.all([
    ...(['melspectrogram', 'embedding', 'classifier'] as const).map(key =>
      verified(key, manifest.files[key], fetchBytes)
    ),
    ...commands.map(({ command, file }) => verified(`${command} classifier`, file, fetchBytes)),
  ]);
  const mel = await session(melBytes);
  const embedding = await session(embeddingBytes);
  const classifier = await session(classifierBytes);
  const commandSessions = new Map<WakeCommand, ort.InferenceSession>();
  for (const [index, { command }] of commands.entries()) {
    commandSessions.set(command, await session(commandBytes[index]));
  }
  const score = async (model: ort.InferenceSession, features: Float32Array) =>
    (await run(model, features, [1, EMBEDDINGS, EMBEDDING_DIM]))[0];
  return {
    melspectrogram: samples => run(mel, samples, [1, samples.length]),
    embed: window => run(embedding, window, [1, MEL_WINDOW, MEL_BINS, 1]),
    classify: features => score(classifier, features),
    classifyCommand: async (command, features) => {
      const model = commandSessions.get(command);
      if (!model) throw new Error(`the manifest ships no ${command} classifier`);
      return score(model, features);
    },
  };
}
