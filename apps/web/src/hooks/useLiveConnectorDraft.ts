'use client';

/**
 * The draft of a live connector's settings as the settings form edits it
 * (ADR-299; wave 2 A10; owner decisions 2026-09-19): choosing a model IS
 * choosing its provider, and a model switched to comes back with what it
 * REMEMBERS — its voice, its thinking level, its two durations — so a voice
 * chosen for a model survives any number of switches; a model never set up
 * takes the provider's first voice and the instance's default durations. The
 * thinking level follows the chosen model's ladder (kept when on it, else the
 * first rung), and the form is dirty when anything differs from what is
 * stored. No JSX here: the rules are testable without a select.
 */
import { useState } from 'react';

import { LIVE_PORTAL_VOICE } from '@/lib/live/providers';
import type {
  LiveConnectorResponse,
  LiveConnectorSettings,
  LiveDurationBounds,
  LiveModel,
  LiveModelSettings,
  LiveVoicesResponse,
} from '@/lib/live/types';

export type LiveConnectorDraft = LiveConnectorSettings & { provider: string };

/** The instance defaults a model without stored durations starts from. */
export interface LiveDurationDefaults {
  idle_timeout_seconds: number;
  session_max_minutes: number;
}

/**
 * What the API publishes about the two durations because it enforces it
 * (ADR-184): the defaults, the bounds of each, and the value meaning « no
 * limit » — allowed BELOW the minimum, the gap between the two refused.
 */
export interface LiveDurationRules {
  defaults: LiveDurationDefaults;
  idle_bounds: LiveDurationBounds;
  session_bounds: LiveDurationBounds;
  unlimited: number;
  /** The most a per-session spend ceiling may be (euros); the ceiling itself is optional. */
  budget_max: number;
}

/** A ceiling the API accepts: none, or a positive amount within the bound. */
export function budgetAllowed(value: number | null, max: number): boolean {
  return value === null || (Number.isFinite(value) && value > 0 && value <= max);
}

/** A duration the API accepts: « no limit », or within the bounds. */
export function durationAllowed(
  value: number,
  bounds: LiveDurationBounds,
  unlimited: number
): boolean {
  return value === unlimited || (value >= bounds.min && value <= bounds.max);
}

/** What a provider's connector remembers of one model, or nothing. */
export type LiveModelLookup = (provider: string, model: string) => LiveModelSettings | undefined;

/** The level a model offers for a draft: the current one when on the ladder, else the first. */
export function levelFor(levels: readonly string[], current: string | null): string | null {
  if (levels.length === 0) return null;
  return current && levels.includes(current) ? current : levels[0];
}

/** `provider|model` — the one value a grouped select carries. */
export function modelKey(provider: string, model: string): string {
  return `${provider}|${model}`;
}

export interface UseLiveConnectorDraftReturn {
  draft: LiveConnectorDraft;
  /** The voice the form shows: the draft's, else the listing's first. */
  voice: string;
  selectedModel: LiveModel | undefined;
  /** The chosen model's ladder (empty: no level to choose). */
  levels: readonly string[];
  dirty: boolean;
  /** Each duration as the API would take it; a refused one is shown, never sent. */
  idleAllowed: boolean;
  sessionAllowed: boolean;
  /** The ceiling as the API would take it (none, or within the bound). */
  budgetAllowed: boolean;
  /** What a save sends — `null` while no voice can be named or a duration is off the rules. */
  toSave: LiveConnectorSettings | null;
  chooseModelKey: (key: string) => void;
  chooseVoice: (voice: string) => void;
  chooseLevel: (level: string) => void;
  chooseIdleTimeout: (seconds: number) => void;
  chooseSessionMax: (minutes: number) => void;
  chooseBudget: (eur: number | null) => void;
}

