import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, useAuth } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post } };
});
import { useBriefing } from '../useBriefing';

const cards = { cards: { reminders: { status: 'ok', data: { items: [{ id: 'saved' }] } } }, windows: {} };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/cards') ? cards : { greeting: {} }));
});

describe('reminder invalidation refreshes briefing cards without paid synthesis', () => {
  it('reads only cards for its own committed reminder changes', async () => {
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.cards).toEqual(cards.cards));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['reminders'])));
    expect(get).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(get.mock.calls.map(call => call[0])).toEqual(['/briefing/cards']);
    expect(post).not.toHaveBeenCalled();
  });

  it('hides old briefing data and rejects its parked refresh after switching accounts', async () => {
    const { result, rerender } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.cards).toEqual(cards.cards));
    const retired = result.current.refetchSection;
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.cards).toBeUndefined();
    expect(result.current.text).toBeUndefined();
    await act(async () => { await retired('reminders'); });
    expect(post).not.toHaveBeenCalled();
  });
});
