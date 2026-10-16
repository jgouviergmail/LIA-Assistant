import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheState } from '@/types/psyche';

const mocks = vi.hoisted(() => ({ owner: { id: 'owner-a' }, get: vi.fn(), desktop: true }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => mocks.desktop }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: mocks.owner }) }));
vi.mock('@/lib/api-client', () => ({ default: { get: mocks.get } }));
import { PsycheStateSummary } from '../PsycheStateSummary';

function state(overrides: Partial<PsycheState> = {}): PsycheState {
  return {
    id: 'psyche-a',
    user_id: 'owner-a',
    trait_openness: 0.82,
    trait_conscientiousness: 0.72,
    trait_extraversion: 0.45,
    trait_agreeableness: 0.9,
    trait_neuroticism: 0.1,
    mood_pleasure: 0.4,
    mood_arousal: -0.25,
    mood_dominance: 0,
    mood_label: 'serene',
    mood_color: '#0ea5e9',
    active_emotions: [
      { name: 'gratitude', intensity: 0.22, triggered_at: '' },
      { name: 'curiosity', intensity: 0.84, triggered_at: '' },
    ],
    relationship_stage: 'STABLE',
    relationship_depth: 0.6,
    relationship_warmth_active: 0.9,
    relationship_trust: 0.8,
    relationship_interaction_count: 143,
    drive_curiosity: 0.75,
    drive_engagement: 0.67,
    self_efficacy: { technical: { score: 0.93, weight: 4.5 } },
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T11:00:00Z',
    ...overrides,
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.owner = { id: 'owner-a' };
  mocks.desktop = true;
  usePsycheStore.getState().reset();
  usePsycheStore.getState().bindOwner('owner-a');
  usePsycheStore.getState().setEnabled(true);
  mocks.get.mockResolvedValue(null);
});
describe('PsycheStateSummary', () => {
  it('does not invent a neutral state or traits before a state exists', () => {
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    expect(screen.getByText('psyche.stateUnavailable')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });
  it('shows signed PAD values on their bipolar scale and every real state dimension', async () => {
    usePsycheStore.getState().updateFromFullState(state());
    const { user } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    const pleasure = screen.getByRole('meter', { name: 'psyche.education.mood.pleasure' });
    expect(pleasure).toHaveAttribute('aria-valuemin', '-1');
    expect(pleasure).toHaveAttribute('aria-valuemax', '1');
    expect(pleasure).toHaveAttribute('aria-valuenow', '0.4');
    expect(screen.getByRole('meter', { name: 'psyche.education.mood.arousal' })).toHaveAttribute(
      'aria-valuenow',
      '-0.25'
    );
    expect(
      screen.queryByRole('meter', { name: 'psyche.education.traits.openness' })
    ).not.toBeInTheDocument();
    await user.click(screen.getByText('psyche.education.traits.title'));
    await user.click(screen.getByText('psyche.education.drives.efficacy_title'));
    for (const name of [
      'openness',
      'conscientiousness',
      'extraversion',
      'agreeableness',
      'neuroticism',
    ])
      expect(
        screen.getByRole('meter', { name: `psyche.education.traits.${name}` })
      ).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'psyche.history.engagement' })).toHaveAttribute(
      'aria-valuenow',
      '67'
    );
    // Legacy score/weight is not evidence and must not become a confidence meter.
    expect(
      within(screen.getByRole('region', { name: 'psyche.domains.technical' })).queryByRole('meter')
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'psyche.domains.technical' })
    ).toBeVisible();
    expect(screen.getByText('143')).toBeInTheDocument();
  });
  it('sorts all emotions by intensity without mutating shared server data', () => {
    const full = state();
    Object.freeze(full.active_emotions);
    usePsycheStore.getState().updateFromFullState(full);
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    const emotions = within(
      screen.getByRole('region', { name: 'psyche.activeEmotion' })
    ).getAllByRole('meter');
    expect(emotions.map(meter => meter.getAttribute('aria-label'))).toEqual([
      'psyche.emotions.curiosity',
      'psyche.emotions.gratitude',
    ]);
    expect(full.active_emotions.map(emotion => emotion.name)).toEqual(['gratitude', 'curiosity']);
  });
  it('hides data from the previous account immediately', () => {
    usePsycheStore.getState().updateFromFullState(state());
    mocks.owner = { id: 'owner-b' };
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText('143')).not.toBeInTheDocument();
  });
  it('rejects a full snapshot whose payload owner disagrees with the bound store', () => {
    usePsycheStore.getState().updateFromFullState(state({ user_id: 'owner-b' }));
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    expect(screen.queryAllByRole('meter')).toHaveLength(0);
    expect(screen.getByText('psyche.stateUnavailable')).toBeVisible();
  });
  it('does not read or initialize psyche on first mount, including Strict Mode', async () => {
    renderWithProviders(
      <StrictMode>
        <PsycheStateSummary lng="fr" />
      </StrictMode>
    );
    await act(async () => {});
    expect(mocks.get).not.toHaveBeenCalled();
  });
  it('refreshes observationally and cancels a superseded read', async () => {
    const { rerender } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    mocks.get.mockReturnValue(new Promise(() => {}));
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
    const firstSignal = mocks.get.mock.calls[0][1].signal as AbortSignal;
    expect(mocks.get.mock.calls[0][0]).toBe('/psyche/state?initialize=false');
    rerender(<PsycheStateSummary lng="fr" refreshKey={2} />);
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(firstSignal.aborted).toBe(true);
  });
});

