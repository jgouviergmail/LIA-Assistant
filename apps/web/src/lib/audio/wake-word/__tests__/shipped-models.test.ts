// @vitest-environment node
/**
 * The wake-word models the app ships (ADR-329), read from `public/` as the
 * browser will fetch them:
 *
 *  - every language `WAKE_MODEL_STATUS` declares has its model, with the
 *    phrase and the stop word the screens name — and no other language has
 *    one (a manifest nobody loads is weight every install carries);
 *  - every file is exactly the one its manifest names (size and SHA-256 —
 *    the browser refuses anything else, so a stale manifest would disable the
 *    wake word everywhere);
 *  - a `stable` model was ACCEPTED by the bench; a `beta` one was not yet
 *    (the settings say so) and graduates the day its bench says `go`; every
 *    model says what it was built from, under which licences;
 *  - no file ships that no manifest names.
 *
 * Models are written by `task wake:train -- <lang>` (scripts/wake-word).
 */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  WAKE_MODEL_STATUS,
  WAKE_MODEL_VERSION,
  WAKE_SHIPPED_LANGUAGES,
  parseManifest,
  type WakeManifest,
} from '../manifest';
import { STOP_WORDS, WAKE_PHRASES } from '../phrases';

const PUBLIC = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  '..',
  '..',
  '..',
  'public'
);
const MODELS = join(PUBLIC, 'models', 'wake');

function raw(language: string): Record<string, unknown> {
  const path = join(MODELS, WAKE_MODEL_VERSION, language, 'manifest.json');
  return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
}

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap(name => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

/** The public URL of a file under `public/`. */
const urlOf = (path: string) => `/${relative(PUBLIC, path).split('\\').join('/')}`;

/** Every model file a manifest names: its three stages and each command's classifier. */
const modelFiles = (manifest: WakeManifest) => [
  ...Object.values(manifest.files),
  ...Object.values(manifest.commands).map(command => command.classifier),
];

describe('shipped wake-word models', () => {
  it('ships a manifest for the declared languages and no other', () => {
    const directories = readdirSync(join(MODELS, WAKE_MODEL_VERSION)).filter(
      name => name !== 'shared'
    );
    expect(directories.sort()).toEqual([...WAKE_SHIPPED_LANGUAGES].sort());
  });

  it.each(WAKE_SHIPPED_LANGUAGES)('%s: every file is the one its manifest names', language => {
    const manifest: WakeManifest = parseManifest(raw(language), language);
    // The words a screen names before any model loads are the model's own.
    expect(manifest.phrase).toBe(WAKE_PHRASES[language]);
    expect(manifest.commands.stop?.phrase).toBe(STOP_WORDS[language]);
    for (const file of modelFiles(manifest)) {
      const bytes = readFileSync(join(PUBLIC, file.url));
      expect(bytes.byteLength, file.url).toBe(file.bytes);
      expect(createHash('sha256').update(bytes).digest('hex'), file.url).toBe(file.sha256);
    }
  });

  it.each(WAKE_SHIPPED_LANGUAGES)('%s: its bench verdict matches its status, with provenance', language => {
    const { measured, provenance, commands } = raw(language) as {
      measured: { verdict: string };
      provenance: Record<string, unknown>;
      commands: { stop: { measured: { verdict: string } } };
    };
    // A stable model passed the bench, phrase AND stop word; a beta one has
    // not yet — the day both say `go`, the table must say `stable`.
    const passed = measured.verdict === 'go' && commands.stop.measured.verdict === 'go';
    expect(['go', 'no-go']).toContain(measured.verdict);
    expect(['go', 'no-go']).toContain(commands.stop.measured.verdict);
    expect(WAKE_MODEL_STATUS[language]).toBe(passed ? 'stable' : 'beta');
    expect(provenance.generator).toBe('scripts/wake-word');
    expect(provenance.sources_lock_sha256).toMatch(/^[0-9a-f]{64}$/);
    for (const key of ['voices', 'synthesisers', 'corpora']) {
      const entries = provenance[key] as string[];
      expect(entries.length, key).toBeGreaterThan(0);
      // Every input names the licence it is used under.
      for (const entry of entries) expect(entry, key).toMatch(/\(.*\)/);
    }
  });

  it('ships no file that no manifest names', () => {
    const named = new Set(
      WAKE_SHIPPED_LANGUAGES.flatMap(language => [
        `/models/wake/${WAKE_MODEL_VERSION}/${language}/manifest.json`,
        ...modelFiles(parseManifest(raw(language), language)).map(file => file.url),
      ])
    );
    expect(
      filesUnder(MODELS)
        .map(urlOf)
        .filter(url => !named.has(url))
    ).toEqual([]);
  });
});
