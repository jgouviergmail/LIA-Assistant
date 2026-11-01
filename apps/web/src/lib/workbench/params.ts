/**
 * A workbench read's params as a stable key (ADR-369): the listings
 * (`useWorkbenchPage`) and the single reads (`useWorkbenchItem`) derive their
 * loading state from it, so a change of params is a new read, never the old
 * answer shown for it.
 */
import type { QueryParamValue } from '@/lib/api-client';

type QueryEntries = Array<[string, QueryParamValue]>;

/** The params as a stable string: undefined values dropped, names sorted. */
export function serialiseParams(params: Readonly<Record<string, QueryParamValue>>): string {
  const entries: QueryEntries = Object.entries(params)
    .filter(([, value]) => value !== undefined)
    .sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify(entries);
}

/** The params back from `serialiseParams` (this module wrote the string, from this type). */
export function paramsOf(serialised: string): Record<string, QueryParamValue> {
  return Object.fromEntries(JSON.parse(serialised) as QueryEntries);
}