describe('PsycheStateSummary — observational response ownership', () => {
  it('shows a refreshed evidence profile and hides it immediately on an account switch', async () => {
    const efficacyProfile: NonNullable<PsycheState['efficacy_profile']> = {
      version: 1,
      window_days: 90,
      collection_enabled: true,
      influence_enabled: true,
      unassigned_feedback_count: 0,
      domains: [{
        domain: 'technical',
        status: 'observed',
        results: { success: 4, failure: 1, partial: 0, unknown: 0 },
        feedback: { helpful: 0, unhelpful: 0 },
        result_count: 5,
        feedback_count: 0,
        result_score: 0.7142857142857143,
        feedback_score: null,
        last_observed_at: '2026-10-16T10:00:00Z',
      }],
    };
    mocks.get.mockResolvedValue(state({ efficacy_profile: efficacyProfile }));
    usePsycheStore.getState().updateFromFullState(state());
    const { user, rerender } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    await user.click(screen.getByText('psyche.education.drives.efficacy_title'));
    const name = 'psyche.domains.technical · psyche.efficacy.results';
    expect(screen.queryByRole('meter', { name })).not.toBeInTheDocument();
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await waitFor(() =>
      expect(screen.getByRole('meter', { name })).toHaveAttribute('aria-valuenow', '71')
    );
    mocks.owner = { id: 'owner-b' };
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    expect(screen.queryByRole('meter', { name })).not.toBeInTheDocument();
  });

  it('rejects a response for another account even when the transport succeeds', async () => {
    mocks.get.mockResolvedValue(state({ user_id: 'owner-b' }));
    const { rerender } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await act(async () => {});
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(usePsycheStore.getState().fullState).toBeNull();
  });
  it('rejects an in-flight result after the active account changes', async () => {
    let resolve: (value: PsycheState | null) => void = () => undefined;
    mocks.get.mockImplementation(
      () =>
        new Promise<PsycheState | null>(done => {
          resolve = done;
        })
    );
    const { rerender } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
    mocks.owner = { id: 'owner-b' };
    act(() => usePsycheStore.getState().bindOwner('owner-b'));
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await act(async () => resolve(state()));
    expect(usePsycheStore.getState().ownerId).toBe('owner-b');
    expect(usePsycheStore.getState().fullState).toBeNull();
  });
  it('clears a deleted observation while preserving the enabled preference', async () => {
    usePsycheStore.getState().updateFromFullState(state());
    const { rerender } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    rerender(<PsycheStateSummary lng="fr" refreshKey={1} />);
    await waitFor(() => expect(screen.getByText('psyche.stateUnavailable')).toBeInTheDocument());
    expect(usePsycheStore.getState().enabled).toBe(true);
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });
});

