/**
 * PsycheSettings — toggling a psyche flag (persist + toast success/error).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { usePsyche } = vi.hoisted(() => ({ usePsyche: vi.fn() }));
vi.mock('@/hooks/usePsyche', () => ({ usePsyche }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { PsycheSettings } from '../PsycheSettings';
import type { usePsyche as usePsycheFn } from '@/hooks/usePsyche';

type PsycheHook = ReturnType<typeof usePsycheFn>;

// PsycheSettings renders inside an open SettingsSection card (ADR-227), so
// its controls are visible on mount.
function renderPsyche() {
  return renderWithProviders(
    <PsycheSettings lng="en" />
  );
}

function hook(over: Partial<PsycheHook> = {}) {
  return {
    settings: {
      psyche_enabled: false,
      psyche_display_avatar: true,
      psyche_sensitivity: 50,
      psyche_stability: 50,
    },
    isUpdatingSettings: false,
    isResetting: false,
    updateSettings: vi.fn().mockResolvedValue(undefined),
    resetPsyche: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('PsycheSettings', () => {
  it('enabling the psyche engine persists it and toasts success', async () => {
    const updateSettings = vi.fn().mockResolvedValue(undefined);
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