/** What a draft becomes when a model is chosen: its remembered settings, else the defaults. */
export function draftForModel(
  draft: LiveConnectorDraft,
  model: LiveModel,
  remembered: LiveModelSettings | undefined,
  rules: LiveDurationRules,
  budgetOf: (provider: string) => number | null
): LiveConnectorDraft {
  const sameProvider = model.provider === draft.provider;
  return {
    ...draft,
    provider: model.provider,
    model: model.name,
    // A portal-voiced model (an agent) takes the sentinel; otherwise a
    // remembered voice always wins, within a provider the current voice
    // carries over, across providers the listing's first is taken.
    voice: model.capabilities.portal_voice
      ? LIVE_PORTAL_VOICE
      : (remembered?.voice ?? (sameProvider ? draft.voice : '')),
    thinking_level: remembered?.thinking_level ?? draft.thinking_level,
    idle_timeout_seconds: remembered?.idle_timeout_seconds ?? rules.defaults.idle_timeout_seconds,
    session_max_minutes: remembered?.session_max_minutes ?? rules.defaults.session_max_minutes,
    // Another provider's connector keeps its own ceiling.
    session_budget_eur: sameProvider ? draft.session_budget_eur : budgetOf(model.provider),
  };
}

/** Whether anything of the draft differs from what the connector stores. */
export function isDraftDirty(
  draft: LiveConnectorDraft,
  voice: string,
  connector: LiveConnectorResponse
): boolean {
  const stored = connector.settings;
  return (
    draft.provider !== connector.provider ||
    draft.model !== stored.model ||
    voice !== stored.voice ||
    draft.thinking_level !== stored.thinking_level ||
    draft.idle_timeout_seconds !== stored.idle_timeout_seconds ||
    draft.session_max_minutes !== stored.session_max_minutes ||
    draft.session_budget_eur !== stored.session_budget_eur
  );
}

export function useLiveConnectorDraft(
  connector: LiveConnectorResponse,
  models: readonly LiveModel[],
  voices: LiveVoicesResponse | undefined,
  lookup: LiveModelLookup,
  rules: LiveDurationRules,
  onProviderChange: (provider: string) => void,
  /** The stored ceiling of a provider's connector — the ceiling is the connector's, not a model's. */
  budgetOf: (provider: string) => number | null = () => null
): UseLiveConnectorDraftReturn {
  const [draft, setDraft] = useState<LiveConnectorDraft>({
    ...connector.settings,
    provider: connector.provider,
  });
  const findModel = (provider: string, name: string) =>
    models.find(m => m.provider === provider && m.name === name);
  const selectedModel = findModel(draft.provider, draft.model);
  const levels = selectedModel?.thinking_levels ?? [];
  const voice = draft.voice || voices?.voices[0]?.name || '';

  const choose = (patch: Partial<LiveConnectorDraft>) =>
    setDraft(previous => {
      const next = { ...previous, ...patch };
      const ladder = findModel(next.provider, next.model)?.thinking_levels ?? [];
      return { ...next, thinking_level: levelFor(ladder, next.thinking_level) };
    });

  /** A model comes back with what its connector remembers of it, else the defaults. */
  const chooseModelKey = (key: string) => {
    const [provider, ...rest] = key.split('|');
    const model = findModel(provider, rest.join('|'));
    if (!model) return;
    const next = draftForModel(draft, model, lookup(model.provider, model.name), rules, budgetOf);
    choose(next);
    if (model.provider !== draft.provider) onProviderChange(model.provider);
  };

  const dirty = isDraftDirty(draft, voice, connector);
  const idleAllowed = durationAllowed(
    draft.idle_timeout_seconds,
    rules.idle_bounds,
    rules.unlimited
  );
  const sessionAllowed = durationAllowed(
    draft.session_max_minutes,
    rules.session_bounds,
    rules.unlimited
  );
  const budgetOk = budgetAllowed(draft.session_budget_eur, rules.budget_max);
  const sendable = Boolean(voice) && idleAllowed && sessionAllowed && budgetOk;

  return {
    draft,
    voice,
    selectedModel,
    levels,
    dirty,
    idleAllowed,
    sessionAllowed,
    budgetAllowed: budgetOk,
    toSave: sendable
      ? {
          model: draft.model,
          voice,
          thinking_level: draft.thinking_level,
          idle_timeout_seconds: draft.idle_timeout_seconds,
          session_max_minutes: draft.session_max_minutes,
          session_budget_eur: draft.session_budget_eur,
        }
      : null,
    chooseModelKey,
    chooseVoice: chosen => choose({ voice: chosen }),
    chooseLevel: level => choose({ thinking_level: level }),
    chooseIdleTimeout: seconds => choose({ idle_timeout_seconds: seconds }),
    chooseSessionMax: minutes => choose({ session_max_minutes: minutes }),
    chooseBudget: eur => choose({ session_budget_eur: eur }),
  };
}
