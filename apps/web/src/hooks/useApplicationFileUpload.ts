'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources, type ApplicationResource } from '@/lib/application-resources';
import type { ApplicationCommandStatus } from '@/types/application-commands';

export type UploadMode = 'idle' | 'sending' | 'accepted' | 'uncertain';
export interface FileUploadDefinition<S extends { max_file_size_bytes: number }> {
  operationId: string;
  resource: ApplicationResource;
  resources?: readonly ApplicationResource[];
  select: (status: ApplicationCommandStatus) => S | null;
  endpoint: (commandId: string, selection: S) => string;
  accept: (value: unknown, commandId: string, selection: S) => { cacheRefreshPending: boolean; details?: unknown } | null;
}

/** Local bytes belong to one account/command lifetime; confirm() is the sole sender. */
export function useApplicationFileUpload<S extends { max_file_size_bytes: number }>(
  status: ApplicationCommandStatus,
  checkResult: () => Promise<void>,
  definition: FileUploadDefinition<S>
) {
  const { user } = useAuth();
  const scopeKey = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { isCurrent, lifetime } = useApplicationAccountLifetime(scopeKey);
  const [file, setFile] = useApplicationAccountState<File | null>(scopeKey, null);
  const [mode, setMode] = useApplicationAccountState<UploadMode>(scopeKey, 'idle');
  const [progress, setProgress] = useApplicationAccountState(scopeKey, 0);
  const [cacheRefreshPending, setCacheRefreshPending] = useApplicationAccountState(scopeKey, false);
  const [acceptedDetails, setAcceptedDetails] = useApplicationAccountState<unknown>(scopeKey, null);
  const request = useRef<XMLHttpRequest | null>(null);
  const started = useRef(false);
  const selection = definition.select(status);
  const waiting = status.operation_id === definition.operationId && status.phase === 'waiting' &&
    status.interaction?.kind === 'device';
  useEffect(() => {
    started.current = false;
    return () => { request.current?.abort(); request.current = null; };
  }, [lifetime]);
  const choose = useCallback((value: File | null) => {
    if (isCurrent() && waiting && !started.current) setFile(value);
  }, [isCurrent, waiting, setFile]);
  const confirm = useCallback((onAccepted?: () => void) => {
    const deadline = Date.parse(status.expires_at);
    if (!isCurrent() || !user?.id || !waiting || !selection || !file || started.current ||
      file.size > selection.max_file_size_bytes || !Number.isFinite(deadline) || deadline <= Date.now()) return;
    started.current = true;
    setMode('sending');
    const xhr = new XMLHttpRequest(); request.current = xhr;
    const uncertain = () => { if (isCurrent()) setMode('uncertain'); };
    xhr.timeout = 120_000;
    xhr.withCredentials = true;
    xhr.upload.onprogress = event => {
      if (isCurrent() && event.lengthComputable && event.total > 0)
        setProgress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onerror = uncertain; xhr.ontimeout = uncertain; xhr.onabort = uncertain;
    xhr.onload = () => {
      if (!isCurrent()) return;
      try {
        const receipt = xhr.status === 200
          ? definition.accept(JSON.parse(xhr.responseText), status.command_id, selection) : null;
        if (!receipt) { uncertain(); return; }
        setMode('accepted'); setFile(null); setProgress(100);
        setCacheRefreshPending(receipt.cacheRefreshPending);
        setAcceptedDetails(receipt.details ?? null);
        onAccepted?.();
        publishApplicationResources(user.id, new Set(definition.resources ?? [definition.resource]));
        void checkResult();
      } catch { uncertain(); }
    };
    const data = new FormData(); data.append('file', file);
    try {
      xhr.open('POST', definition.endpoint(status.command_id, selection));
      xhr.setRequestHeader('x-lia-file-confirmed', 'true');
      xhr.send(data);
    } catch { uncertain(); }
  }, [isCurrent, user, waiting, selection, file, status.command_id, status.expires_at,
    setMode, setFile, setProgress, setCacheRefreshPending, setAcceptedDetails, checkResult, definition]);
  return { scopeKey, selection, file, mode, progress, waiting, cacheRefreshPending, acceptedDetails, choose, confirm };
}
