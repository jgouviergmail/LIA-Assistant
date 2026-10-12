import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get } = vi.hoisted(() => ({ useAuth: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));

import { PsycheStateSummary } from '../PsycheStateSummary';
import { usePsycheStore } from '@/stores/psycheStore';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  usePsycheStore.getState().reset();
});

describe('owned passive manual psyche state refresh', () => {
  it('uses an observational read when explicitly refreshed', async () => {
    get.mockResolvedValue(null);
    const { rerender } = render(<PsycheStateSummary lng="en" refreshKey={0} />);
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    await waitFor(() => expect(get).toHaveBeenCalledWith('/psyche/state?initialize=false'));
  });

  it('refuses an obsolete account response', async () => {
    let finish: (value: object) => void = () => {};
    get.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const update = vi
      .spyOn(usePsycheStore.getState(), 'updateFromFullState')
      .mockImplementation(() => {});
    const { rerender } = render(<PsycheStateSummary lng="en" refreshKey={0} />);
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementationOnce(() => new Promise(() => {}));
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    await act(async () => finish({ active_emotions: [] }));
    expect(update).not.toHaveBeenCalled();
    update.mockRestore();
  });
});
