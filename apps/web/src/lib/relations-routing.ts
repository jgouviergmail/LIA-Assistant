/** Preserve existing URLs; arbitrary SMS sender labels use authenticated query readers. */
const RESERVED_NAMES = new Set(['settings', 'overview-scope', 'favorites', 'merges']);
export function relationReadEndpoint(name: string, section?: 'context' | 'debrief'): string {
  const encoded = encodeURIComponent(name);
  if (name.includes('/') || RESERVED_NAMES.has(name)) {
    return `/relations/lookup/person${section ? `/${section}` : ''}?name=${encoded}`;
  }
  return `/relations/${encoded}${section ? `/${section}` : ''}`;
}
export function relationQuerySeparator(endpoint: string): '&' | '?' {
  return endpoint.includes('?') ? '&' : '?';
}
