/**
 * PsycheMilestoneWatcher — forward-only stage toasts with hydration guard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { toast } from 'sonner';

import { PsycheMilestoneWatcher } from '../PsycheMilestoneWatcher';
import { usePsycheStore } from '@/stores/psycheStore';

vi.mock('sonner', () => ({
  toast: { success: vi.fn() },
}));

describe('PsycheMilestoneWatcher', () => {
  beforeEach(() => {
    usePsycheStore.getState().reset();
    vi.mocked(toast.success).mockClear();
  });

  it('never toasts on hydration (store default -> server value)', () => {
    render(<PsycheMilestoneWatcher />);
    act(() => {
      usePsycheStore.setState({
        enabled: true,
        relationshipStage: 'STABLE',
        lastUpdated: '2026-07-11T00:00:00Z',
      });
    });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('toasts once on a forward transition', () => {
    usePsycheStore.setState({
      enabled: true,
      relationshipStage: 'ORIENTATION',
      lastUpdated: '2026-07-11T00:00:00Z',
    });
    render(<PsycheMilestoneWatcher />);

    act(() => {
      usePsycheStore.setState({ relationshipStage: 'EXPLORATORY' });
    });

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(vi.mocked(toast.success).mock.calls[0][0]).toBe('psyche.milestone.EXPLORATORY');
  });

  it('stays silent on a backward transition (full reset)', () => {
    usePsycheStore.setState({
      enabled: true,
      relationshipStage: 'AFFECTIVE',
      lastUpdated: '2026-07-11T00:00:00Z',
    });
    render(<PsycheMilestoneWatcher />);

    act(() => {
      usePsycheStore.setState({ relationshipStage: 'ORIENTATION' });
    });

    expect(toast.success).not.toHaveBeenCalled();
  });

  it('stays silent when psyche is disabled', () => {
    usePsycheStore.setState({
      enabled: false,
      relationshipStage: 'ORIENTATION',
      lastUpdated: '2026-07-11T00:00:00Z',
    });
    render(<PsycheMilestoneWatcher />);

    act(() => {
      usePsycheStore.setState({ relationshipStage: 'EXPLORATORY' });
    });

    expect(toast.success).not.toHaveBeenCalled();
  });
});
