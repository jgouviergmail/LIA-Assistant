import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

describe('application device addressing', () => {
  it('addresses chat and command requests to the same document without changing other requests', async () => {
    const { applicationDeviceHeaders } = await import('../application-device-identity');
    const chat = applicationDeviceHeaders('/agents/chat/stream');
    expect(chat['X-Lia-Device-ID']).toMatch(/^[0-9a-f-]{36}$/);
    expect(applicationDeviceHeaders('/application-commands/command-id')).toEqual(chat);
    expect(applicationDeviceHeaders('/application-device/snapshot')).toEqual(chat);
    expect(applicationDeviceHeaders('/auth/features')).toEqual({});
    expect(applicationDeviceHeaders('/users/me')).toEqual({});
  });

  it('a new document cannot reuse the previous document address', async () => {
    const first = await import('../application-device-identity');
    const original = first.applicationDeviceHeaders('/agents/chat/stream');
    vi.resetModules();
    const next = await import('../application-device-identity');
    expect(next.applicationDeviceHeaders('/agents/chat/stream')).not.toEqual(original);
  });

  it('server rendering and unsupported browsers cannot invent a device address', async () => {
    const { applicationDeviceHeaders } = await import('../application-device-identity');
    vi.stubGlobal('window', undefined);
    expect(applicationDeviceHeaders('/agents/chat/stream')).toEqual({});
    vi.unstubAllGlobals();
    vi.stubGlobal('crypto', {});
    expect(applicationDeviceHeaders('/agents/chat/stream')).toEqual({});
  });

  it('the actual API client attaches this document address only to the command transport', async () => {
    const fetch = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const { default: client } = await import('../api-client');
    const { applicationDeviceId } = await import('../application-device-identity');
    await client.post('/application-commands/owned-command/claim', {});
    expect(fetch).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({ 'X-Lia-Device-ID': applicationDeviceId() }),
      })
    );
    await client.get('/auth/features');
    expect(fetch).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.objectContaining({
        credentials: 'include',
        headers: {},
      })
    );
  });
});
