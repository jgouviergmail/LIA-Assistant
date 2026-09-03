/**
 * The provider publishes the COARSE recorder state only: a level tick or an
 * elapsed second must not re-render the composer (or any other consumer) —
 * measured concern for a two-hour meeting on a phone.
 */

import { act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import { LIVE_PHASES, isCapturingPhase, useMeetingRecorderStore } from '@/stores/meetingRecorderStore';

import {
  MeetingRecorderProvider,
  useMeetingRecorderContext,
} from '../MeetingRecorderProvider';

vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const noop = vi.fn();
const asyncNoop = vi.fn(async () => undefined);
const stop = vi.fn(async () => 'processing' as const);

// The hook under the provider is the real store read plus stable commands; the
// controller (browser APIs, network) is out of scope here.
vi.mock('@/hooks/useMeetingRecorder', () => ({
  useMeetingRecorder: (): UseMeetingRecorderReturn => {
    const state = useMeetingRecorderStore();
    return {
      ...state,
      isSupported: true,
      isCapturing: isCapturingPhase(state.phase),
      isLive: LIVE_PHASES.includes(state.phase),
      start: asyncNoop,
      stop,
      finalizeWithGaps: stop,
      resume: asyncNoop,
      discard: asyncNoop,
      dismiss: noop,
      continueAfterSilence: noop,
    };
  },
}));

// A spy call is how render counts are observed without mutating anything in render.
const renderSpy = vi.fn();

function Consumer() {
  const recorder = useMeetingRecorderContext();
  renderSpy();
  return <span data-testid="phase">{recorder?.phase ?? 'none'}</span>;
}

describe('MeetingRecorderProvider', () => {
  beforeEach(() => {
    useMeetingRecorderStore.getState().reset();
    renderSpy.mockClear();
  });

  it('gives consumers null when the feature is disabled', () => {
    renderWithProviders(
      <MeetingRecorderProvider lng="en" enabled={false}>
        <Consumer />
      </MeetingRecorderProvider>
    );
    expect(screen.getByTestId('phase')).toHaveTextContent('none');
  });

  it('re-renders consumers on a phase change, never on a level or elapsed tick', () => {
    renderWithProviders(
      <MeetingRecorderProvider lng="en" enabled>
        <Consumer />
      </MeetingRecorderProvider>
    );
    expect(screen.getByTestId('phase')).toHaveTextContent('idle');
    const afterMount = renderSpy.mock.calls.length;

    act(() => {
      const store = useMeetingRecorderStore.getState();
      store.setLevel(0.4);
      store.setLevel(0.7);
      store.setElapsed(12);
      store.setProgress(3, 1);
    });
    expect(renderSpy).toHaveBeenCalledTimes(afterMount);

    act(() => {
      useMeetingRecorderStore.getState().setPhase('recording');
    });
    expect(screen.getByTestId('phase')).toHaveTextContent('recording');
    expect(renderSpy).toHaveBeenCalledTimes(afterMount + 1);
  });
});
