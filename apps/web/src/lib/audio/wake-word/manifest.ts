/**
 * A language's wake-word model, as its manifest describes it (ADR-329).
 *
 * The toolbox (`scripts/wake-word`) writes `public/models/wake/<version>/<lang>/
 * manifest.json` beside the files it names: each file with its SHA-256 and size
 * (the runtime refuses bytes that do not match), the detection policy the model
 * was measured under, the phrase, and the measured figures. Every model file is
 * named after its SHA-256, so a retrained model is a new URL and a cache never
 * serves a stale one; the manifest keeps its name and is revalidated.
 *
 * A language may also ship SPOKEN COMMANDS (`commands`): a word the person
 * says to LIA rather than to wake her — « Stop » cuts her voice — each with its
 * own classifier over the same embeddings, its own policy and its own measured
 * figures. A manifest without them offers none.
 *
 * Parsing is strict: a manifest this engine cannot run (another generation,
 * sample rate or chunk) or that names a file outside the models path is
 * refused, never half-read — a malformed known command included. A command
 * this engine does not know is left out (a later toolbox may ship one).
 */
import { languages, type Language } from '@/i18n/settings';

import { WAKE_COMMANDS, type WakeCommand } from './commands';
import { CHUNK_SAMPLES, SAMPLE_RATE } from './engine';
import type { DetectionPolicyOptions } from './policy';

/** The model generation the client loads; the toolbox's `MODEL_VERSION`. */
export const WAKE_MODEL_VERSION = 'v1';
const MODELS_PREFIX = '/models/wake/';
/**
 * A plain path under the models prefix: segments of letters, digits, `.`, `_`
 * and `-`, none starting with a dot — so no `..`, no encoded one, no query.
 */
const MODEL_PATH =
  /^\/models\/wake\/(?:[A-Za-z0-9_-][A-Za-z0-9._-]*\/)*[A-Za-z0-9_-][A-Za-z0-9._-]*$/;
const SHA256 = /^[0-9a-f]{64}$/;

export type WakeFileKey = 'melspectrogram' | 'embedding' | 'classifier';

export interface WakeFile {
  url: string;
  sha256: string;
  bytes: number;
}

/** A spoken command: its word, the policy it was measured under, its classifier. */
export interface WakeCommandModel {
  phrase: string;
  policy: DetectionPolicyOptions;
  classifier: WakeFile;
}

export interface WakeManifest {
  version: string;
  language: Language;
  phrase: string;
  policy: DetectionPolicyOptions;
  files: Record<WakeFileKey, WakeFile>;
  commands: Partial<Record<WakeCommand, WakeCommandModel>>;
}

export class ManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ManifestError';
  }
}

/**
 * The languages a model is SHIPPED for, and how far it got through the bench.
 *
 * A language absent here has no model: its listener stays `unavailable` and
 * never fetches a manifest the server does not hold — the person keeps the
 * button. A `beta` model ships BELOW the bench's published thresholds (its
 * manifest's verdict says `no-go`, and the settings say « beta »); a `stable`
 * one passed them. `shipped-models.test.ts` holds this table to the files in
 * `public/`, both ways: a `beta` model whose bench says `go` must graduate, a
 * `stable` one whose bench does not is refused.
 */
export const WAKE_MODEL_STATUS: Readonly<Partial<Record<Language, 'beta' | 'stable'>>> = {
  fr: 'beta',
};

/** The languages a model ships for, in the interface's declaration order. */
export const WAKE_SHIPPED_LANGUAGES: readonly Language[] = languages.filter(
  language => WAKE_MODEL_STATUS[language] !== undefined
);

/** The wake-word language of an interface language (`zh-CN` → `zh`) when a model ships for it, or null. */
export function wakeLanguageOf(language: string | null | undefined): Language | null {
  const base = (language ?? '').toLowerCase().split(/[-_]/)[0];
  return (WAKE_SHIPPED_LANGUAGES as readonly string[]).includes(base) ? (base as Language) : null;
}

