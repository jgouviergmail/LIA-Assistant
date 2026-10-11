import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const { useAuth, get, patch, put, post } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch, put, post },
  apiClient: { get, patch, put, post },
}));
import { publishApplicationResources } from '@/lib/application-resources';
import {
  useRelationsOverview,
  useOverviewScope,
  useRelationDetail,
  useRelationContext,
  useRelationDebrief,
  type RelationOverviewScope,
} from '../useRelations';

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  patch.mockReset();
  put.mockReset();
  post.mockReset();
  useAuth.mockReturnValue({ user: { id: 'account-one' } });
  get.mockResolvedValue({ relations: [], relations_total: 0, debrief_enabled: true });
});

it('a native relation hint rereads a removed debrief without buying another build', async () => {
  get.mockResolvedValue({ status: 'ready', person: 'Alice', body: null });
  const { result } = renderHook(() =>
    useRelationDebrief('Alice', { enabled: true, providerReady: true })
  );
  await waitFor(() => expect(result.current.debrief?.status).toBe('ready'));
  get.mockResolvedValue({ status: 'absent', person: 'Alice', body: null });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() => expect(result.current.debrief?.status).toBe('absent'));
  expect(post).not.toHaveBeenCalled();
});

it('the existing absent-debrief automatic attempt stays once-only in React Strict Mode', async () => {
  get.mockResolvedValue({ status: 'absent', person: 'Alice', body: null });
  post.mockResolvedValue({ status: 'ready', person: 'Alice', body: null });
  const { result } = renderHook(
    () => useRelationDebrief('Alice', { enabled: true, providerReady: true }),
    { reactStrictMode: true }
  );
  await waitFor(() => expect(result.current.debrief?.status).toBe('ready'));
  expect(post).toHaveBeenCalledOnce();
});

it('hides a stored debrief on account change and refuses the old rebuild callback', async () => {
  get.mockResolvedValue({ status: 'ready', person: 'Alice', body: null });
  const { result, rerender } = renderHook(() =>
    useRelationDebrief('Alice', { enabled: true, providerReady: true })
  );
  await waitFor(() => expect(result.current.debrief?.status).toBe('ready'));
  const obsolete = result.current.rebuild;
  get.mockImplementationOnce(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'account-two' } });
  rerender();
  expect(result.current.debrief).toBeNull();
  await act(async () => {
    await obsolete();
  });
  expect(post).not.toHaveBeenCalled();
});

it('hides provider card data and refuses an obsolete refresh on account change', async () => {
  get.mockResolvedValue({
    contact: { status: 'ok', contact: { display_name: 'Private contact' } },
  });
  const { result, rerender } = renderHook(() => useRelationContext('Alice'));
  await waitFor(() => expect(result.current.context?.contact.status).toBe('ok'));
  const obsolete = result.current.refreshSections;
  get.mockImplementationOnce(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'account-two' } });
  rerender();
  expect(result.current.context).toBeNull();
  await act(async () => {
    await obsolete(['contact']);
  });
  expect(get.mock.calls.some(([endpoint]) => String(endpoint).includes('?refresh='))).toBe(false);
});

it('a native context hint rereads cache without another forced provider refresh', async () => {
  get.mockResolvedValue({ contact: { status: 'ok', contact: { display_name: 'Old card' } } });
  const { result } = renderHook(() => useRelationContext('Alice'));
  await waitFor(() =>
    expect(result.current.context?.contact.contact?.display_name).toBe('Old card')
  );
  get.mockResolvedValue({ contact: { status: 'ok', contact: { display_name: 'Fresh card' } } });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() =>
    expect(result.current.context?.contact.contact?.display_name).toBe('Fresh card')
  );
  expect(get.mock.calls.every(([endpoint]) => !String(endpoint).includes('?refresh='))).toBe(true);
});

