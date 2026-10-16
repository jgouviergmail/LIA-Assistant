/**
 * PsycheSettings — toggling a psyche flag (persist + toast success/error).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { usePsyche, useAuth } = vi.hoisted(() => ({ usePsyche: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/components/psyche/PsycheLLMSummary', () => ({
  PsycheLLMSummary: () => <section aria-label="point">point</section>,
}));
vi.mock('@/components/psyche/PsycheStateSummary', () => ({
  PsycheStateSummary: ({ summary }: { summary?: React.ReactNode }) => (
    <>
      {summary}
      <p>observed mood</p>
    </>
  ),
}));
vi.mock('@/components/psyche/PsycheHistory', () => ({
  PsycheHistory: () => <p>observed history</p>,
}));
vi.mock('@/components/psyche/PsycheEducation', () => ({ PsycheEducation: () => <p>education</p> }));
vi.mock('@/hooks/usePsyche', () => ({ usePsyche }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { PsycheSettings } from '../PsycheSettings';
import type { usePsyche as usePsycheFn } from '@/hooks/usePsyche';

type PsycheHook = ReturnType<typeof usePsycheFn>;

// PsycheSettings renders inside an open SettingsSection card (ADR-227), so
// its controls are visible on mount.
function renderPsyche() {
  return renderWithProviders(<PsycheSettings lng="en" />);
}

function hook(over: Partial<PsycheHook> = {}) {
  return {
    settings: {
      psyche_enabled: false,
      psyche_display_avatar: true,
      psyche_sensitivity: 50,
      psyche_stability: 50,
    },
    state: null,
    error: null,
    stateError: null,
    settingsError: null,
    isLoading: false,
    refetchState: vi.fn().mockResolvedValue(undefined),
    refetchSettings: vi.fn().mockResolvedValue(undefined),
    isUpdatingSettings: false,
    isResetting: false,
    updateSettings: vi.fn().mockResolvedValue(undefined),
    resetPsyche: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
});

describe('PsycheSettings', () => {
  it('reports an unattested update as failed instead of announcing success', async () => {
    const updateSettings = vi.fn().mockResolvedValue(undefined);
    usePsyche.mockReturnValue(hook({ updateSettings }));
    const { user } = renderPsyche();
    await user.click(screen.getAllByRole('switch')[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not announce success for an obsolete account callback', async () => {
    const updateSettings = vi.fn().mockResolvedValue(null);
    usePsyche.mockReturnValue(hook({ updateSettings }));
    const { user } = renderPsyche();
    await user.click(screen.getAllByRole('switch')[0]);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('enabling the psyche engine persists it and toasts success', async () => {
    const updateSettings = vi.fn().mockResolvedValue({ psyche_enabled: true });
    usePsyche.mockReturnValue(hook({ updateSettings }));
    const { user } = renderPsyche();
    await user.click(screen.getAllByRole('switch')[0]);
    expect(updateSettings).toHaveBeenCalledWith({ psyche_enabled: true });
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when the update rejects', async () => {
    const updateSettings = vi.fn().mockRejectedValue(new Error('boom'));
    usePsyche.mockReturnValue(hook({ updateSettings }));
    const { user } = renderPsyche();
    await user.click(screen.getAllByRole('switch')[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

describe('psyche presentation and confirmations', () => {
  it('opens the point and evolution but keeps commands folded and separates the three commands in the requested order', () => {
    const data = hook();
    data.settings.psyche_enabled = true;
    usePsyche.mockReturnValue(data);
    renderPsyche();
    expect(screen.getByRole('region', { name: 'point' })).toBeInTheDocument();
    for (const name of [
      'psyche.education.title',
      'psyche.settingsSection.title',
      'psyche.presentation.resets',
    ])
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'psyche.presentation.evolution' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    const names = screen.getAllByRole('button').map(button => button.textContent);
    expect(names.indexOf('psyche.education.title')).toBeLessThan(
      names.indexOf('psyche.settingsSection.title')
    );
    expect(names.indexOf('psyche.settingsSection.title')).toBeLessThan(
      names.indexOf('psyche.presentation.resets')
    );
  });
  it('refreshes page observations while keeping the point mounted', async () => {
    const data = hook();
    data.settings.psyche_enabled = true;
    usePsyche.mockReturnValue(data);
    const { user } = renderPsyche();
    await user.click(screen.getByRole('button', { name: 'common.refresh' }));
    expect(data.refetchState).toHaveBeenCalledTimes(1);
    expect(data.refetchSettings).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('region', { name: 'point' })).toBeInTheDocument();
  });
  it('requires confirmation for reset, ignores cancellation and serializes confirmed reset', async () => {
    let finish: (value: { status: string; level: string }) => void = () => {};
    const resetPsyche = vi.fn<PsycheHook['resetPsyche']>().mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const data = hook({ resetPsyche });
    data.settings.psyche_enabled = true;
    usePsyche.mockReturnValue(data);
    const { user } = renderPsyche();
    await user.click(screen.getByRole('button', { name: 'psyche.presentation.resets' }));
    await user.click(screen.getByRole('button', { name: 'psyche.softReset' }));
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(data.resetPsyche).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'psyche.softReset' }));
    await user.click(screen.getByRole('button', { name: 'psyche.softReset' }));
    expect(data.resetPsyche).toHaveBeenCalledTimes(1);
    await act(async () => finish({ status: 'reset', level: 'soft' }));
  });
  it('does not publish an obsolete account mutation error', async () => {
    let reject: (error: Error) => void = () => {};
    const data = hook({
      updateSettings: vi.fn().mockImplementation(
        () =>
          new Promise((_, fail) => {
            reject = fail;
          })
      ),
    });
    usePsyche.mockReturnValue(data);
    const { user, rerender } = renderPsyche();
    await user.click(screen.getAllByRole('switch')[0]);
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<PsycheSettings lng="en" />);
    await act(async () => reject(new Error('old failure')));
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('psyche observation retry', () => {
  it('reports a failed observation refresh without losing the point or leaving controls locked', async () => {
    const data = hook({
      refetchState: vi
        .fn()
        .mockRejectedValueOnce(new Error('offline'))
        .mockResolvedValue(undefined),
    });
    data.settings.psyche_enabled = true;
    usePsyche.mockReturnValue(data);
    const { user } = renderPsyche();
    const button = screen.getByRole('button', { name: 'common.refresh' });
    await user.click(button);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('psyche.presentation.readError'));
    expect(screen.getByRole('region', { name: 'point' })).toBeInTheDocument();
    expect(button).toHaveFocus();
    await user.click(button);
    expect(data.refetchState).toHaveBeenCalledTimes(2);
  });
});
