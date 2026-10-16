'use client';

/**
 * The instance's Fish Audio voice library (ADR-345): the account's own voices,
 * and the acts an administrator performs on them.
 *
 * A clone and a transcript upload recordings, so they leave through `fetch`
 * with a `FormData` body (the API client forces JSON); a refusal keeps its
 * status and its coded `detail` in an `ApiError`, which the section translates
 * by its code like every other refusal. Every act that changes the library
 * re-reads it: the server decides what a voice now is.
 */

import { useCallback } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import apiClient, { ApiError, apiEndpointUrl } from '@/lib/api-client';
import type {
  CloneRequest,
  DesignRequest,
  DesignResult,
  LibraryLanguage,
  LibraryVoice,
  VoiceLibrary,
} from '@/types/voice-library';

export const VOICE_LIBRARY_ENDPOINT = '/admin/voice/fishaudio/library';

async function postForm<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(apiEndpointUrl(`${VOICE_LIBRARY_ENDPOINT}${path}`), {
    method: 'POST',
    credentials: 'include',
    body,
  });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(`Voice library request failed (${response.status})`, response.status, data);
  }
  return data as T;
}

export interface UseVoiceLibrary {
  library: VoiceLibrary | undefined;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  clone: (request: CloneRequest) => Promise<LibraryVoice>;
  transcribe: (sample: File, language: LibraryLanguage | null) => Promise<string>;
  design: (request: DesignRequest) => Promise<DesignResult>;
  saveDesign: (candidateId: string, title: string) => Promise<LibraryVoice>;
  rename: (voiceId: string, title: string) => Promise<void>;
  remove: (voiceId: string) => Promise<void>;
}

export function useVoiceLibrary(): UseVoiceLibrary {
  const { data, loading, error, refetch } = useApiQuery<VoiceLibrary>(VOICE_LIBRARY_ENDPOINT, {
    componentName: 'AdminVoiceLibrarySection',
  });

  const clone = useCallback(
    async (request: CloneRequest): Promise<LibraryVoice> => {
      const body = new FormData();
      body.append('title', request.title);
      body.append('consent', request.consent ? 'true' : 'false');
      body.append('enhance_audio_quality', request.enhanceAudioQuality ? 'true' : 'false');
      request.samples.forEach(sample => body.append('samples', sample));
      request.texts.forEach(text => body.append('texts', text));
      const voice = await postForm<LibraryVoice>('/clone', body);
      await refetch();
      return voice;
    },
    [refetch]
  );

  const transcribe = useCallback(
    async (sample: File, language: LibraryLanguage | null): Promise<string> => {
      const body = new FormData();
      body.append('sample', sample);
      if (language) body.append('language', language);
      const { text } = await postForm<{ text: string }>('/transcript', body);
      return text;
    },
    []
  );

  const design = useCallback(
    (request: DesignRequest) =>
      apiClient.post<DesignResult>(`${VOICE_LIBRARY_ENDPOINT}/designs`, request),
    []
  );

  const saveDesign = useCallback(
    async (candidateId: string, title: string): Promise<LibraryVoice> => {
      const voice = await apiClient.post<LibraryVoice>(
        `${VOICE_LIBRARY_ENDPOINT}/designs/${candidateId}/save`,
        { title }
      );
      await refetch();
      return voice;
    },
    [refetch]
  );

  const rename = useCallback(
    async (voiceId: string, title: string): Promise<void> => {
      await apiClient.patch<void>(`${VOICE_LIBRARY_ENDPOINT}/${voiceId}`, { title });
      await refetch();
    },
    [refetch]
  );

  const remove = useCallback(
    async (voiceId: string): Promise<void> => {
      await apiClient.delete<void>(`${VOICE_LIBRARY_ENDPOINT}/${voiceId}`);
      await refetch();
    },
    [refetch]
  );

  return {
    library: data,
    loading,
    error,
    refetch,
    clone,
    transcribe,
    design,
    saveDesign,
    rename,
    remove,
  };
}
