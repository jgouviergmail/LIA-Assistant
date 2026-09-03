/**
 * Typed calls of the meetings API (ADR-258) — one place for every endpoint.
 *
 * Hooks and the recorder controller call these; nothing else spells a
 * `/meetings/...` path. Segments are the one exception: their raw-body PUT
 * lives in `segment-uploader.ts` because `apiClient` JSON-encodes bodies.
 */

import { apiClient, ApiError } from '@/lib/api-client';
import type {
  MeetingActionResponse,
  MeetingDetail,
  MeetingListResponse,
  MeetingPatchRequest,
  MeetingPreferences,
  MeetingPreferencesUpdate,
  MeetingStartRequest,
  MeetingStartResponse,
  MeetingStopRequest,
  MeetingTemplate,
  MeetingTemplateUpdate,
} from '@/types/meetings';

const BASE = '/meetings';

export const meetingsApi = {
  start: (request: MeetingStartRequest) => apiClient.post<MeetingStartResponse>(BASE, request),

  /** The live meeting, or `null` (the endpoint answers 204). */
  active: async (): Promise<MeetingDetail | null> => {
    const detail = await apiClient.get<MeetingDetail | null | undefined>(`${BASE}/active`);
    return detail ?? null;
  },

  list: (limit: number, offset: number) =>
    apiClient.get<MeetingListResponse>(BASE, { params: { limit, offset } }),

  detail: (id: string, includeTranscript = false) =>
    apiClient.get<MeetingDetail>(`${BASE}/${id}`, {
      params: includeTranscript ? { include_transcript: true } : undefined,
    }),

  stop: (id: string, request: MeetingStopRequest) =>
    apiClient.post<MeetingActionResponse>(`${BASE}/${id}/stop`, request),

  resume: (id: string) => apiClient.post<MeetingActionResponse>(`${BASE}/${id}/resume`),

  retry: (id: string) => apiClient.post<MeetingActionResponse>(`${BASE}/${id}/retry`),

  regenerate: (id: string) => apiClient.post<MeetingActionResponse>(`${BASE}/${id}/regenerate`),

  patch: (id: string, request: MeetingPatchRequest) =>
    apiClient.patch<MeetingDetail>(`${BASE}/${id}`, request),

  resetReport: (id: string) => apiClient.post<MeetingDetail>(`${BASE}/${id}/report/reset`),

  email: (id: string) => apiClient.post<MeetingDetail>(`${BASE}/${id}/email`),

  deleteTranscript: (id: string) => apiClient.delete<MeetingDetail>(`${BASE}/${id}/transcript`),

  remove: (id: string) => apiClient.delete<void>(`${BASE}/${id}`),

  template: () => apiClient.get<MeetingTemplate>(`${BASE}/template`),

  putTemplate: (request: MeetingTemplateUpdate) =>
    apiClient.put<MeetingTemplate>(`${BASE}/template`, request),

  resetTemplate: () => apiClient.delete<MeetingTemplate>(`${BASE}/template`),

  preferences: () => apiClient.get<MeetingPreferences>(`${BASE}/preferences`),

  putPreferences: (request: MeetingPreferencesUpdate) =>
    apiClient.put<MeetingPreferences>(`${BASE}/preferences`, request),
};

/** Relative endpoint of the PDF, for the browser to follow as a top-level GET. */
export function meetingPdfEndpoint(id: string): string {
  return `${BASE}/${id}/pdf`;
}

/**
 * The stable `code` the meetings API puts in `detail`, or `null`.
 *
 * Every refusal (409/413/429/502) carries `{ code }`; the frontend maps it to a
 * localized sentence instead of showing the server's words.
 */
export function meetingErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const detail = (error.data as { detail?: unknown } | undefined)?.detail;
  if (detail && typeof detail === 'object') {
    const code = (detail as { code?: unknown }).code;
    if (typeof code === 'string') return code;
  }
  return null;
}

/** The `missing` sequences a `segments_missing` refusal reports. */
export function missingSegmentsOf(error: unknown): number[] | null {
  if (!(error instanceof ApiError)) return null;
  const detail = (error.data as { detail?: unknown } | undefined)?.detail;
  const missing = (detail as { missing?: unknown } | undefined)?.missing;
  return Array.isArray(missing) && missing.every(n => typeof n === 'number')
    ? (missing as number[])
    : null;
}
