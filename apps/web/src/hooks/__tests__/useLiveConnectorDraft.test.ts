/**
 * useLiveConnectorDraft — the rules of the live settings form without a
 * select: a model comes back with what its connector REMEMBERS of it (voice,
 * level, durations — owner decision 2026-09-19), else a model of the same
 * provider keeps the current voice and takes the instance's default
 * durations; a model of ANOTHER provider switches the provider, drops the
 * voice (the new listing's first is taken) and tells the parent; the thinking
 * level follows the chosen model's ladder; a key naming no listed model
 * changes nothing; dirty compares with what is stored, durations included;
 * nothing is sent while no voice can be named.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { budgetAllowed, levelFor, modelKey, useLiveConnectorDraft } from '../useLiveConnectorDraft';
import type { LiveModelLookup } from '../useLiveConnectorDraft';
import type { LiveModelSettings, LiveVoicesResponse } from '@/lib/live/types';

const CAPABILITIES = {
  async_delegation: true,
  delivery_scheduling: true,
  reports_idle: false,
  cancels_on_interruption: true,
  configurable_vad: true,
  resumes: true,
  thinking: false,
  direct_tools: true,
  portal_voice: false,
  vendor_billed: false,
};
const MODELS = [
  { provider: 'gemini', name: 'g-live', thinking_levels: [], capabilities: CAPABILITIES },
  {
    provider: 'gemini',
    name: 'g-think',
    thinking_levels: ['low', 'high'],
    capabilities: CAPABILITIES,
  },
  { provider: 'openai', name: 'o-live', thinking_levels: [], capabilities: CAPABILITIES },
  {
    provider: 'elevenlabs',
    name: 'agent_0123456789abcdef',
    label: 'Assistant',
    thinking_levels: [],
    capabilities: { ...CAPABILITIES, portal_voice: true },
  },
];
const DEFAULTS = { idle_timeout_seconds: 60, session_max_minutes: 10 };
const RULES = {
  defaults: DEFAULTS,
  idle_bounds: { min: 5, max: 3600 },
  session_bounds: { min: 1, max: 240 },
  unlimited: 0,
  budget_max: 100,
};
const STORED = {
  model: 'g-live',
  voice: 'Kore',
  thinking_level: null,
  session_budget_eur: null,
  ...DEFAULTS,
};
const CONNECTOR = {
  provider: 'gemini',
  connector_type: 'gemini_live',
  status: 'active',
  settings: STORED,
  model_settings: { 'g-live': STORED },
  functionally_verified: true,
  capabilities: CAPABILITIES,
  active: true,
};
/** What the connectors remember: the stored model alone unless a test says more. */
const remembering =
  (table: Record<string, LiveModelSettings | undefined>): LiveModelLookup =>
  (provider, model) =>
    provider === 'gemini' ? table[model] : undefined;
const NOTHING_MORE = remembering({ 'g-live': STORED });
const voicesOf = (provider: string, names: string[]) => ({
  provider,
  voices: names.map(name => ({ name, characteristic: '' })),
  provenance: 'published' as const,
  published_at: null,
  source: null,
});

