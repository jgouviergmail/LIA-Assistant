/**
 * The two vocabularies of ADR-390, as the frontend reads them: a MODE a person
 * chooses, an ENGINE that answered — never one read as the other.
 */
import { describe, expect, it } from 'vitest';

import { executionEngineOf, executionModeOf } from '../execution-mode';

describe('executionModeOf', () => {
  it.each(['pipeline', 'react', 'auto'] as const)('keeps the choice %s', mode => {
    expect(executionModeOf(mode)).toBe(mode);
  });

  it.each([undefined, null, '', 'loop', 'AUTO', 3])(
    'reads %s as the pipeline, the default',
    value => {
      expect(executionModeOf(value)).toBe('pipeline');
    }
  );
});

describe('executionEngineOf', () => {
  it.each(['pipeline', 'react'] as const)('names the engine %s of an automatic turn', engine => {
    expect(executionEngineOf({ execution_engine: engine })).toBe(engine);
  });

  it.each([
    ['no metadata', undefined],
    ['a turn whose mode was chosen', { execution_mode: 'react' }],
    ['a requested mode', { execution_engine: 'auto' }],
    ['a value of another shape', { execution_engine: ['react'] }],
  ])('names none for %s', (_case, metadata) => {
    expect(executionEngineOf(metadata)).toBeNull();
  });
});
