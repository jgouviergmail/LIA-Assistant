/**
 * The API error envelope — and the reason this module exists.
 *
 * Both HTTP clients throw an error that carries the parsed body on `.data`.
 * For a long time the call sites read `err.response?.data?.detail` instead —
 * the axios shape, from a dependency this app dropped. That optional chain
 * never resolved, so **every** backend message was silently replaced by a
 * generic fallback: an admin saw "Erreur lors de la création du modèle"
 * instead of "model already exists", and a refused connector preference lost
 * the field error explaining why.
 *
 * These tests drive the real error classes, never a hand-written stand-in, so
 * a change to either client's shape breaks here rather than in production.
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { ApiError, ApiStepUpError } from '@/lib/api-client';
import { getApiErrorDetail } from '@/lib/api-error';

/** Envelope FastAPI puts on the wire for a `BaseAPIException` with a str detail. */
function apiErrorWithDetail(detail: unknown, status = 422): ApiError {
  return new ApiError('irrelevant', status, { detail });
}

describe('getApiErrorDetail — string detail', () => {
  it('returns the detail a real ApiError carries', () => {
    expect(getApiErrorDetail(apiErrorWithDetail('Model already exists', 409))).toBe(
      'Model already exists'
    );
  });

  it('trims surrounding whitespace', () => {
    expect(getApiErrorDetail(apiErrorWithDetail('  spaced  '))).toBe('spaced');
  });

  it('treats a blank detail as absent so the caller keeps its translated fallback', () => {
    expect(getApiErrorDetail(apiErrorWithDetail('   '))).toBeUndefined();
    expect(getApiErrorDetail(apiErrorWithDetail(''))).toBeUndefined();
  });
});

describe('getApiErrorDetail — ConnectorValidationError envelope', () => {
  // apps/api/src/core/exceptions.py::ConnectorValidationError overrides
  // `self.detail` with {"errors": [{"field": ..., "message": ...}]}.
  it('joins the field messages of a connector validation 422', () => {
    const detail = {
      errors: [
        { field: 'preferences', message: 'unknown calendar' },
        { field: 'preferences', message: 'try again' },
      ],
    };
    expect(getApiErrorDetail(apiErrorWithDetail(detail))).toBe('unknown calendar, try again');
  });

  it('returns undefined when the errors list is empty', () => {
    expect(getApiErrorDetail(apiErrorWithDetail({ errors: [] }))).toBeUndefined();
  });

  it('skips entries that carry no usable message', () => {
    const detail = { errors: [{ field: 'a' }, { field: 'b', message: '  ' }, 'plain text'] };
    expect(getApiErrorDetail(apiErrorWithDetail(detail))).toBe('plain text');
  });

  it('ignores a dict detail that has no errors list', () => {
    expect(getApiErrorDetail(apiErrorWithDetail({ code: 'x' }))).toBeUndefined();
  });
});

describe('getApiErrorDetail — Pydantic / StructuredValidationError envelope', () => {
  // FastAPI's own 422 (and `StructuredValidationError`) put a LIST on `detail`,
  // each entry keyed `msg`, not `message`.
  it('joins the msg of each validation entry', () => {
    const detail = [
      { type: 'greater_than', loc: ['body', 'max_tokens'], msg: 'must be > 0' },
      { type: 'missing', loc: ['body', 'model_name'], msg: 'field required' },
    ];
    expect(getApiErrorDetail(apiErrorWithDetail(detail))).toBe('must be > 0, field required');
  });

  it('returns undefined for an empty list', () => {
    expect(getApiErrorDetail(apiErrorWithDetail([]))).toBeUndefined();
  });
});

