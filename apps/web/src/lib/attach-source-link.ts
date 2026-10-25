/**
 * The chat's `?attach=<kind>:<id>` deep link — pure, so a page can build it
 * without the client that makes the copy (owner request 2026-10-24).
 */

export type AttachSourceKind = 'bookmark' | 'generated';

export interface AttachSource {
  kind: AttachSourceKind;
  id: string;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** `<kind>:<id>` — the value of `?attach=`. */
export function formatAttachSource(source: AttachSource): string {
  return `${source.kind}:${source.id}`;
}

/** The source a `?attach=` value names, or null when it names nothing valid. */
export function parseAttachSource(value: string | null | undefined): AttachSource | null {
  const [kind, id, ...rest] = (value ?? '').split(':');
  if (rest.length > 0 || !id || !UUID.test(id)) return null;
  return kind === 'bookmark' || kind === 'generated' ? { kind, id } : null;
}
