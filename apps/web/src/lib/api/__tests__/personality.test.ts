/**
 * Personality API client — every call that changes how LIA speaks.
 *
 * This module used to call `fetch` directly instead of going through
 * `apiClient`, which cost it three things the rest of the app gets for free:
 *
 * 1. **Session handling** — a 401 must eject to the localized login. Raw fetch
 *    threw `Error("Failed to fetch personalities: 401")` and the user stared at
 *    a broken settings panel until they reloaded.
 * 2. **A timeout** — `apiClient` arms `AbortSignal.timeout`; a raw fetch hangs
 *    for as long as the network lets it.
 * 3. **One error contract** — four of the eight functions hand-rolled their own
 *    `detail` reader (two handling the Pydantic list shape, two not, one
 *    interpolating the list straight into a string), and the other four never
 *    read the backend reason at all.
 *
 * These tests drive the module over a stubbed `fetch`, so they assert the real
 * request shape and the real error surface.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { ApiError } from '@/lib/api-client';
import {
  createPersonality,
  deletePersonality,
  fetchCurrentPersonality,
  fetchPersonalities,
  fetchPersonalitiesAdmin,
  translatePersonality,
  updateCurrentPersonality,
  updatePersonality,
} from '@/lib/api/personality';

const ORIGINAL_FETCH = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function respond(status: number, body: unknown): void {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(async () =>
    jsonResponse(status, body)
  );
}

function lastRequest(): { url: string; init: RequestInit } {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const call = mock.mock.calls.at(-1)!;
  return { url: String(call[0]), init: (call[1] ?? {}) as RequestInit };
}

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi.fn().mockImplementation(async () => jsonResponse(200, {}));
});

afterEach(() => {
  globalThis.fetch = ORIGINAL_FETCH;
});

describe('personality API — requests', () => {
  it('lists the active personalities', async () => {
    respond(200, { personalities: [{ code: 'warm' }] });

    await expect(fetchPersonalities()).resolves.toEqual({ personalities: [{ code: 'warm' }] });
    expect(lastRequest().url).toContain('/personalities');
  });

  it('reads the current preference', async () => {
    respond(200, { personality_code: 'warm' });

    await expect(fetchCurrentPersonality()).resolves.toEqual({ personality_code: 'warm' });
    expect(lastRequest().url).toContain('/personalities/current');
  });

  it('patches the current preference with the chosen code', async () => {
    respond(200, { personality_code: 'direct' });

    await updateCurrentPersonality({ personality_id: 'p-direct' });

    const { url, init } = lastRequest();
    expect(url).toContain('/personalities/current');
    expect(init.method).toBe('PATCH');
    expect(init.body).toBe('{"personality_id":"p-direct"}');
  });

  it('lists the admin view on its own endpoint', async () => {
    respond(200, []);

    await fetchPersonalitiesAdmin();

    expect(lastRequest().url).toContain('/personalities/admin');
  });

  it('creates through POST', async () => {
    respond(200, { id: 'p1' });

    await createPersonality({ code: 'warm', emoji: '🙂', title: 'Chaleureuse' } as never);

    const { url, init } = lastRequest();
    expect(url).toMatch(/\/personalities\/admin$/);
    expect(init.method).toBe('POST');
  });

  it('carries the propagate flag as a query parameter on update', async () => {
    respond(200, { id: 'p1' });

    await updatePersonality('p1', { title: 'Nouveau' } as never, false);

    const { url, init } = lastRequest();
    expect(url).toContain('/personalities/admin/p1');
    expect(url).toContain('propagate=false');
    expect(init.method).toBe('PATCH');
  });

  it('propagates translations by default', async () => {
    respond(200, { id: 'p1' });

    await updatePersonality('p1', { title: 'Nouveau' } as never);

    expect(lastRequest().url).toContain('propagate=true');
  });

  it('deletes through DELETE and resolves with nothing', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      async () => new Response(null, { status: 204 })
    );

    await expect(deletePersonality('p1')).resolves.toBeUndefined();
    expect(lastRequest().init.method).toBe('DELETE');
  });

  it('triggers auto-translation and returns the count', async () => {
    respond(200, { translations_created: 5, source_language: 'fr' });

    await expect(translatePersonality('p1')).resolves.toEqual({
      translations_created: 5,
      source_language: 'fr',
    });
    expect(lastRequest().url).toContain('/auto-translate');
  });
});

describe('personality API — one error contract for all eight calls', () => {
  const calls: [string, () => Promise<unknown>][] = [
    ['fetchPersonalities', () => fetchPersonalities()],
    ['fetchCurrentPersonality', () => fetchCurrentPersonality()],
    ['updateCurrentPersonality', () => updateCurrentPersonality({ personality_id: 'x' })],
    ['fetchPersonalitiesAdmin', () => fetchPersonalitiesAdmin()],
    ['createPersonality', () => createPersonality({ code: 'x' } as never)],
    ['updatePersonality', () => updatePersonality('p1', {} as never)],
    ['deletePersonality', () => deletePersonality('p1')],
    ['translatePersonality', () => translatePersonality('p1')],
  ];

  it.each(calls)('%s raises ApiError carrying the status and the body', async (_name, run) => {
    respond(409, { detail: 'code already taken' });

    const error = await run().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).data).toEqual({ detail: 'code already taken' });
  });

  it.each(calls)('%s surfaces the backend reason as the message', async (_name, run) => {
    respond(409, { detail: 'code already taken' });

    await expect(run()).rejects.toThrow('code already taken');
  });

  it('a Pydantic validation list reaches the caller intact, not stringified', async () => {
    // The hand-rolled readers joined the list — or, for delete/translate,
    // interpolated it straight into a template, printing "[object Object]".
    const detail = [
      { loc: ['body', 'code'], msg: 'field required' },
      { loc: ['body', 'emoji'], msg: 'not an emoji' },
    ];
    respond(422, { detail });

    const error = await createPersonality({} as never).catch((e: unknown) => e);

    expect((error as ApiError).data).toEqual({ detail });
    expect(String((error as ApiError).message)).not.toContain('[object Object]');
  });

  it('a delete refused with a structured detail does not print [object Object]', async () => {
    respond(422, { detail: [{ msg: 'personality is in use' }] });

    const error = await deletePersonality('p1').catch((e: unknown) => e);

    expect((error as ApiError).message).not.toContain('[object Object]');
  });

  it('falls back to the status line when the body carries no reason', async () => {
    respond(500, {});

    await expect(fetchPersonalities()).rejects.toMatchObject({ status: 500 });
  });
});

describe('personality API — session and transport', () => {
  it('sends the session cookie on every call', async () => {
    respond(200, {});

    await fetchPersonalities();

    expect(lastRequest().init.credentials).toBe('include');
  });

  it('arms a request timeout', async () => {
    respond(200, {});

    await fetchPersonalities();

    expect(lastRequest().init.signal).toBeInstanceOf(AbortSignal);
  });

  it('an expired session raises the typed 401 instead of a bare message', async () => {
    // apiClient ejects to the localized login on 401; the raw-fetch version
    // threw `Error("Failed to fetch personalities: 401")` and left the user on
    // a dead settings panel.
    respond(401, { detail: 'Not authenticated' });

    const error = await fetchPersonalities().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
  });
});
