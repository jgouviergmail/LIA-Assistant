'use client';

/**
 * useRadioSettings — the radio's published options and the listener's settings (ADR-324).
 *
 * `GET /radio/options` says what may be offered (published because the API
 * enforces it, ADR-184); `GET /radio/preferences` what the listener chose. A
 * save is a full replace with optimistic local state, and a choice the pure
 * helpers could not make — they return the same object — saves nothing.
 *
 * Saves are SERIALISED: one PUT in flight, and a change made meanwhile is sent
 * after it — the latest state only. Two full replaces racing could land in the
 * wrong order and leave the server on the older one; disabling the controls
 * instead would drop the click and the focus (apps/web CLAUDE.md). A failure
 * rolls back to the last state the server accepted.
 *
 * The voices offered are the engine's that a Configuration LLM slot names: when
 * that slot is saved, both reads start again (`radio_voices`), and a copy made
 * before yields to what the server reads since — a voice of the old engine,
 * sent back, would refuse every save.
 */

import { useCallback, useRef, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import { radioRefusalOf, type RadioWrite } from '@/lib/radio/errors';
import type { RadioOptions, RadioPreferences } from '@/lib/radio/types';
import { useResourceRevision } from '@/stores/revisionStore';

export interface UseRadioSettingsReturn {
  options: RadioOptions | null;
  preferences: RadioPreferences | null;
  /** First load only — monotone: once something is on screen, it stays (false once a read failed). */
  loading: boolean;
  /** A save is in flight (announce it; never unmount the form). */
  saving: boolean;
  /** Optimistic full replace; rolls back on a refusal and says why when the API named it. */
  save: (next: RadioPreferences) => Promise<RadioWrite<RadioPreferences>>;
}

const COMPONENT = 'useRadioSettings';

/** A copy of the settings, and the voices' revision it was made under. */
interface Revised {
  revision: number;
  value: RadioPreferences;
}

export function useRadioSettings(enabled = true): UseRadioSettingsReturn {
  const revision = useResourceRevision('radio_voices');
  const options = useApiQuery<RadioOptions>(RADIO_ENDPOINTS.options, {
    componentName: COMPONENT,
    enabled,
    deps: [revision],
  });
  const stored = useApiQuery<RadioPreferences>(RADIO_ENDPOINTS.preferences, {
    componentName: COMPONENT,
    enabled,
    deps: [revision],
  });
  // Derived-with-override (no state-sync effect): the server's copy is the
  // base; an optimistic save overrides it and rolls back on error — unless
  // the voices changed since it was made.
  const [override, setOverride] = useState<Revised | null>(null);
  const current = override?.revision === revision ? override.value : null;
  const preferences = current ?? stored.data ?? null;

  const { mutate, loading: saving } = useApiMutation<RadioPreferences, RadioPreferences>({
    method: 'PUT',
    componentName: COMPONENT,
  });
  // Written in handlers only, never read during render.
  const accepted = useRef<Revised | null>(null);
  const queued = useRef<RadioPreferences | null>(null);
  const flushing = useRef(false);

  const flush = useCallback(
    async (first: RadioPreferences, made: number): Promise<RadioWrite<RadioPreferences>> => {
      flushing.current = true;
      let next: RadioPreferences | null = first;
      try {
        while (next !== null) {
          queued.current = null;
          await mutate(RADIO_ENDPOINTS.preferences, next);
          accepted.current = { revision: made, value: next };
          next = queued.current;
        }
        return { ok: true, value: first };
      } catch (error) {
        queued.current = null;
        setOverride(accepted.current);
        return { ok: false, refusal: radioRefusalOf(error) };
      } finally {
        flushing.current = false;
      }
    },
    [mutate]
  );

  const save = useCallback(
    async (next: RadioPreferences): Promise<RadioWrite<RadioPreferences>> => {
      if (next === preferences) return { ok: true, value: next };
      setOverride({ revision, value: next });
      if (flushing.current) {
        queued.current = next;
        return { ok: true, value: next };
      }
      return flush(next, revision);
    },
    [preferences, flush, revision]
  );

  const missing = options.data === undefined || stored.data === undefined;
  const failed = missing && Boolean(options.error ?? stored.error);
  return {
    options: options.data ?? null,
    preferences,
    loading: missing && !failed,
    saving,
    save,
  };
}