describe('PsycheStateSummary — approved visual instruments', () => {
  it('positions the PAD point from pleasure and arousal while stating dominance independently', () => {
    usePsycheStore
      .getState()
      .updateFromFullState(state({ mood_pleasure: 0.4, mood_arousal: -0.25, mood_dominance: 0.8 }));
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    const plane = screen.getByRole('img', { name: 'psyche.presentation.padTitle' });
    const point = plane.querySelector('circle:last-of-type');
    expect(point).toHaveAttribute('cx', '219.4');
    expect(point).toHaveAttribute('cy', '153.75');
    expect(screen.getByRole('meter', { name: 'psyche.education.mood.dominance' })).toHaveAttribute(
      'aria-valuenow',
      '0.8'
    );
  });
  it('collapses the mobile instruments while preserving the always visible point', async () => {
    mocks.desktop = false;
    usePsycheStore.getState().updateFromFullState(state());
    const { user } = renderWithProviders(
      <PsycheStateSummary lng="fr" summary={<p>Current point</p>} />
    );
    expect(screen.getByText('Current point')).toBeVisible();
    const mood = screen.getByRole('button', { name: 'psyche.presentation.mood' });
    expect(mood).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.queryByRole('img', { name: 'psyche.presentation.padTitle' })
    ).not.toBeInTheDocument();
    await user.click(mood);
    expect(screen.getByRole('img', { name: 'psyche.presentation.padTitle' })).toBeVisible();
    expect(screen.getByText('Current point')).toBeVisible();
  });
  it('offers independent closed mobile sections without nesting OCEAN under the mood toggle', async () => {
    mocks.desktop = false;
    usePsycheStore.getState().updateFromFullState(state());
    const { user } = renderWithProviders(<PsycheStateSummary lng="fr" />);
    for (const name of [
      'psyche.presentation.mood',
      'psyche.presentation.relationship',
      'psyche.presentation.drivesTitle',
    ])
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'false');
    const ocean = screen.getByText('psyche.education.traits.title');
    const confidence = screen.getByText('psyche.education.drives.efficacy_title');
    expect(ocean).toBeVisible();
    expect(confidence).toBeVisible();
    expect(ocean.closest('details')).not.toHaveAttribute('open');
    expect(confidence.closest('details')).not.toHaveAttribute('open');
    expect(screen.queryByRole('meter', { name: 'psyche.depth' })).not.toBeInTheDocument();
    await user.click(ocean);
    expect(screen.getByRole('meter', { name: 'psyche.education.traits.openness' })).toHaveAttribute(
      'aria-valuenow',
      '82'
    );
    expect(screen.getByRole('button', { name: 'psyche.presentation.mood' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    await user.click(screen.getByRole('button', { name: 'psyche.presentation.relationship' }));
    expect(screen.getByRole('meter', { name: 'psyche.depth' })).toHaveAttribute(
      'aria-valuenow',
      '60'
    );
    await user.click(screen.getByRole('button', { name: 'psyche.presentation.drivesTitle' }));
    expect(screen.getByRole('meter', { name: 'psyche.history.engagement' })).toHaveAttribute(
      'aria-valuenow',
      '67'
    );
  });
  it('keeps every recorded emotion visible, even when more than three arcs are readable', () => {
    const emotions = Array.from({ length: 8 }, (_, index) => ({
      name: `emotion-${index}`,
      intensity: 0.9 - index / 10,
      triggered_at: '',
    }));
    usePsycheStore.getState().updateFromFullState(state({ active_emotions: emotions }));
    renderWithProviders(<PsycheStateSummary lng="fr" />);
    expect(
      within(screen.getByRole('region', { name: 'psyche.activeEmotion' })).getAllByRole('meter')
    ).toHaveLength(8);
  });
});

it('keeps native term and definition semantics while exposing each measure', async () => {
  usePsycheStore.getState().updateFromFullState(state());
  const { user } = renderWithProviders(<PsycheStateSummary lng="fr" />);
  expect(screen.getAllByRole('definition')).toHaveLength(3);
  await user.click(screen.getByText('psyche.education.traits.title'));
  expect(screen.getAllByRole('definition')).toHaveLength(8);
  expect(screen.getByRole('meter', { name: 'psyche.education.mood.pleasure' })).toHaveAttribute(
    'aria-valuenow',
    '0.4'
  );
});