it('a late manual provider refresh cannot overwrite a native context reread', async () => {
  get.mockResolvedValue({ contact: { status: 'ok', contact: { display_name: 'Initial card' } } });
  const { result } = renderHook(() => useRelationContext('Alice'));
  await waitFor(() =>
    expect(result.current.context?.contact.contact?.display_name).toBe('Initial card')
  );
  let resolve: ((value: unknown) => void) | undefined;
  get.mockImplementationOnce(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  let pending: Promise<void> | undefined;
  act(() => {
    pending = result.current.refreshSections(['contact']);
  });
  get.mockResolvedValue({ contact: { status: 'ok', contact: { display_name: 'Native card' } } });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() =>
    expect(result.current.context?.contact.contact?.display_name).toBe('Native card')
  );
  await act(async () => {
    resolve?.({ contact: { status: 'ok', contact: { display_name: 'Obsolete card' } } });
    await pending;
  });
  expect(result.current.context?.contact.contact?.display_name).toBe('Native card');
});

it('a late manual build response cannot overwrite the native stored reread', async () => {
  get.mockResolvedValue({ status: 'ready', person: 'Alice', body: null });
  let resolve: ((value: unknown) => void) | undefined;
  post.mockImplementationOnce(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  const { result } = renderHook(() =>
    useRelationDebrief('Alice', { enabled: true, providerReady: true })
  );
  await waitFor(() => expect(result.current.debrief?.status).toBe('ready'));
  let pending: Promise<void>;
  act(() => {
    pending = result.current.rebuild();
  });
  get.mockResolvedValue({ status: 'disabled', person: 'Alice', body: null });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() => expect(result.current.debrief?.status).toBe('disabled'));
  await act(async () => {
    resolve?.({ status: 'ready', person: 'Alice', body: { headline: 'Obsolete' } });
    await pending;
  });
  expect(result.current.debrief?.status).toBe('disabled');
});

it('rereads the local detail after grouping and hides it on an account switch', async () => {
  get.mockResolvedValue({ display_name: 'Alice', merged_from: [] });
  const { result, rerender } = renderHook(() => useRelationDetail('Alice'));
  await waitFor(() => expect(result.current.detail?.display_name).toBe('Alice'));
  get.mockResolvedValue({ display_name: 'Alice', merged_from: ['Papa'] });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() => expect(result.current.detail?.merged_from).toEqual(['Papa']));
  get.mockImplementationOnce(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'account-two' } });
  rerender();
  expect(result.current.detail).toBeNull();
});

it('rereads a confirmed relation preference and releases the prior manual override', async () => {
  patch.mockResolvedValue({ debrief_enabled: false });
  const { result } = renderHook(() => useRelationsOverview());
  await waitFor(() => expect(get).toHaveBeenCalled());
  await act(async () => {
    await result.current.setDebriefEnabled(false);
  });
  expect(result.current.debriefEnabled).toBe(false);
  get.mockResolvedValue({ relations: [], relations_total: 0, debrief_enabled: true });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() => expect(result.current.debriefEnabled).toBe(true));
});

it('hides private scope during an account switch and refuses the obsolete save callback', async () => {
  const scope: RelationOverviewScope = {
    sections: ['emails'],
    directions: [],
    roles: [],
    max_items: 3,
  };
  get.mockResolvedValue(scope);
  const { result, rerender } = renderHook(() => useOverviewScope());
  await waitFor(() => expect(result.current.scope).toEqual(scope));
  const obsolete = result.current.save;
  get.mockImplementationOnce(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'account-two' } });
  rerender();
  expect(result.current.scope).toBeNull();
  await act(async () => {
    expect(await obsolete(scope)).toBe(false);
  });
  expect(put).not.toHaveBeenCalled();
});

it('a late manual debrief response cannot override a confirmed native reread', async () => {
  let resolve: ((value: unknown) => void) | undefined;
  patch.mockImplementationOnce(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  const { result } = renderHook(() => useRelationsOverview());
  await waitFor(() => expect(get).toHaveBeenCalled());
  let pending: Promise<{ ok: boolean }>;
  act(() => {
    pending = result.current.setDebriefEnabled(false);
  });
  get.mockResolvedValue({ relations: [], relations_total: 0, debrief_enabled: true });
  act(() => publishApplicationResources('account-one', new Set(['relations'])));
  await waitFor(() => expect(result.current.debriefEnabled).toBe(true));
  await act(async () => {
    resolve?.({ debrief_enabled: false });
    await pending;
  });
  expect(result.current.debriefEnabled).toBe(true);
});
