// @vitest-environment node
/**
 * The runtime refuses any model file its manifest does not describe (ADR-329):
 * a spoken command's classifier included, and before anything is run.
 */
import { createHash } from 'node:crypto';

import { describe, expect, it } from 'vitest';

import type { WakeFile, WakeManifest } from '../manifest';
import { IntegrityError, createOrtRuntime } from '../ort-runtime';

const bytesOf = (text: string) => new TextEncoder().encode(text).buffer as ArrayBuffer;

/** A file entry describing `text` exactly, served at `url`. */
function described(url: string, text: string): WakeFile {
  const bytes = new Uint8Array(bytesOf(text));
  return { url, sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length };
}

const policy = { threshold: 0.5, patience: 1, refractoryChunks: 25, warmupChunks: 25 };

describe('createOrtRuntime', () => {
  it("refuses a command's classifier that is not the file its manifest names", async () => {
    const served: Record<string, string> = {
      '/models/wake/v1/shared/mel.onnx': 'mel',
      '/models/wake/v1/shared/embedding.onnx': 'embedding',
      '/models/wake/v1/fr/classifier.onnx': 'classifier',
      '/models/wake/v1/fr/stop-classifier.onnx': 'a different file',
    };
    const manifest: WakeManifest = {
      version: 'v1',
      language: 'fr',
      phrase: 'Dis LIA',
      policy,
      files: {
        melspectrogram: described('/models/wake/v1/shared/mel.onnx', 'mel'),
        embedding: described('/models/wake/v1/shared/embedding.onnx', 'embedding'),
        classifier: described('/models/wake/v1/fr/classifier.onnx', 'classifier'),
      },
      commands: {
        stop: {
          phrase: 'Stop',
          policy,
          classifier: described('/models/wake/v1/fr/stop-classifier.onnx', 'stop'),
        },
      },
    };
    const fetched: string[] = [];
    const created = createOrtRuntime(manifest, {
      fetchBytes: async url => {
        fetched.push(url);
        return bytesOf(served[url]);
      },
    });
    await expect(created).rejects.toThrow(IntegrityError);
    await expect(created).rejects.toThrow('the stop classifier model does not match its manifest');
    expect(fetched).toContain('/models/wake/v1/fr/stop-classifier.onnx');
  });
});
