'use client';
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { photoFile, renderPhoto, type PhotoFormat, type PhotoImage } from './photo-export';
import type { PhotoScene } from './photo-projection';

/**
 * The object URL of an encoded still, alive exactly while its one owner (this hook)
 * subscribes. A hidden panel unsubscribes, revoking it; a reveal subscribes again with a
 * fresh URL, so a visible preview or Download link never points at a revoked URL.
 */
class ObjectUrl {
  private url: string | null = null;
  constructor(private blob: Blob) {}
  getSnapshot = (): string | null => this.url;
  subscribe = (listener: () => void): (() => void) => {
    const url = URL.createObjectURL(this.blob);
    this.url = url;
    listener();
    return () => {
      this.url = null;
      URL.revokeObjectURL(url);
    };
  };
}
const NO_URL = {
  getSnapshot: (): string | null => null,
  subscribe: () => () => {},
};
interface Encoded extends PhotoImage {
  file: File;
  url: ObjectUrl;
}
export interface PhotoPreview extends PhotoImage {
  file: File;
  url: string;
}
export function usePhotoPreview(ownerId: string, scene: PhotoScene, format: PhotoFormat) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [attempt, setAttempt] = useState(0);
  const request = useMemo(() => ({ scene, format, attempt }), [scene, format, attempt]);
  const [state, setState] = useState<{
    settled: typeof request | null;
    encoded: Encoded | null;
    error: boolean;
  }>({ settled: null, encoded: null, error: false });
  const settled = state.settled;
  useEffect(() => {
    // A reveal re-runs effects: a request that already settled is never encoded twice.
    if (settled === request) return;
    let alive = true;
    const controller = new AbortController();
    // StrictMode withdraws its first setup synchronously. Do not allocate an
    // uncancellable browser encoder for an effect that has already ended.
    void Promise.resolve()
      .then(() =>
        alive && isCurrent() ? renderPhoto(request.scene, request.format, controller.signal) : null
      )
      .then(image => {
        if (!image || !alive || !isCurrent()) return;
        const encoded = { ...image, file: photoFile(image), url: new ObjectUrl(image.blob) };
        setState({ settled: request, encoded, error: false });
      })
      .catch(() => {
        if (alive && isCurrent())
          setState(previous => ({ ...previous, settled: request, error: true }));
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [request, settled, isCurrent]);
  const lease = state.encoded?.url ?? NO_URL;
  const url = useSyncExternalStore(lease.subscribe, lease.getSnapshot, NO_URL.getSnapshot);
  const loading = settled !== request;
  const preview = useMemo<PhotoPreview | null>(() => {
    if (!state.encoded || !url) return null;
    const { url: _lease, ...image } = state.encoded;
    return { ...image, url };
  }, [state.encoded, url]);
  return {
    preview,
    loading,
    error: !loading && state.error,
    isCurrent,
    retry: () => setAttempt(value => value + 1),
  };
}
