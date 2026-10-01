/**
 * The wake-word worker (ADR-329): the engine and its ONNX runtime off the main
 * thread, so 80 ms of audio scored never competes with the interface.
 */
import { ManifestError } from './manifest';
import { createOrtRuntime } from './ort-runtime';
import type { FromWorker, ToWorker } from './protocol';
import { createWorkerHandler } from './worker-core';

const scope = self as unknown as {
  postMessage: (message: FromWorker) => void;
  onmessage: ((event: MessageEvent<ToWorker>) => void) | null;
};

const handle = createWorkerHandler({
  post: message => scope.postMessage(message),
  fetchJson: async url => {
    // A manifest that cannot be read is a language without a model, not a
    // broken runtime: the reason says so.
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(String(response.status));
      return await response.json();
    } catch (error) {
      throw new ManifestError(`manifest unreadable: ${String(error)}`);
    }
  },
  createRuntime: manifest => createOrtRuntime(manifest),
});

scope.onmessage = event => {
  void handle(event.data);
};
