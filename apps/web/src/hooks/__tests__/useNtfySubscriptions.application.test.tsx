/**
 * useNtfySubscriptions — the ntfy settings of an account (ADR-391), through the real query and
 * mutation hooks: only the HTTP client is replaced.
 *
 * Oracle: what is read and when, what each verb sends, that a success re-reads the list, and
 * that a refusal comes back with its stable code (the screen translates it) and re-reads nothing.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';

const { client, useAuth } = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: client, apiClient: client };
});

import {
  useNtfySubscriptions,
  type NtfyOverview,
  type NtfySubscriptionView,
} from '../useNtfySubscriptions';

function view(overrides: Partial<NtfySubscriptionView> = {}): NtfySubscriptionView {
  return {
    id: 'sub-1',
    server_kind: 'instance',
    server_url: 'https://ntfy.example.org',
    topic: 'lia_AbCdEfGhIjKlMnOpQrStUvWxYz12',
    has_token: false,
    content: 'minimal',
    is_active: true,
    last_sent_at: null,
    last_error_code: null,
    last_error_at: null,
    created_at: '2026-11-16T08:00:00Z',
    subscribe_link: 'ntfy://ntfy.example.org/lia_AbCdEfGhIjKlMnOpQrStUvWxYz12?display=LIA',
    ...overrides,
  };
}

function overview(subscriptions: NtfySubscriptionView[] = [view()]): NtfyOverview {
  return {
    instance_url: 'https://ntfy.example.org',
    custom_servers_enabled: true,
    max_subscriptions: 3,
    subscriptions,
  };
}

const OVERVIEW = '/notifications/ntfy';

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
  client.get.mockResolvedValue(overview());
});

async function mounted(enabled = true) {
  const hook = renderHook(() => useNtfySubscriptions(enabled));
  if (enabled) await waitFor(() => expect(hook.result.current.overview).toBeDefined());
  return hook;
}

function reads(): number {
  return client.get.mock.calls.filter(([endpoint]) => endpoint === OVERVIEW).length;
}

describe('useNtfySubscriptions', () => {
  it('reads the account settings once offered, and nothing while the capability is off', async () => {
    const off = renderHook(() => useNtfySubscriptions(false));
    await act(async () => {});
    expect(client.get).not.toHaveBeenCalled();
    expect(off.result.current.firstLoad).toBe(false);

    const { result } = await mounted();
    expect(result.current.overview?.subscriptions).toHaveLength(1);
    expect(result.current.firstLoad).toBe(false);
  });

  it('posts a new subscription as typed, then re-reads the list', async () => {
    const { result } = await mounted();
    const made = view({ id: 'sub-2', server_kind: 'custom', server_url: 'https://ntfy.sh' });
    client.post.mockResolvedValue(made);
    const before = reads();

    let outcome: Awaited<ReturnType<typeof result.current.create>> | undefined;
    await act(async () => {
      outcome = await result.current.create({
        server: 'custom',
        server_url: 'https://ntfy.sh',
        topic: 'my-alerts',
        content: 'full',
      });
    });

    expect(outcome).toEqual({ ok: true, errorCode: null, data: made });
    expect(client.post).toHaveBeenCalledWith(
      OVERVIEW,
      { server: 'custom', server_url: 'https://ntfy.sh', topic: 'my-alerts', content: 'full' },
      undefined
    );
    await waitFor(() => expect(reads()).toBe(before + 1));
  });

  it('returns a refusal with its code and re-reads nothing', async () => {
    const { result } = await mounted();
    client.post.mockRejectedValue(
      new ApiError('refused', 409, { detail: { code: 'ntfy_subscription_limit', max: 3 } })
    );
    const before = reads();

    let outcome: Awaited<ReturnType<typeof result.current.create>> | undefined;
    await act(async () => {
      outcome = await result.current.create({ server: 'instance', content: 'minimal' });
    });

    expect(outcome).toEqual({ ok: false, errorCode: 'ntfy_subscription_limit' });
    expect(reads()).toBe(before);
  });

  it('pauses with the switch alone, and changes the content with the content alone', async () => {
    const { result } = await mounted();
    client.patch.mockResolvedValue(view({ is_active: false }));

    await act(async () => {
      await result.current.update('sub-1', { is_active: false });
      await result.current.update('sub-1', { content: 'full' });
    });

    expect(client.patch.mock.calls.map(([endpoint, body]) => [endpoint, body])).toEqual([
      ['/notifications/ntfy/sub-1', { is_active: false }],
      ['/notifications/ntfy/sub-1', { content: 'full' }],
    ]);
  });

  it('says what the server answered a test', async () => {
    const { result } = await mounted();
    client.post.mockResolvedValue({ outcome: 'auth_refused' });

    let outcome: Awaited<ReturnType<typeof result.current.test>> | undefined;
    await act(async () => {
      outcome = await result.current.test('sub-1');
    });

    expect(client.post).toHaveBeenCalledWith(
      '/notifications/ntfy/sub-1/test',
      undefined,
      undefined
    );
    expect(outcome).toEqual({ ok: true, errorCode: null, data: 'auth_refused' });
  });

  it('removes a subscription, then re-reads the list', async () => {
    const { result } = await mounted();
    client.delete.mockResolvedValue(undefined);
    const before = reads();

    await act(async () => {
      await result.current.remove('sub-1');
    });

    expect(client.delete.mock.calls[0]?.[0]).toBe('/notifications/ntfy/sub-1');
    await waitFor(() => expect(reads()).toBe(before + 1));
  });
});
