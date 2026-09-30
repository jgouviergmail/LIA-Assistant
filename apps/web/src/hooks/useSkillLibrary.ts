/**
 * The skill library's reads and acts (ADR-327).
 *
 * Two reads follow the screen — the portal's answer to the debounced search
 * text, and the installed skills with their update verdicts — and four acts
 * are called on demand: read a skill before installing it, install it, read
 * its next version, update it. Every call goes through `api-client` (the BFF
 * cookie), and a refusal reaches the caller as the `ApiError` whose
 * `detail.code` `lib/skill-library/errors.ts` turns into a sentence.
 */
import { useCallback } from 'react';

import apiClient from '@/lib/api-client';
import type {
  LibraryInstalledResponse,
  LibraryInstallRequest,
  LibraryInstallResponse,
  LibraryPreviewAnswer,
  LibraryPreviewQuery,
  LibrarySearchResponse,
  LibraryUpdatePreview,
} from '@/lib/skill-library/types';

import { useApiQuery } from './useApiQuery';

const BASE = '/skill-library';

/** Shortest search text the API accepts (`SKILL_LIBRARY_QUERY_MIN_CHARS`). */
export const LIBRARY_QUERY_MIN_CHARS = 2;

/**
 * The portal's answer to a search text — read only once the text is long enough,
 * and read again when `revision` moves (an install changes what is marked installed).
 */
export function useLibrarySearch(query: string, revision = 0) {
  const text = query.trim();
  return useApiQuery<LibrarySearchResponse>(`${BASE}/search`, {
    componentName: 'SkillLibrarySearch',
    enabled: text.length >= LIBRARY_QUERY_MIN_CHARS,
    params: { q: text },
    deps: [revision],
  });
}

/** The skills installed from a library, each with its update verdict. */
export function useLibraryInstalled(enabled: boolean) {
  return useApiQuery<LibraryInstalledResponse>(`${BASE}/installed`, {
    componentName: 'SkillLibraryInstalled',
    enabled,
  });
}

/** The four acts, each one request; the caller owns its busy state. */
export function useLibraryActions() {
  const preview = useCallback(
    (query: LibraryPreviewQuery) =>
      apiClient.get<LibraryPreviewAnswer>(`${BASE}/preview`, {
        params: { ...query },
      }),
    []
  );
  const install = useCallback(
    (request: LibraryInstallRequest) =>
      apiClient.post<LibraryInstallResponse>(`${BASE}/install`, request),
    []
  );
  const updatePreview = useCallback(
    (skillId: string) =>
      apiClient.get<LibraryUpdatePreview>(
        `${BASE}/installed/${encodeURIComponent(skillId)}/update`
      ),
    []
  );
  const update = useCallback(
    (skillId: string, commitSha: string) =>
      apiClient.post<LibraryInstallResponse>(
        `${BASE}/installed/${encodeURIComponent(skillId)}/update`,
        { commit_sha: commitSha }
      ),
    []
  );
  return { preview, install, updatePreview, update };
}