/** Whether the model of an interface language (any regional variant) ships in beta. */
export function isWakeBeta(language: string | null | undefined): boolean {
  const wakeLanguage = wakeLanguageOf(language);
  return wakeLanguage !== null && WAKE_MODEL_STATUS[wakeLanguage] === 'beta';
}

export function manifestUrl(language: Language): string {
  return `${MODELS_PREFIX}${WAKE_MODEL_VERSION}/${language}/manifest.json`;
}

function record(value: unknown, what: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ManifestError(`${what} is not an object`);
  }
  return value as Record<string, unknown>;
}

function integer(value: unknown, what: string, min: number): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < min) {
    throw new ManifestError(`${what} must be an integer >= ${min}`);
  }
  return value;
}

function file(value: unknown, what: string): WakeFile {
  const entry = record(value, what);
  const { url, sha256, bytes } = entry;
  if (typeof url !== 'string' || !MODEL_PATH.test(url)) {
    throw new ManifestError(`${what}.url is not under ${MODELS_PREFIX}`);
  }
  if (typeof sha256 !== 'string' || !SHA256.test(sha256)) {
    throw new ManifestError(`${what}.sha256 is not a SHA-256`);
  }
  return { url, sha256, bytes: integer(bytes, `${what}.bytes`, 1) };
}

function phraseOf(value: unknown, what: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new ManifestError(`${what} must be a non-empty string`);
  }
  return value;
}

/** The detection policy an entry was measured under (the manifest's, or a command's). */
function policyOf(entry: Record<string, unknown>, prefix: string): DetectionPolicyOptions {
  const { threshold } = entry;
  if (typeof threshold !== 'number' || !(threshold > 0 && threshold <= 1)) {
    throw new ManifestError(`${prefix}threshold must be in (0, 1]`);
  }
  return {
    threshold,
    patience: integer(entry.patience, `${prefix}patience`, 1),
    refractoryChunks: integer(entry.refractory_chunks, `${prefix}refractory_chunks`, 0),
    warmupChunks: integer(entry.warmup_chunks, `${prefix}warmup_chunks`, 1),
  };
}

function commandsOf(value: unknown): Partial<Record<WakeCommand, WakeCommandModel>> {
  if (value === undefined) return {};
  const entries = record(value, 'commands');
  const commands: Partial<Record<WakeCommand, WakeCommandModel>> = {};
  for (const command of WAKE_COMMANDS) {
    if (!(command in entries)) continue;
    const entry = record(entries[command], `commands.${command}`);
    commands[command] = {
      phrase: phraseOf(entry.phrase, `commands.${command}.phrase`),
      policy: policyOf(entry, `commands.${command}.`),
      classifier: file(entry.classifier, `commands.${command}.classifier`),
    };
  }
  return commands;
}

/** A manifest the engine can run, for the language asked; throws `ManifestError` otherwise. */
export function parseManifest(raw: unknown, language: Language): WakeManifest {
  const manifest = record(raw, 'the manifest');
  if (manifest.language !== language) {
    throw new ManifestError(`the manifest is for ${String(manifest.language)}, not ${language}`);
  }
  if (manifest.sample_rate !== SAMPLE_RATE || manifest.chunk_samples !== CHUNK_SAMPLES) {
    throw new ManifestError('the manifest is for another sample rate or chunk size');
  }
  const { version } = manifest;
  if (version !== WAKE_MODEL_VERSION) {
    throw new ManifestError(
      `the manifest is of generation ${String(version)}, not ${WAKE_MODEL_VERSION}`
    );
  }
  const files = record(manifest.files, 'files');
  return {
    version,
    language,
    phrase: phraseOf(manifest.phrase, 'phrase'),
    policy: policyOf(manifest, ''),
    files: {
      melspectrogram: file(files.melspectrogram, 'files.melspectrogram'),
      embedding: file(files.embedding, 'files.embedding'),
      classifier: file(files.classifier, 'files.classifier'),
    },
    commands: commandsOf(manifest.commands),
  };
}
