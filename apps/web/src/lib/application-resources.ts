import type { ApplicationStateChange } from '@/types/application-state';

export type ApplicationResource = ApplicationStateChange['resources'][number];
interface Listener { ownerId: string; resource: ApplicationResource; read: () => void }
const listeners = new Set<Listener>();

/** Invalidations initiate authenticated reads; this registry executes no command. */
export function subscribeApplicationResource(ownerId: string, resource: ApplicationResource, read: () => void) {
  const listener = { ownerId, resource, read };
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function publishApplicationResources(ownerId: string, resources: ReadonlySet<ApplicationResource>) {
  for (const listener of listeners) {
    if (listener.ownerId === ownerId && resources.has(listener.resource)) listener.read();
  }
}