describe('useLiveConnectorDraft', () => {
  it('levelFor keeps a level on the ladder, else the first, and none off an empty ladder', () => {
    expect(levelFor([], 'high')).toBeNull();
    expect(levelFor(['low', 'high'], 'high')).toBe('high');
    expect(levelFor(['low', 'high'], 'medium')).toBe('low');
    expect(modelKey('gemini', 'g|x')).toBe('gemini|g|x');
  });

  it('starts clean from what is stored and follows the ladder of the model chosen', () => {
    const onProviderChange = vi.fn();
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore', 'Puck']),
        NOTHING_MORE,
        RULES,
        onProviderChange
      )
    );
    expect(result.current.dirty).toBe(false);
    expect(result.current.levels).toEqual([]);
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-think')));
    expect(result.current.draft.thinking_level).toBe('low');
    expect(result.current.voice).toBe('Kore');
    expect(result.current.dirty).toBe(true);
    act(() => result.current.chooseLevel('high'));
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-live')));
    // Back on a model without a ladder: the level goes, the form is clean again.
    expect(result.current.draft.thinking_level).toBeNull();
    expect(result.current.dirty).toBe(false);
    expect(onProviderChange).not.toHaveBeenCalled();
  });

  it("switching to another provider's model drops the voice, tells the parent, then takes the new listing's first", () => {
    const onProviderChange = vi.fn();
    let voices: ReturnType<typeof voicesOf> | undefined = voicesOf('gemini', ['Kore']);
    const { result, rerender } = renderHook(() =>
      useLiveConnectorDraft(CONNECTOR, MODELS, voices, NOTHING_MORE, RULES, onProviderChange)
    );
    act(() => result.current.chooseModelKey(modelKey('openai', 'o-live')));
    expect(onProviderChange).toHaveBeenCalledWith('openai');
    // The old listing is gone and the new one not yet here: nothing can be sent.
    voices = undefined;
    rerender();
    expect(result.current.voice).toBe('');
    expect(result.current.toSave).toBeNull();
    voices = voicesOf('openai', ['Marin', 'Cedar']);
    rerender();
    expect(result.current.voice).toBe('Marin');
    expect(result.current.toSave).toEqual({
      model: 'o-live',
      session_budget_eur: null,
      voice: 'Marin',
      thinking_level: null,
      ...DEFAULTS,
    });
    expect(result.current.draft.provider).toBe('openai');
    act(() => result.current.chooseVoice('Cedar'));
    expect(result.current.toSave?.voice).toBe('Cedar');
  });

  it('an agent (a portal-voiced model) takes the sentinel voice and is sendable with no listing (ADR-300 wave 4)', () => {
    const onProviderChange = vi.fn();
    let voices: LiveVoicesResponse | undefined = voicesOf('gemini', ['Kore']);
    const { result, rerender } = renderHook(() =>
      useLiveConnectorDraft(CONNECTOR, MODELS, voices, NOTHING_MORE, RULES, onProviderChange)
    );
    act(() => result.current.chooseModelKey(modelKey('elevenlabs', 'agent_0123456789abcdef')));
    expect(onProviderChange).toHaveBeenCalledWith('elevenlabs');
    // The portal's listing is empty by design; the sentinel is what the API knows.
    voices = {
      provider: 'elevenlabs',
      voices: [],
      provenance: 'portal' as const,
      published_at: null,
      source: null,
    };
    rerender();
    expect(result.current.voice).toBe('agent');
    expect(result.current.selectedModel?.capabilities.portal_voice).toBe(true);
    expect(result.current.toSave).toEqual({
      model: 'agent_0123456789abcdef',
      session_budget_eur: null,
      voice: 'agent',
      thinking_level: null,
      ...DEFAULTS,
    });
    // Back to a voiced model of the first provider: the remembered voice returns.
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-live')));
    expect(result.current.draft.voice).toBe('Kore');
  });

  it('a model switched back to comes back with the voice and durations it remembers', () => {
    // Owner decision 2026-09-19: the voice chosen for a model survives any
    // number of switches — the connector remembers each model beside the others.
    const lookup = remembering({
      'g-live': STORED,
      'g-think': {
        voice: 'Puck',
        thinking_level: 'high',
        idle_timeout_seconds: 0,
        session_max_minutes: 0,
      },
    });
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore', 'Puck']),
        lookup,
        RULES,
        vi.fn()
      )
    );
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-think')));
    expect(result.current.toSave).toEqual({
      model: 'g-think',
      session_budget_eur: null,
      voice: 'Puck',
      thinking_level: 'high',
      idle_timeout_seconds: 0,
      session_max_minutes: 0,
    });
    // Back on the stored model: its own voice and durations, the form clean.
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-live')));
    expect(result.current.voice).toBe('Kore');
    expect(result.current.draft.idle_timeout_seconds).toBe(DEFAULTS.idle_timeout_seconds);
    expect(result.current.dirty).toBe(false);
  });

  it('a model never set up takes the instance defaults, and a changed duration makes the form dirty', () => {
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore', 'Puck']),
        NOTHING_MORE,
        { ...RULES, defaults: { idle_timeout_seconds: 90, session_max_minutes: 15 } },
        vi.fn()
      )
    );
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-think')));
    expect(result.current.draft.idle_timeout_seconds).toBe(90);
    expect(result.current.draft.session_max_minutes).toBe(15);
    act(() => result.current.chooseModelKey(modelKey('gemini', 'g-live')));
    expect(result.current.dirty).toBe(false);
    act(() => result.current.chooseSessionMax(0));
    expect(result.current.dirty).toBe(true);
    expect(result.current.toSave?.session_max_minutes).toBe(0);
    act(() => result.current.chooseIdleTimeout(120));
    expect(result.current.toSave?.idle_timeout_seconds).toBe(120);
  });

  it('a duration between « no limit » and the minimum, or past the maximum, is shown refused and never sent', () => {
    // The bounds are published because they are enforced (ADR-184); a value
    // typed on the way to another one must not reach a 422.
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore']),
        NOTHING_MORE,
        RULES,
        vi.fn()
      )
    );
    act(() => result.current.chooseIdleTimeout(3));
    expect(result.current.idleAllowed).toBe(false);
    expect(result.current.toSave).toBeNull();
    act(() => result.current.chooseIdleTimeout(0));
    expect(result.current.idleAllowed).toBe(true);
    act(() => result.current.chooseSessionMax(241));
    expect(result.current.sessionAllowed).toBe(false);
    expect(result.current.toSave).toBeNull();
    act(() => result.current.chooseSessionMax(240));
    expect(result.current.toSave?.session_max_minutes).toBe(240);
  });

  it('ignores a key that names no listed model', () => {
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore']),
        NOTHING_MORE,
        RULES,
        vi.fn()
      )
    );
    act(() => result.current.chooseModelKey('nowhere|nothing'));
    expect(result.current.draft.model).toBe('g-live');
    expect(result.current.dirty).toBe(false);
  });
});

