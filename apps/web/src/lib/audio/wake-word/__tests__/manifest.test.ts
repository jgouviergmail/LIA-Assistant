import { describe, expect, it } from 'vitest';

import { languages } from '@/i18n/settings';

import {
  ManifestError,
  WAKE_MODEL_STATUS,
  WAKE_SHIPPED_LANGUAGES,
  isWakeBeta,
  manifestUrl,
  parseManifest,
  wakeLanguageOf,
} from '../manifest';

const sha = (c: string) => c.repeat(64);

function valid(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    version: 'v1',
    language: 'fr',
    phrase: 'Dis LIA',
    sample_rate: 16000,
    chunk_samples: 1280,
    threshold: 0.9,
    patience: 1,
    refractory_chunks: 25,
    warmup_chunks: 25,
    files: {
      melspectrogram: {
        url: '/models/wake/v1/shared/melspectrogram.onnx',
        sha256: sha('a'),
        bytes: 10,
      },
      embedding: {
        url: '/models/wake/v1/shared/embedding_model.onnx',
        sha256: sha('b'),
        bytes: 20,
      },
      classifier: { url: '/models/wake/v1/fr/classifier.onnx', sha256: sha('c'), bytes: 30 },
    },
    measured: { recall_clean: 0.95 },
    provenance: { generator: 'scripts/wake-word' },
    ...overrides,
  };
}

const BACKSLASH = String.fromCharCode(92);

describe('parseManifest', () => {
  it('reads a complete manifest', () => {
    const manifest = parseManifest(valid(), 'fr');
    expect(manifest.phrase).toBe('Dis LIA');
    expect(manifest.policy).toEqual({
      threshold: 0.9,
      patience: 1,
      refractoryChunks: 25,
      warmupChunks: 25,
    });
    expect(manifest.files.classifier.url).toBe('/models/wake/v1/fr/classifier.onnx');
  });

  it.each([
    ['another language than asked', { language: 'de' }],
    ['a sample rate the engine does not run at', { sample_rate: 22050 }],
    ['a chunk the engine does not use', { chunk_samples: 1600 }],
    ['a threshold out of (0, 1]', { threshold: 0 }],
    ['a non-integer patience', { patience: 1.5 }],
    ['a negative refractory period', { refractory_chunks: -1 }],
    ['no warm-up', { warmup_chunks: 0 }],
    ['an empty phrase', { phrase: '' }],
    ['another model generation than the engine runs', { version: 'v2' }],
  ])('refuses %s', (_label, override) => {
    expect(() => parseManifest(valid(override), 'fr')).toThrow(ManifestError);
  });

  it.each([
    ['another origin', 'https://evil.example/c.onnx'],
    ['a protocol-relative URL', '//evil.example/models/wake/c.onnx'],
    ['a parent segment', '/models/wake/v1/../../api/x'],
    ['an encoded parent segment', '/models/wake/%2e%2e/%2E%2E/api/x'],
    ['a backslash', `/models/wake/v1${BACKSLASH}..${BACKSLASH}x`],
    ['a query', '/models/wake/v1/fr/c.onnx?x=1'],
  ])('refuses a file served from outside the models path: %s', (_label, url) => {
    const manifest = valid();
    (manifest.files as Record<string, Record<string, unknown>>).classifier.url = url;
    expect(() => parseManifest(manifest, 'fr')).toThrow(ManifestError);
  });

  it('refuses a malformed hash and a missing file', () => {
    const badHash = valid();
    (badHash.files as Record<string, Record<string, unknown>>).embedding.sha256 = 'xyz';
    expect(() => parseManifest(badHash, 'fr')).toThrow(ManifestError);
    const missing = valid();
    delete (missing.files as Record<string, unknown>).melspectrogram;
    expect(() => parseManifest(missing, 'fr')).toThrow(ManifestError);
  });

  it('refuses what is not an object', () => {
    expect(() => parseManifest(null, 'fr')).toThrow(ManifestError);
    expect(() => parseManifest('manifest', 'fr')).toThrow(ManifestError);
  });
});

/** A spoken command beside the phrase: its own word, policy and classifier. */
function stop(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    phrase: 'Stop',
    threshold: 0.8,
    patience: 2,
    refractory_chunks: 10,
    warmup_chunks: 25,
    classifier: { url: '/models/wake/v1/fr/stop-classifier.onnx', sha256: sha('d'), bytes: 40 },
    measured: { recall_clean: 0.93 },
    ...overrides,
  };
}

describe('parseManifest — spoken commands', () => {
  it('reads a command with its own word, policy and classifier', () => {
    const manifest = parseManifest(valid({ commands: { stop: stop() } }), 'fr');
    expect(manifest.commands).toEqual({
      stop: {
        phrase: 'Stop',
        policy: { threshold: 0.8, patience: 2, refractoryChunks: 10, warmupChunks: 25 },
        classifier: {
          url: '/models/wake/v1/fr/stop-classifier.onnx',
          sha256: sha('d'),
          bytes: 40,
        },
      },
    });
  });

  it('reads a manifest without commands as offering none', () => {
    expect(parseManifest(valid(), 'fr').commands).toEqual({});
  });

  it('leaves out a command this engine does not know (a later generation of the toolbox)', () => {
    const manifest = parseManifest(valid({ commands: { stop: stop(), louder: stop() } }), 'fr');
    expect(Object.keys(manifest.commands)).toEqual(['stop']);
  });

  it.each([
    ['commands that are not an object', 'stop'],
    ['a command that is not an object', { stop: 'Stop' }],
    ['a command with an empty word', { stop: stop({ phrase: ' ' }) }],
    ['a command with a threshold out of (0, 1]', { stop: stop({ threshold: 1.5 }) }],
    ['a command without patience', { stop: stop({ patience: undefined }) }],
    [
      'a command served from outside the models path',
      { stop: stop({ classifier: { url: '/api/x.onnx', sha256: sha('d'), bytes: 40 } }) },
    ],
    ['a command without a classifier', { stop: stop({ classifier: undefined }) }],
  ])('refuses %s, never half-reads a known one', (_label, commands) => {
    expect(() => parseManifest(valid({ commands }), 'fr')).toThrow(ManifestError);
  });
});

describe('wakeLanguageOf and manifestUrl', () => {
  it('maps the interface language to its shipped model, region codes included', () => {
    expect(wakeLanguageOf('fr')).toBe('fr');
    expect(wakeLanguageOf('fr-CA')).toBe('fr');
    expect(wakeLanguageOf('pt')).toBeNull();
    expect(wakeLanguageOf(undefined)).toBeNull();
  });

  it('answers null for an interface language no model ships for', () => {
    for (const language of languages) {
      expect(wakeLanguageOf(language)).toBe(
        WAKE_SHIPPED_LANGUAGES.includes(language) ? language : null
      );
    }
  });

  it('ships every declared language, and only those, flagging the beta ones', () => {
    expect([...WAKE_SHIPPED_LANGUAGES].sort()).toEqual(Object.keys(WAKE_MODEL_STATUS).sort());
    for (const language of WAKE_SHIPPED_LANGUAGES) {
      expect(isWakeBeta(language)).toBe(WAKE_MODEL_STATUS[language] === 'beta');
    }
    expect(isWakeBeta('pt')).toBe(false);
  });

  it('points at the versioned manifest of a language', () => {
    expect(manifestUrl('de')).toBe('/models/wake/v1/de/manifest.json');
  });
});
