/**
 * Rehydrating interactive widgets from conversation history.
 *
 * Before this, the registry was filled by the live SSE stream alone: a
 * conversation opened from history resolved every widget sentinel to nothing
 * and rendered an error box. Measured on the real production message content:
 * two grey placeholders, zero iframes.
 */

import { describe, it, expect } from 'vitest';

import { collectHistoryWidgets, mergeRegistryWithHistory } from '../message-widgets';
import type { Message, RegistryItem } from '@/types/chat';

function item(id: string, extra: Partial<RegistryItem> = {}): RegistryItem {
  return {
    id,
    type: 'SKILL_APP',
    payload: { skill_name: 'interactive-map', frame_url: 'https://x' },
    meta: { source: 'skill', timestamp: '2026-07-21T09:13:00Z' },
    ...extra,
  };
}

function message(id: string, widgets?: Record<string, RegistryItem>): Message {
  return {
    id,
    content: '<p>x</p>',
    role: 'assistant',
    timestamp: new Date('2026-07-21T09:13:00Z'),
    ...(widgets ? { metadata: { run_id: 'r', widgets } } : {}),
  } as Message;
}

describe('collectHistoryWidgets', () => {
  it('collects widgets across several messages', () => {
    const messages = [
      message('m1', { skill_app_a: item('skill_app_a') }),
      message('m2'),
      message('m3', { mcp_app_b: item('mcp_app_b', { type: 'MCP_APP' }) }),
    ];
    expect(Object.keys(collectHistoryWidgets(messages)).sort()).toEqual([
      'mcp_app_b',
      'skill_app_a',
    ]);
  });

  it('returns an empty map when no message carries a widget', () => {
    expect(collectHistoryWidgets([message('m1'), message('m2')])).toEqual({});
  });

  it('ignores a malformed widgets field instead of throwing', () => {
    const broken = {
      id: 'm',
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      metadata: { widgets: 'nope' },
    } as unknown as Message;
    expect(collectHistoryWidgets([broken])).toEqual({});
  });
});

describe('mergeRegistryWithHistory', () => {
  it('makes a history widget resolvable when the live registry is empty (the reload case)', () => {
    const messages = [message('m1', { skill_app_a: item('skill_app_a') })];
    const merged = mergeRegistryWithHistory({}, messages);
    expect(merged.skill_app_a).toBeDefined();
    expect(merged.skill_app_a.type).toBe('SKILL_APP');
  });

  it('lets the live registry win on a conflicting id (the current turn is the truth)', () => {
    const live = { skill_app_a: item('skill_app_a', { payload: { fresh: true } }) };
    const messages = [
      message('m1', { skill_app_a: item('skill_app_a', { payload: { fresh: false } }) }),
    ];
    expect(mergeRegistryWithHistory(live, messages).skill_app_a.payload).toEqual({ fresh: true });
  });

  it('returns the live registry BY IDENTITY when history adds nothing (no needless re-render)', () => {
    const live = { skill_app_a: item('skill_app_a') };
    expect(mergeRegistryWithHistory(live, [message('m1')])).toBe(live);
  });
});
