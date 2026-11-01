/**
 * How the « Tools » section tells a refusal (ADR-369): every `detail.code` the
 * API sends has a sentence, and a figure beside it is quoted only when the API
 * sent it — a sentence quoting what nobody sent would be a claim nobody made.
 */

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';

import { WORKBENCH_ERROR_CODES, workbenchRefusal } from '../errors';

function refused(detail: unknown, status = 409): ApiError {
  return new ApiError('refused', status, { detail });
}

describe('workbenchRefusal', () => {
  it('tells every code the API sends in its own words', () => {
    for (const code of WORKBENCH_ERROR_CODES) {
      expect(workbenchRefusal(refused({ code }))).toEqual({ key: `workbench.errors.${code}` });
    }
  });

  it('quotes the wait a throttle names, in seconds', () => {
    expect(
      workbenchRefusal(refused({ code: 'provider_rate_limited', retry_after: 30 }, 429))
    ).toEqual({ key: 'workbench.errors.provider_rate_limited_wait', values: { seconds: 30 } });
    expect(
      workbenchRefusal(refused({ code: 'provider_unavailable', retry_after: 5 }, 502))
    ).toEqual({ key: 'workbench.errors.provider_unavailable_wait', values: { seconds: 5 } });
  });

  it('quotes the size bound in megabytes', () => {
    expect(workbenchRefusal(refused({ code: 'too_large', max_bytes: 26_214_400 }, 413))).toEqual({
      key: 'workbench.errors.too_large_bounded',
      values: { megabytes: 25 },
    });
    expect(workbenchRefusal(refused({ code: 'too_large', max_bytes: 3_145_728 }, 413))).toEqual({
      key: 'workbench.errors.too_large_bounded',
      values: { megabytes: 3 },
    });
  });

  it('names the unreadable recipient by its position, counted from one', () => {
    expect(workbenchRefusal(refused({ code: 'invalid_recipient', index: 0 }, 422))).toEqual({
      key: 'workbench.errors.invalid_recipient_at',
      values: { position: 1 },
    });
  });

  it('tells a replay what became of the first submission', () => {
    for (const outcome of ['done', 'pending', 'unknown']) {
      expect(workbenchRefusal(refused({ code: 'already_submitted', outcome }))).toEqual({
        key: `workbench.errors.already_submitted_${outcome}`,
      });
    }
  });

  it('quotes the bound a provider cannot exceed', () => {
    expect(workbenchRefusal(refused({ code: 'not_supported_by_provider', bound: 3 }, 422))).toEqual(
      { key: 'workbench.errors.not_supported_by_provider_bounded', values: { bound: 3 } }
    );
  });

  it('never quotes a figure nobody sent', () => {
    const plain = (code: string, facts: Record<string, unknown>) =>
      workbenchRefusal(refused({ code, ...facts }));
    expect(plain('provider_rate_limited', { retry_after: 'soon' })).toEqual({
      key: 'workbench.errors.provider_rate_limited',
    });
    expect(plain('too_large', { max_bytes: -1 })).toEqual({ key: 'workbench.errors.too_large' });
    expect(plain('invalid_recipient', { index: 1.5 })).toEqual({
      key: 'workbench.errors.invalid_recipient',
    });
    expect(plain('already_submitted', { outcome: 'lost' })).toEqual({
      key: 'workbench.errors.already_submitted',
    });
  });

  it('tells our own window like a provider’s throttle, with the wait it names', () => {
    const throttled = (detail: unknown) => new ApiError('limited', 429, { detail });
    expect(
      workbenchRefusal(throttled({ error: 'rate_limit_exceeded', retry_after_seconds: 60 }))
    ).toEqual({ key: 'workbench.errors.provider_rate_limited_wait', values: { seconds: 60 } });
    expect(workbenchRefusal(throttled({ error: 'rate_limit_exceeded' }))).toEqual({
      key: 'workbench.errors.provider_rate_limited',
    });
  });

  it('says nothing of an error the API did not name', () => {
    expect(workbenchRefusal(refused({ code: 'radio_instance_full' }))).toBeNull();
    expect(workbenchRefusal(refused('Not found', 404))).toBeNull();
    expect(workbenchRefusal(new Error('network down'))).toBeNull();
    expect(workbenchRefusal(undefined)).toBeNull();
  });
});
