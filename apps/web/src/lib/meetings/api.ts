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
  MeetingBulkDeleteResponse,
  MeetingDetail,
  MeetingListResponse,
  MeetingPatchRequest,
  MeetingPreferences,
  MeetingPreferencesUpdate,
  MeetingReformatRequest,
  MeetingReformatResponse,
  MeetingStartRequest,
  MeetingStartResponse,
  MeetingStopRequest,
  MeetingTemplate,
  MeetingTemplateCreate,
  MeetingTemplateListResponse,
  MeetingTemplateUpdate,
  MeetingTemplateBulkDeleteResponse,
  MeetingTemplateBulkDuplicateResponse,
  TemplateRefsRequest,
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

  /** Write the minutes again with another template, in place or as new minutes (ADR-259). */
  reformat: (id: string, request: MeetingReformatRequest) =>
    apiClient.post<MeetingReformatResponse>(`${BASE}/${id}/reformat`, request),

  patch: (id: string, request: MeetingPatchRequest) =>
    apiClient.patch<MeetingDetail>(`${BASE}/${id}`, request),

  resetReport: (id: string) => apiClient.post<MeetingDetail>(`${BASE}/${id}/report/reset`),

  email: (id: string) => apiClient.post<MeetingDetail>(`${BASE}/${id}/email`),

  deleteTranscript: (id: string) => apiClient.delete<MeetingDetail>(`${BASE}/${id}/transcript`),

  remove: (id: string) => apiClient.delete<void>(`${BASE}/${id}`),

  /** Delete several meetings; the server answers every id (deleted or skipped with a code). */
  bulkDelete: (ids: string[]) =>
    apiClient.post<MeetingBulkDeleteResponse>(`${BASE}/bulk-delete`, { ids }),

  /** The library: every built-in (localized) plus the user's own (ADR-259). */
  templates: () => apiClient.get<MeetingTemplateListResponse>(`${BASE}/templates`),

  template: (ref: string) => apiClient.get<MeetingTemplate>(`${BASE}/templates/${ref}`),

  createTemplate: (request: MeetingTemplateCreate) =>
    apiClient.post<MeetingTemplate>(`${BASE}/templates`, request),

  updateTemplate: (ref: string, request: MeetingTemplateUpdate) =>
    apiClient.put<MeetingTemplate>(`${BASE}/templates/${ref}`, request),

  deleteTemplate: (ref: string) => apiClient.delete<void>(`${BASE}/templates/${ref}`),
  /** Add several templates to « My templates »: each ref created or skipped with a code. */
  bulkDuplicateTemplates: (request: TemplateRefsRequest) =>
    apiClient.post<MeetingTemplateBulkDuplicateResponse>(
      `${BASE}/templates/bulk-duplicate`,
      request
    ),
  /** Delete several user templates; says whether the default-format preference was reset. */
  bulkDeleteTemplates: (request: TemplateRefsRequest) =>
    apiClient.post<MeetingTemplateBulkDeleteResponse>(`${BASE}/templates/bulk-delete`, request),

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
