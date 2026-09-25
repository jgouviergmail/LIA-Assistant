/**
 * Which model a call ran on, as the panel names it (B8, 2026-09-24).
 *
 * The panel showed only the name the PROVIDER answered under. When a provider
 * resolves an alias (a retired DeepSeek name) or answers under a dated
 * snapshot, that is a model nobody configured: the row could not be matched
 * with the admin screen. The configured name leads; the served one follows only
 * when it differs.
 */

import { describe, expect, it } from 'vitest';

import { callModel } from '../call-model';

describe('callModel', () => {
  it('names the configured model and the one the provider served under', () => {
    expect(
      callModel({ model_name: 'deepseek-flash', requested_model: 'deepseek-v4-flash' })
    ).toEqual({ name: 'deepseek-v4-flash', servedAs: 'deepseek-flash' });
  });

  it('names one model when both agree', () => {
    expect(callModel({ model_name: 'qwen3.5-plus', requested_model: 'qwen3.5-plus' })).toEqual({
      name: 'qwen3.5-plus',
      servedAs: null,
    });
  });

  it('falls back to the reported name when the request named none', () => {
    // Embeddings, and every payload recorded before the field existed.
    expect(callModel({ model_name: 'gemini-embedding-001' })).toEqual({
      name: 'gemini-embedding-001',
      servedAs: null,
    });
    expect(callModel({ model_name: 'x', requested_model: null })).toEqual({
      name: 'x',
      servedAs: null,
    });
  });

  it('does not call « unknown » a served name', () => {
    // A failed call reports nothing; its row carries the requested model.
    expect(callModel({ model_name: 'unknown', requested_model: 'gpt-6-luna' })).toEqual({
      name: 'gpt-6-luna',
      servedAs: null,
    });
  });
});
