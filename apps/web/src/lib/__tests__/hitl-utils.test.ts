/**
 * Unit tests for the HITL fallback-question generator and helpers.
 *
 * `generateFallbackHitlQuestion` is the client-side graceful-degradation path
 * used when backend LLM streaming of the confirmation question is unavailable.
 * It is a pure function driven by tool-name heuristics (category) and argument
 * extraction (target) — every branch is exercised here so the fallback wording
 * cannot silently drift.
 *
 * The `t` (TFunction) stub echoes the i18n key plus any interpolation params so
 * assertions pin both the branch taken AND the interpolated value.
 */
import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';

import {
  extractToolNames,
  formatActionArgs,
  generateFallbackHitlQuestion,
} from '../hitl-utils';
import type { ActionRequest } from '@/types/chat';

/** Echo stub: returns `key` alone, or `key {json-params}` when interpolation is used. */
const t = ((key: string, second?: unknown, third?: unknown): string => {
  const opts =
    third && typeof third === 'object'
      ? (third as Record<string, unknown>)
      : second && typeof second === 'object'
        ? (second as Record<string, unknown>)
        : undefined;
  return opts ? `${key} ${JSON.stringify(opts)}` : key;
}) as unknown as TFunction;

/** Build a minimal ActionRequest (description is required by the type). */
function ar(name: string, args: Record<string, unknown> = {}): ActionRequest {
  return { name, args, description: '' };
}

describe('generateFallbackHitlQuestion — empty / missing input', () => {
  it('falls back to hitl.default for an empty list', () => {
    expect(generateFallbackHitlQuestion([], t)).toBe('hitl.default');
  });

  it('falls back to hitl.default for a null-ish list', () => {
    expect(generateFallbackHitlQuestion(null as unknown as ActionRequest[], t)).toBe('hitl.default');
  });
});

describe('generateFallbackHitlQuestion — single action, category + target matrix', () => {
  it('search with a query target', () => {
    expect(generateFallbackHitlQuestion([ar('search_contacts', { query: 'Alice' })], t)).toBe(
      'hitl.search.with_query {"query":"Alice"}'
    );
  });

  it('search with search_query / q fallbacks', () => {
    expect(generateFallbackHitlQuestion([ar('find_places', { search_query: 'Paris' })], t)).toBe(
      'hitl.search.with_query {"query":"Paris"}'
    );
    expect(generateFallbackHitlQuestion([ar('search_web', { q: 'news' })], t)).toBe(
      'hitl.search.with_query {"query":"news"}'
    );
  });

  it('search without a target (generic)', () => {
    expect(generateFallbackHitlQuestion([ar('search_all', {})], t)).toBe('hitl.search.generic');
  });

  it('a "query"-named tool is categorized search but uses the generic target extractor', () => {
    // name includes 'query' → category 'search', but extractTarget only reads
    // query/search_query/q for names containing 'search'|'find'; here it falls
    // through to the generic name/target/id extractor.
    expect(generateFallbackHitlQuestion([ar('run_query', { name: 'X' })], t)).toBe(
      'hitl.search.with_query {"query":"X"}'
    );
  });

  it('delete with and without a target', () => {
    expect(generateFallbackHitlQuestion([ar('delete_event', { id: 'e1' })], t)).toBe(
      'hitl.delete.with_target {"target":"e1"}'
    );
    expect(generateFallbackHitlQuestion([ar('remove_item', {})], t)).toBe('hitl.delete.generic');
  });

  it('create with and without a target', () => {
    expect(generateFallbackHitlQuestion([ar('create_task', { name: 'Buy milk' })], t)).toBe(
      'hitl.create.with_target {"target":"Buy milk"}'
    );
    expect(generateFallbackHitlQuestion([ar('add_label', {})], t)).toBe('hitl.create.generic');
  });

  it('update with and without a target (edit/modify/save also map to update)', () => {
    expect(generateFallbackHitlQuestion([ar('update_contact', { name: 'Bob' })], t)).toBe(
      'hitl.update.with_target {"target":"Bob"}'
    );
    expect(generateFallbackHitlQuestion([ar('edit_profile', {})], t)).toBe('hitl.update.generic');
    expect(generateFallbackHitlQuestion([ar('save_draft', {})], t)).toBe('hitl.update.generic');
  });

  it('send with and without a target (to/recipient/email)', () => {
    expect(generateFallbackHitlQuestion([ar('send_email', { to: 'a@b.co' })], t)).toBe(
      'hitl.send.with_target {"to":"a@b.co"}'
    );
    expect(generateFallbackHitlQuestion([ar('send_email', { recipient: 'x@y.co' })], t)).toBe(
      'hitl.send.with_target {"to":"x@y.co"}'
    );
    expect(generateFallbackHitlQuestion([ar('send_sms', {})], t)).toBe('hitl.send.generic');
  });

  it('list and get categories', () => {
    expect(generateFallbackHitlQuestion([ar('list_events', {})], t)).toBe('hitl.list');
    expect(generateFallbackHitlQuestion([ar('get_weather', {})], t)).toBe('hitl.get');
    expect(generateFallbackHitlQuestion([ar('retrieve_doc', {})], t)).toBe('hitl.get');
    expect(generateFallbackHitlQuestion([ar('fetch_data', {})], t)).toBe('hitl.get');
  });

  it('generic action strips the _tool suffix and underscores', () => {
    expect(generateFallbackHitlQuestion([ar('do_something_tool', {})], t)).toBe(
      'hitl.generic_action {"action":"do something"}'
    );
  });
});

describe('generateFallbackHitlQuestion — multiple actions', () => {
  it('same category delete → plural delete', () => {
    const reqs = [ar('delete_a'), ar('remove_b')];
    expect(generateFallbackHitlQuestion(reqs, t)).toBe('hitl.delete.multiple {"count":2}');
  });

  it('same category create / update / send → plural variants', () => {
    expect(generateFallbackHitlQuestion([ar('create_a'), ar('add_b')], t)).toBe(
      'hitl.create.multiple {"count":2}'
    );
    expect(generateFallbackHitlQuestion([ar('update_a'), ar('edit_b')], t)).toBe(
      'hitl.update.multiple {"count":2}'
    );
    expect(generateFallbackHitlQuestion([ar('send_a'), ar('send_b')], t)).toBe(
      'hitl.send.multiple {"count":2}'
    );
  });

  it('same category with no dedicated plural key → multiple_similar', () => {
    expect(generateFallbackHitlQuestion([ar('get_a'), ar('fetch_b')], t)).toBe(
      'hitl.multiple_similar {"count":2}'
    );
  });

  it('mixed categories → generic multiple_actions', () => {
    expect(generateFallbackHitlQuestion([ar('delete_a'), ar('create_b')], t)).toBe(
      'hitl.multiple_actions {"count":2}'
    );
  });
});

describe('formatActionArgs', () => {
  it('pretty-prints serializable args', () => {
    expect(formatActionArgs({ a: 1, b: 'x' })).toBe('{\n  "a": 1,\n  "b": "x"\n}');
  });

  it('falls back to String() on a circular structure', () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(formatActionArgs(circular)).toBe('[object Object]');
  });
});

describe('extractToolNames', () => {
  it('maps action requests to their tool names', () => {
    expect(extractToolNames([ar('a'), ar('b'), ar('c')])).toEqual(['a', 'b', 'c']);
  });

  it('returns an empty array for no requests', () => {
    expect(extractToolNames([])).toEqual([]);
  });
});
