/** Execute the real service worker's handlers with synthetic Push API clients. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';
import { vi } from 'vitest';

const source = readFileSync(join(process.cwd(), 'public/firebase-messaging-sw.js'), 'utf8');

export interface WorkerEvent {
  data?: { json: () => unknown; text: () => string };
  notification?: { data: Record<string, string>; close: () => void };
  /** The notification action pressed; absent for a press on the body. */
  action?: string;
  waitUntil: (promise: Promise<unknown>) => void;
}

/** What the worker passes to `showNotification`. */
export interface ShownOptions {
  tag: string;
  data: Record<string, string>;
  actions?: { action: string; title: string }[];
}

/** The part of a fetch response the worker reads. */
export interface FetchAnswer {
  ok: boolean;
  json: () => Promise<unknown>;
}

export type WorkerFetch = (url: string, init: RequestInit) => Promise<FetchAnswer>;

/**
 * Load the worker in a fresh context.
 *
 * @param fetchImpl - What the worker's `fetch` answers (a refusal by default).
 * @returns The event emitter and the doubles the worker talks to.
 */
export function worker(
  fetchImpl: WorkerFetch = async () => ({ ok: false, json: async () => null })
) {
  const handlers = new Map<string, (event: WorkerEvent) => void>();
  const showNotification = vi.fn<(title: string, options: ShownOptions) => Promise<void>>(
    async () => {}
  );
  const client = {
    url: 'https://lia.test/en/dashboard',
    navigate: vi.fn(async (_url: string) => null),
    focus: vi.fn(async () => {}),
  };
  const openWindow = vi.fn(async (_url: string) => null);
  const output = { log: vi.fn(), error: vi.fn() };
  const fetch = vi.fn<WorkerFetch>(fetchImpl);
  runInNewContext(source, {
    self: {
      location: { origin: 'https://lia.test' },
      registration: { showNotification },
      addEventListener: (type: string, callback: (event: WorkerEvent) => void) =>
        handlers.set(type, callback),
    },
    clients: { matchAll: async () => [client], openWindow },
    fetch,
    URL,
    console: output,
  });
  async function emit(type: string, event: Omit<WorkerEvent, 'waitUntil'>) {
    const pending: Promise<unknown>[] = [];
    const handler = handlers.get(type);
    if (!handler) throw new Error('Missing worker handler');
    handler({
      ...event,
      waitUntil: promise => {
        pending.push(promise);
      },
    });
    await Promise.all(pending);
  }
  return { emit, showNotification, client, openWindow, output, fetch };
}