describe('getApiErrorDetail — failures that carry nothing usable', () => {
  it('returns undefined for a plain Error (network failure, thrown by fetch)', () => {
    expect(getApiErrorDetail(new Error('Failed to fetch'))).toBeUndefined();
  });

  it('returns undefined for an ApiError with no body at all', () => {
    expect(getApiErrorDetail(new ApiError('Unauthorized', 401))).toBeUndefined();
  });

  it('returns undefined when the body is raw text (an HTML error page)', () => {
    // api-client keeps a non-JSON body as a string; surfacing it would print
    // markup at the user.
    expect(
      getApiErrorDetail(new ApiError('HTTP 502', 502, '<html>bad gateway</html>'))
    ).toBeUndefined();
  });

  it('returns undefined for a step-up challenge with no detail', () => {
    expect(getApiErrorDetail(new ApiStepUpError())).toBeUndefined();
  });

  it.each([[null], [undefined], ['a string'], [42]])('returns undefined for %o', value => {
    expect(getApiErrorDetail(value)).toBeUndefined();
  });
});

describe('error-class contract the extractor depends on', () => {
  it('ApiError exposes the parsed body on .data and never on .response', () => {
    const error = new ApiError('boom', 400, { detail: 'why' });
    expect(error.data).toEqual({ detail: 'why' });
    expect('response' in error).toBe(false);
  });

  it('ApiStepUpError exposes the same .data field', () => {
    const error = new ApiStepUpError({ detail: 'step up' });
    expect(error.data).toEqual({ detail: 'step up' });
    expect('response' in error).toBe(false);
  });

  it('ServerApiError (Server Actions) carries the body on .data too', async () => {
    // Imported lazily: the module pulls `next/headers`, which only the server
    // bundle normally resolves.
    const { ServerApiError } = await import('@/lib/api-server');
    const error = new ServerApiError('boom', 409, { detail: 'conflict' });
    expect(error.data).toEqual({ detail: 'conflict' });
    expect('response' in error).toBe(false);
    expect(getApiErrorDetail(error)).toBe('conflict');
  });
});

describe('guard — the axios shape must not come back', () => {
  /** Every first-party source file, tests included. */
  function sourceFiles(): string[] {
    const root = path.resolve(__dirname, '../..');
    return fs
      .readdirSync(root, { recursive: true, encoding: 'utf8' })
      .filter(entry => /\.(ts|tsx)$/.test(entry))
      .map(entry => path.join(root, entry))
      .filter(file => fs.statSync(file).isFile());
  }

  /** The historical defect, in both its optional-chained and plain forms. */
  const AXIOS_SHAPE = /\.response\s*(\?\.|\.)\s*data\b/;

  /** Lines that are pure prose — naming the defect in a doc block is allowed. */
  function isCommentLine(line: string): boolean {
    const trimmed = line.trimStart();
    return trimmed.startsWith('*') || trimmed.startsWith('//') || trimmed.startsWith('/*');
  }

  it('no source file reads an error through `.response.data`', () => {
    const offenders = sourceFiles()
      // This file spells the defect out on purpose, in the oracle below.
      .filter(file => path.basename(file) !== 'api-error.test.ts')
      .filter(file =>
        fs
          .readFileSync(file, 'utf8')
          .split('\n')
          .some(line => !isCommentLine(line) && AXIOS_SHAPE.test(line))
      )
      .map(file => path.relative(path.resolve(__dirname, '../..'), file));
    expect(offenders).toEqual([]);
  });

  it('the guard actually catches the historical defect', () => {
    expect(AXIOS_SHAPE.test("apiError.response?.data?.detail || t('x')")).toBe(true);
    expect(AXIOS_SHAPE.test('err.response.data.detail')).toBe(true);
    expect(AXIOS_SHAPE.test('getApiErrorDetail(error) ?? fallback')).toBe(false);
  });

  it('the guard still reads code that carries a trailing comment', () => {
    const line = 'const x = err.response?.data?.detail; // legacy';
    expect(isCommentLine(line)).toBe(false);
    expect(AXIOS_SHAPE.test(line)).toBe(true);
  });
});
