/**
 * The radio API behind the player (ADR-324), through the one API client — so
 * the session cookie, the native shell's header, the timeout and the 401/403
 * handling are the same as every other call. The audio of a segment comes back
 * as a blob: `media-src` allows `blob:`, never the API's own origin.
 */
import { apiClient } from '@/lib/api-client';

import type { RadioApi } from './controller';
import type { RadioPlayhead, RadioSessionState, RadioStartOptions } from './types';

/** The radio's endpoints, in one place. */
export const RADIO_ENDPOINTS = {
  sessions: '/radio/sessions',
  playhead: (sessionId: string) => `/radio/sessions/${encodeURIComponent(sessionId)}/playhead`,
  stop: (sessionId: string) => `/radio/sessions/${encodeURIComponent(sessionId)}/stop`,
  audio: (sessionId: string, seq: number) =>
    `/radio/sessions/${encodeURIComponent(sessionId)}/segments/${seq}/audio`,
  options: '/radio/options',
  preferences: '/radio/preferences',
  sources: '/radio/sources',
  sourcePreview: '/radio/sources/preview',
  source: (sourceId: string) => `/radio/sources/${encodeURIComponent(sourceId)}`,
  article: (articleId: string) => `/radio/articles/${encodeURIComponent(articleId)}`,
  budget: '/radio/budget',
  heard: '/radio/heard',
} as const;

export const radioApi: RadioApi = {
  start: (options: RadioStartOptions) =>
    apiClient.post<RadioSessionState>(RADIO_ENDPOINTS.sessions, options),
  report: (sessionId: string, playhead: RadioPlayhead) =>
    apiClient.post<RadioSessionState>(RADIO_ENDPOINTS.playhead(sessionId), playhead),
  stop: async (sessionId: string) => {
    await apiClient.post<unknown>(RADIO_ENDPOINTS.stop(sessionId));
  },
  fetchAudio: (sessionId: string, seq: number, signal: AbortSignal) =>
    apiClient.getBlob(RADIO_ENDPOINTS.audio(sessionId, seq), { signal }),
};
