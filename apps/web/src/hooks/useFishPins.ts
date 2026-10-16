'use client';

/**
 * The public Fish Audio voices the instance pinned (ADR-345 amendment 2026-10-14):
 * ONE list for every voice slot, kept by the server.
 *
 * A pin is an act of its own — immediate, filed in the admin audit log with the
 * administrator's attestation — never part of a slot's save. Every act answers
 * with the list as the server now holds it, which the hook adopts: two
 * administrators may pin at once, and the server decides what the list holds.
 */

import { useCallback } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import { VOICE_LIBRARY_ENDPOINT } from '@/hooks/useVoiceLibrary';
import apiClient from '@/lib/api-client';
import type { PinnedVoices } from '@/types/voice-library';

export const FISH_PINS_ENDPOINT = `${VOICE_LIBRARY_ENDPOINT}/pins`;

export interface UseFishPins {
  /** The list and its ceiling, once read. */
  pins: PinnedVoices | undefined;
  loading: boolean;
  error: Error | null;
  /** Pin a voice under the administrator's attestation (refused without it). */
  pin: (voiceId: string, attested: boolean) => Promise<void>;
  /** Unpin a voice (refused while a voice slot speaks with it). */
  unpin: (voiceId: string) => Promise<void>;
}

/**
 * The shared pins, read while `enabled`.
 *
 * @param enabled - Whether the list is wanted (a dialog open on a Fish Audio slot).
 */
export function useFishPins(enabled: boolean): UseFishPins {
  const { data, loading, error, setData } = useApiQuery<PinnedVoices>(FISH_PINS_ENDPOINT, {
    componentName: 'FishPinnedVoices',
    enabled,
    deps: [enabled],
  });

  const pin = useCallback(
    async (voiceId: string, attested: boolean): Promise<void> => {
      setData(await apiClient.put<PinnedVoices>(`${FISH_PINS_ENDPOINT}/${voiceId}`, { attested }));
    },
    [setData]
  );

  const unpin = useCallback(
    async (voiceId: string): Promise<void> => {
      setData(await apiClient.delete<PinnedVoices>(`${FISH_PINS_ENDPOINT}/${voiceId}`));
    },
    [setData]
  );

  return { pins: data, loading, error, pin, unpin };
}