describe('the per-provider spend ceiling (ADR-300 wave 3)', () => {
  it('is optional, bounded, part of the save, and the OTHER provider keeps its own', () => {
    const budgetOf = (provider: string) => (provider === 'openai' ? 2.5 : null);
    const { result } = renderHook(() =>
      useLiveConnectorDraft(
        CONNECTOR,
        MODELS,
        voicesOf('gemini', ['Kore']),
        NOTHING_MORE,
        RULES,
        vi.fn(),
        budgetOf
      )
    );
    expect(result.current.dirty).toBe(false);
    expect(result.current.budgetAllowed).toBe(true);
    expect(result.current.toSave?.session_budget_eur).toBeNull();
    act(() => result.current.chooseBudget(1.5));
    expect(result.current.dirty).toBe(true);
    expect(result.current.toSave?.session_budget_eur).toBe(1.5);
    // Off the bound: shown refused, never sent.
    act(() => result.current.chooseBudget(101));
    expect(result.current.budgetAllowed).toBe(false);
    expect(result.current.toSave).toBeNull();
    act(() => result.current.chooseBudget(0));
    expect(result.current.budgetAllowed).toBe(false);
    act(() => result.current.chooseBudget(null));
    expect(result.current.budgetAllowed).toBe(true);
    // Switching to another provider's model brings THAT connector's ceiling.
    act(() => result.current.chooseModelKey(modelKey('openai', 'o-live')));
    expect(result.current.draft.session_budget_eur).toBe(2.5);
  });

  it('budgetAllowed: none, or a positive amount within the bound', () => {
    expect(budgetAllowed(null, 100)).toBe(true);
    expect(budgetAllowed(0.01, 100)).toBe(true);
    expect(budgetAllowed(100, 100)).toBe(true);
    expect(budgetAllowed(100.01, 100)).toBe(false);
    expect(budgetAllowed(0, 100)).toBe(false);
    expect(budgetAllowed(Number.NaN, 100)).toBe(false);
  });
});
