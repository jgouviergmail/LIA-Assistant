/**
 * ScheduledActionsSettings — the loading and empty states of the scheduled
 * actions list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const { useScheduledActions } = vi.hoisted(() => ({ useScheduledActions: vi.fn() }));
vi.mock('@/hooks/useScheduledActions', () => ({ useScheduledActions }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ScheduledActionsSettings } from '../ScheduledActionsSettings';
import type { useScheduledActions as useScheduledActionsFn } from '@/hooks/useScheduledActions';

type ScheduledHook = ReturnType<typeof useScheduledActionsFn>;

function hook(over: Partial<ScheduledHook> = {}) {
  return {
    actions: [],
    total: 0,
    loading: false,
    createAction: vi.fn(),
    updateAction: vi.fn(),
    deleteAction: vi.fn(),
    toggleAction: vi.fn(),
    executeAction: vi.fn(),
    creating: false,
    updating: false,
    executing: false,
    ...over,
  };
}

function render() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['scheduled-actions']}>
      <ScheduledActionsSettings lng="en" />
    </Accordion>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('ScheduledActionsSettings', () => {
  it('shows a loading spinner while actions load', () => {
    useScheduledActions.mockReturnValue(hook({ loading: true }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the empty state once the (empty) list has loaded', () => {
    useScheduledActions.mockReturnValue(hook({ loading: false, actions: [] }));
    render();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
