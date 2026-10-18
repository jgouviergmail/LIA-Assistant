'use client';

import { useEffect, useRef, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { parseMapAdmission, reportRouteMapLoad, type MapGrant } from '@/lib/route-map-metering';
type Controller = { destroy(): void };
interface Options<Prepared, Mounted extends Controller> {
  purpose?: 'places';
  prepare(grant: MapGrant): Promise<Prepared>;
  mount(
    prepared: Prepared,
    element: HTMLDivElement,
    grant: MapGrant,
    onFailure: () => void,
    onConstruct: () => void
  ): Mounted;
}

/** Explicit admission, no bill until construction; every async step is owner fenced. */
export function usePaidMap<Prepared, Mounted extends Controller>(
  options: Options<Prepared, Mounted>
) {
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [reportFailed, setReportFailed] = useState(false);
  const element = useRef<HTMLDivElement>(null);
  const controller = useRef<Mounted | null>(null);
  const lifecycle = useRef(0);
  const pending = useRef<number | null>(null);
  const sequence = useRef(0);
  const reports = useRef(new Map<string, boolean>());
  const reporting = useRef(new Set<string>());
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    lifecycle.current += 1;
    return () => {
      lifecycle.current += 1;
      pending.current = null;
      request.current?.abort();
      controller.current?.destroy();
      controller.current = null;
    };
  }, []);

  async function report(token: string, generation: number) {
    if (reporting.current.has(token)) return;
    reporting.current.add(token);
    try {
      await reportRouteMapLoad(token);
      reports.current.delete(token);
    } catch {
      reports.current.set(token, true);
    } finally {
      reporting.current.delete(token);
      if (lifecycle.current === generation)
        setReportFailed([...reports.current.values()].some(Boolean));
    }
  }
  async function activate() {
    if (pending.current !== null || controller.current) return;
    const own = ++sequence.current,
      generation = lifecycle.current;
    const current = () => lifecycle.current === generation && sequence.current === own;
    pending.current = own;
    setState('loading');
    request.current = new AbortController();
    try {
      const raw = await apiClient.post<unknown>(
        `/connectors/google-maps/load-admissions${options.purpose ? '?purpose=places' : ''}`,
        undefined,
        { signal: request.current.signal, timeout: 10000 }
      );
      const grant = parseMapAdmission(raw, options.purpose === 'places');
      if (!grant) throw new Error('Invalid map admission');
      if (!current()) return;
      const prepared = await options.prepare(grant);
      if (!current() || !element.current) return;
      controller.current = options.mount(
        prepared,
        element.current,
        grant,
        () => {
          if (!current()) return;
          controller.current?.destroy();
          controller.current = null;
          setState('error');
        },
        () => {
          reports.current.set(grant.load_token, false);
          void report(grant.load_token, generation);
        }
      );
      setState('ready');
    } catch {
      if (current()) setState('error');
    } finally {
      if (pending.current === own) pending.current = null;
    }
  }
  function retryReport() {
    for (const [token, failed] of reports.current) {
      if (failed) void report(token, lifecycle.current);
    }
  }
  return { state, reportFailed, element, controller, activate, retryReport };
}
