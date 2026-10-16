import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get } = vi.hoisted(() => ({ useAuth: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));

import { PsycheStateSummary } from '../PsycheStateSummary';
import { PsycheLLMSummary } from '../PsycheLLMSummary';
import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheState } from '@/types/psyche';

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  usePsycheStore.getState().reset();
  usePsycheStore.getState().bindOwner('one');
  usePsycheStore.getState().setEnabled(true);
});

describe('owned passive manual psyche state refresh', () => {
  it('uses an observational read when explicitly refreshed', async () => {
    get.mockResolvedValue(null);
    const { rerender } = render(<PsycheStateSummary lng="en" refreshKey={0} />);
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/psyche/state?initialize=false', {
        signal: expect.any(AbortSignal),
      })
    );
    expect(usePsycheStore.getState().ownerId).toBe('one');
  });

  it('refuses an obsolete account response', async () => {
    let finish: (value: PsycheState) => void = () => {};
    get.mockImplementationOnce(
      () =>
        new Promise<PsycheState>(resolve => {
          finish = resolve;
        })
    );
    const update = vi
      .spyOn(usePsycheStore.getState(), 'updateFromFullState')
      .mockImplementation(() => {});
    const { rerender } = render(<PsycheStateSummary lng="en" refreshKey={0} />);
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const signal = get.mock.calls[0][1].signal as AbortSignal;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementationOnce(() => new Promise(() => {}));
    rerender(<PsycheStateSummary lng="en" refreshKey={1} />);
    await act(async () => finish(previousAccountState()));
    expect(signal.aborted).toBe(true);
    expect(update).not.toHaveBeenCalled();
    update.mockRestore();
  });
});

/** A complete, valid old-owner payload: rejection cannot pass merely on invalid data. */
function previousAccountState(): PsycheState {
  return {
    id: 'psyche-one',
    user_id: 'one',
    trait_openness: 0.8,
    trait_conscientiousness: 0.7,
    trait_extraversion: 0.5,
    trait_agreeableness: 0.9,
    trait_neuroticism: 0.2,
    mood_pleasure: 0.4,
    mood_arousal: 0.1,
    mood_dominance: -0.2,
    mood_label: 'serene',
    mood_color: '#38bdf8',
    active_emotions: [],
    relationship_stage: 'STABLE',
    relationship_depth: 0.8,
    relationship_warmth_active: 0.7,
    relationship_trust: 0.6,
    relationship_interaction_count: 123,
    drive_curiosity: 0.6,
    drive_engagement: 0.7,
    self_efficacy: {},
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T11:00:00Z',
  };
}

describe('stable automatic point composition', () => {
  it('generates once across null/full observation transitions and only rereads on explicit reset', async () => {
    get.mockResolvedValue({ summary: 'One automatic point' });
    const view = (resetVersion: number) => (
      <StrictMode>
        <PsycheStateSummary
          lng="en"
          summary={<PsycheLLMSummary lng="en" refreshKey={resetVersion} />}
        />
      </StrictMode>
    );
    const { rerender, findByText } = render(view(0));
    await findByText('One automatic point');
    expect(get.mock.calls.filter(([endpoint]) => endpoint === '/psyche/summary')).toHaveLength(1);
    act(() => usePsycheStore.getState().updateFromFullState(previousAccountState()));
    await act(async () => {});
    expect(get.mock.calls.filter(([endpoint]) => endpoint === '/psyche/summary')).toHaveLength(1);
    act(() => usePsycheStore.getState().clearObservedState());
    await act(async () => {});
    act(() => usePsycheStore.getState().updateFromFullState(previousAccountState()));
    await act(async () => {});
    expect(get.mock.calls.filter(([endpoint]) => endpoint === '/psyche/summary')).toHaveLength(1);
    rerender(view(1));
    await waitFor(() =>
      expect(get.mock.calls.filter(([endpoint]) => endpoint === '/psyche/summary')).toHaveLength(2)
    );
  });
});
