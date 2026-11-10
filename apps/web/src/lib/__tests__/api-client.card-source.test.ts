/** A card's source proof reaches its real provider read, and no other screen. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient, { apiEndpointUrl } from '../api-client';

const originalUrl = window.location.href;
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { headers: { 'content-type': 'application/json' } }))
  );
});
afterEach(() => {
  window.history.replaceState(null, '', originalUrl);
  vi.unstubAllGlobals();
});

function headers() {
  return new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers);
}

describe('card source at the actual API transport', () => {
  it.each([
    ['files', '/workbench/files/download?id=file%26exact&format=pdf'],
    ['mail', '/workbench/mail/attachment?message_id=exact&filename=notes.pdf'],
    ['contacts', '/workbench/contacts/export?id=person%2Fexact'],
  ])('keeps the signed proof on direct %s downloads', (family, endpoint) => {
    window.history.replaceState(
      null,
      '',
      `/dashboard/tools/${family}?card_source=opaque.signed-token`
    );
    const url = new URL(apiEndpointUrl(endpoint), window.location.origin);
    expect(url.searchParams.get('card_source')).toBe('opaque.signed-token');
    const original = new URL(endpoint, window.location.origin);
    for (const [key, value] of original.searchParams) expect(url.searchParams.get(key)).toBe(value);
  });

  it('leaves unrelated direct media and download endpoints unchanged', () => {
    window.history.replaceState(null, '', '/dashboard/tools/files?card_source=proof');
    for (const endpoint of [
      '/world/ws',
      '/attachments/file/download',
      '/workbench/mail/attachment?id=1',
    ]) {
      expect(apiEndpointUrl(endpoint)).toBe(`/api/v1${endpoint}`);
    }
  });
  it.each(['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'])(
    'guards %s reads with the same opaque proof',
    async family => {
      window.history.replaceState(
        null,
        '',
        `/en/dashboard/tools/${family}?card_source=opaque.signed-token`
      );
      await apiClient.get(`/workbench/${family}/detail`, { params: { id: 'one' } });
      expect(headers().get('X-LIA-Card-Source')).toBe('opaque.signed-token');
      expect(vi.mocked(fetch).mock.calls[0][1]?.credentials).toBe('include');
    }
  );

  it.each([
    ['/dashboard/chat?card_source=proof', '/workbench/mail/messages'],
    ['/dashboard/tools/mail?card_source=proof', '/workbench/contacts'],
    ['/dashboard/tools/mail?card_source=proof', '/workbench'],
    ['/dashboard/tools/mail?card_source=proof', '/auth/me'],
    ['/dashboard/tools/mail', '/workbench/mail/messages'],
  ])('never leaks the proof from %s to %s', async (page, endpoint) => {
    window.history.replaceState(null, '', page);
    await apiClient.get(endpoint);
    expect(headers().has('X-LIA-Card-Source')).toBe(false);
  });

  it('reads the current route each time rather than retaining a previous source', async () => {
    window.history.replaceState(null, '', '/dashboard/tools/mail?card_source=first');
    await apiClient.get('/workbench/mail/message');
    window.history.replaceState(null, '', '/dashboard/tools/mail?card_source=second');
    await apiClient.get('/workbench/mail/message');
    expect(new Headers(vi.mocked(fetch).mock.calls[1][1]?.headers).get('X-LIA-Card-Source')).toBe(
      'second'
    );
  });
});
