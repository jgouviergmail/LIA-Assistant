import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import { applicationStateChangeSchema } from '@/types/application-state';
import { useSessions, type DeviceSession } from '../useSessions';

const { auth, get, remove, post } = vi.hoisted(() => ({
  auth: vi.fn(),
  get: vi.fn(),
  remove: vi.fn(),
  post: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, delete: remove, post } };
});
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

function session(id: string): DeviceSession {
  return {
    id,
    current: false,
    ua_family: 'chrome',
    os_family: 'windows',
    ip_trunc: null,
    auth_methods: ['password'],
    created_at: '2026-10-07T10:00:00Z',
    last_seen_at: null,
    device_name: 'Owned device',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.mockReturnValue({ user: { id: 'one' } });
});

describe('application session invalidation and account authority', () => {
  it('refuses every session mutation while logged out without issuing HTTP', async () => {
    auth.mockReturnValue({ user: null });
    const { result } = renderHook(() => useSessions());
    await act(async () => {
      await expect(result.current.revokeSession('a')).rejects.toThrow();
      await expect(result.current.revokeOthers()).rejects.toThrow();
    });
    expect(get).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });
  it('rereads only the addressed session resource without another mutation', async () => {
    get.mockResolvedValueOnce([session('a')]).mockResolvedValueOnce([]);
    const { result } = renderHook(() => useSessions());
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    act(() => {
      publishApplicationResources('two', new Set(['device_sessions']));
      publishApplicationResources('one', new Set(['phone_identity']));
    });
    expect(get).toHaveBeenCalledTimes(1);
    act(() => {
      publishApplicationResources('one', new Set(['device_sessions']));
    });
    await waitFor(() => expect(result.current.sessions).toEqual([]));
    expect(get).toHaveBeenCalledTimes(2);
    expect(remove).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });

  it('hides the previous account and refuses its old mutation callback', async () => {
    get.mockResolvedValueOnce([session('private-one')]);
    get.mockImplementationOnce(() => new Promise(() => {}));
    const { result, rerender } = renderHook(() => useSessions());
    await waitFor(() => expect(result.current.sessions[0]?.id).toBe('private-one'));
    const obsolete = result.current.revokeSession;
    auth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.sessions).toEqual([]);
    await act(async () => {
      await expect(obsolete('private-one')).rejects.toThrow();
    });
    expect(remove).not.toHaveBeenCalled();
  });

  it('accepts the new backend hint without accepting session credentials', () => {
    const hint = {
      schema_version: 1,
      command_id: '46c2fdb3-7bdd-4ee4-a21a-bd6e5dce9bba',
      actor_id: '20b5e4db-34f3-4717-91e4-040eb21e70d7',
      resources: ['device_sessions'],
      changed_fields: ['session_to_revoke'],
      observed_at: '2026-10-07T10:00:00Z',
    };
    expect(applicationStateChangeSchema.safeParse(hint).success).toBe(true);
    expect(applicationStateChangeSchema.safeParse({ ...hint, cookie: 'private' }).success).toBe(
      false
    );
  });
});
