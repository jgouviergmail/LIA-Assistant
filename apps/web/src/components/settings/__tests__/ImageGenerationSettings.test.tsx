/**
 * ImageGenerationSettings — the options-driven dropdowns across loading
 * (skeletons), the unavailable-pricing error, and the loaded selectors;
 * enabling generation (persist + refresh + toast), the error path, and the
 * no-user guard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import { dataQuery, loadingQuery, errorQuery } from '@/__tests__/api-mocks';
import type { User } from '@/lib/auth';
import type { ImageGenerationOptions } from '@/hooks/useImageGenerationOptions';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { useImageGenerationOptions } = vi.hoisted(() => ({ useImageGenerationOptions: vi.fn() }));
vi.mock('@/hooks/useImageGenerationOptions', () => ({ useImageGenerationOptions }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ImageGenerationSettings } from '../ImageGenerationSettings';

const OPTIONS: ImageGenerationOptions = {
  active_model: 'gpt-image-1',
  provider: 'openai',
  qualities: [
    { value: 'low', min_cost_usd: 0.01, max_cost_usd: 0.02 },
    { value: 'high', min_cost_usd: 0.05, max_cost_usd: 0.08 },
  ],
  sizes: [{ value: '1024x1024', label_key: 'settings.image_generation.size_square' }],
};

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAuth.mockReturnValue(authed());
});

describe('ImageGenerationSettings — options states', () => {
  it('shows only the client-side format selector while options load', () => {
    useImageGenerationOptions.mockReturnValue(loadingQuery());
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    // Quality/size render as skeletons (no combobox); only the format Select is one.
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
  });

  it('shows the unavailable message when the options request errors', () => {
    useImageGenerationOptions.mockReturnValue(errorQuery());
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(screen.getByText('settings.image_generation.options_unavailable')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
  });

  it('renders quality, size and format selectors once options load', () => {
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });
});

describe('ImageGenerationSettings — enable toggle', () => {
  it('enabling generation persists it, refreshes and toasts', async () => {
    const ctx = authed({ image_generation_enabled: false });
    useAuth.mockReturnValue(ctx);
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/u1', { image_generation_enabled: true })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('does not persist when no user is authenticated', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    expect(patch).not.toHaveBeenCalled();
  });
});
