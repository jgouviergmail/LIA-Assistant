/**
 * useWorkbenchAvailability — the rail's one read of `GET /workbench` (ADR-369).
 *
 * Read only where the section is offered; re-read, in place, when a connector
 * changes elsewhere (the `connectors` application resource), so a service
 * unlinked in Settings leaves the rail without a reload.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import { publishApplicationResources } from '@/lib/application-resources';
import type { WorkbenchAvailability } from '@/lib/workbench/types';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
const { account } = vi.hoisted(() => ({ account: { id: 'account-a' } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useWorkbenchAvailability } from '../useWorkbenchAvailability';

function answer(state: 'ready' | 'not_connected'): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'mail',
        state,
        provider: state === 'ready' ? 'google_gmail' : null,
        features: [],
        bounds: {},
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
    },
  };
}

beforeEach(() => {
  account.id = 'account-a';
  vi.clearAllMocks();
  get.mockResolvedValue(answer('ready'));
});

describe('useWorkbenchAvailability', () => {
  it('reads the rail where the section is offered', async () => {
    const { result } = renderHook(() => useWorkbenchAvailability(true));

    await waitFor(() => expect(result.current.availability).toEqual(answer('ready')));
    expect(get.mock.calls[0]?.[0]).toBe('/workbench');
  });

  it('reads nothing where the section is not offered', async () => {
    const { result } = renderHook(() => useWorkbenchAvailability(false));

    await act(async () => {
      await Promise.resolve();
    });
    expect(get).not.toHaveBeenCalled();
    expect(result.current.availability).toBeUndefined();
  });

  it('re-reads when a connector of this account changes elsewhere', async () => {
    const { result } = renderHook(() => useWorkbenchAvailability(true));
    await waitFor(() => expect(result.current.availability?.tools[0]?.state).toBe('ready'));

    get.mockResolvedValue(answer('not_connected'));
    act(() => publishApplicationResources('account-a', new Set(['connectors'])));

    await waitFor(() => expect(result.current.availability?.tools[0]?.state).toBe('not_connected'));
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("ignores another account's change and another resource", async () => {
    const { result } = renderHook(() => useWorkbenchAvailability(true));
    await waitFor(() => expect(result.current.availability).toBeDefined());

    act(() => {
      publishApplicationResources('account-b', new Set(['connectors']));
      publishApplicationResources('account-a', new Set(['memories']));
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(get).toHaveBeenCalledTimes(1);
  });
});
