import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCapabilityTransfer } from '../useCapabilityTransfer';
import type { CapabilitySelection, CapabilityTransfer } from '@/lib/capability-sharing';

const mocks = vi.hoisted(() => ({ owner: 'owner-a', post: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: mocks.owner } }) }));
vi.mock('@/lib/api-client', () => ({ default: { post: mocks.post, get: mocks.get } }));

const source: CapabilitySelection = {
  kind: 'skill',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Example',
};
function receipt(overrides: Partial<CapabilityTransfer> = {}): CapabilityTransfer {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    kind: 'skill',
    name: 'Example',
    status: 'preparing',
    digest: 'a'.repeat(64),
    files: [{ path: 'SKILL.md', size: 30 }],
    omitted: [],
    requires_credentials: false,
    created_at: '2026-10-18T12:00:00Z',
    transferred_at: null,
    components: [],
    error_code: null,
    ...overrides,
  };
}
function deferred<T>() {
  let resolve: (value: T) => void = () => {
    throw new Error('not initialized');
  };
  const promise = new Promise<T>(done => {
    resolve = done;
  });
  return { promise, resolve: (value: T) => resolve(value) };
}

beforeEach(() => {
  mocks.owner = 'owner-a';
  vi.clearAllMocks();
});

describe('useCapabilityTransfer', () => {
  it('does nothing until the person asks, and submits only closed preview fields', async () => {
    mocks.post.mockResolvedValue(receipt());
    const { result } = renderHook(() => useCapabilityTransfer(source));
    expect(mocks.post).not.toHaveBeenCalled();
    await act(() => result.current.prepare('connection-id'));
    expect(mocks.post).toHaveBeenCalledWith(
      '/peers/capability-transfers/preview',
      {
        connection_id: 'connection-id',
        kind: 'skill',
        source_id: source.id,
        idempotency_key: expect.any(String),
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(result.current.preview?.digest).toBe(receipt().digest);
  });

  it('deduplicates a double click before React rerenders', async () => {
    const pending = deferred<CapabilityTransfer>();
    mocks.post.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCapabilityTransfer(source));
    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.prepare('peer');
      void result.current.prepare('peer');
    });
    expect(mocks.post).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(receipt());
      await first;
    });
  });

  it('reuses a preview idempotency key after an ambiguous network failure', async () => {
    mocks.post.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(receipt());
    const { result } = renderHook(() => useCapabilityTransfer(source));
    await act(() => result.current.prepare('peer'));
    await act(() => result.current.prepare('peer'));
    expect(mocks.post.mock.calls[0][1].idempotency_key).toBe(
      mocks.post.mock.calls[1][1].idempotency_key
    );
  });

  it('reads a durable outcome after losing the send response without sending again', async () => {
    mocks.post.mockResolvedValueOnce(receipt()).mockRejectedValueOnce(new Error('lost response'));
    mocks.get.mockResolvedValue(
      receipt({ status: 'installed', transferred_at: '2026-10-18T12:00:01Z' })
    );
    const { result } = renderHook(() => useCapabilityTransfer(source));
    await act(() => result.current.prepare('peer'));
    const preview = result.current.preview;
    expect(preview).not.toBeNull();
    if (!preview) throw new Error('missing preview');
    await act(() => result.current.send(preview));
    expect(mocks.post).toHaveBeenCalledTimes(2);
    expect(mocks.get).toHaveBeenCalledWith(
      `/peers/capability-transfers/${preview.id}`,
      expect.any(Object)
    );
    expect(result.current.outcome?.status).toBe('installed');
    expect(result.current.error).toBeNull();
  });

  it('rejects malformed or mismatched receipt data instead of showing success', async () => {
    mocks.post.mockResolvedValue({ ...receipt(), status: 'made_up' });
    const { result } = renderHook(() => useCapabilityTransfer(source));
    await act(() => result.current.prepare('peer'));
    expect(result.current.preview).toBeNull();
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('aborts old reads and suppresses late data and retained actions across A to B to A', async () => {
    const pending = deferred<CapabilityTransfer>();
    mocks.post.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(() => useCapabilityTransfer(source));
    const stale = result.current.prepare;
    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.prepare('peer-a');
    });
    const signal: AbortSignal = mocks.post.mock.calls[0][2].signal;
    mocks.owner = 'owner-b';
    rerender();
    mocks.owner = 'owner-a';
    rerender();
    expect(signal.aborted).toBe(true);
    await act(async () => {
      pending.resolve(receipt());
      await first;
      await stale('peer-a');
    });
    expect(result.current.preview).toBeNull();
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it('invalidates a retained send when the person discards its preview', async () => {
    mocks.post.mockResolvedValue(receipt());
    const { result } = renderHook(() => useCapabilityTransfer(source));
    await act(() => result.current.prepare('peer'));
    const preview = result.current.preview;
    if (!preview) throw new Error('missing preview');
    act(() => result.current.reset());
    await act(() => result.current.send(preview));
    expect(mocks.post).toHaveBeenCalledTimes(1);
    expect(result.current.preview).toBeNull();
  });

  it('isolates a source change and allows an explicit read of a partial receipt', async () => {
    mocks.post.mockResolvedValue(receipt());
    const { result, rerender } = renderHook(({ selection }) => useCapabilityTransfer(selection), {
      initialProps: { selection: source },
    });
    await act(() => result.current.prepare('peer'));
    const preview = result.current.preview;
    if (!preview) throw new Error('missing preview');
    mocks.get.mockResolvedValue(receipt({ status: 'partial' }));
    await act(() => result.current.refresh(preview));
    expect(result.current.outcome?.status).toBe('partial');
    rerender({ selection: { ...source, id: '33333333-3333-4333-8333-333333333333' } });
    await waitFor(() => expect(result.current.preview).toBeNull());
  });
});
