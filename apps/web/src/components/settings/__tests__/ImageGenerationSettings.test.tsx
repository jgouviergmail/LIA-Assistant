/**
 * ImageGenerationSettings — the options-driven dropdowns across loading
 * (skeletons), the unavailable-pricing error, and the loaded selectors;
 * enabling generation (persist + refresh + toast), the error path, and the
 * no-user guard; the prompt enhancement switch (ADR-315), offered only when the
 * server would honour it.
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
  active_model: 'gpt-image-2',
  provider: 'openai',
  qualities: [
    { value: 'low', min_cost_usd: 0.01, max_cost_usd: 0.02 },
    { value: 'high', min_cost_usd: 0.05, max_cost_usd: 0.08 },
  ],
  sizes: [
    {
      value: '1024x1024',
      orientation: 'square',
      tier: null,
      label_key: 'settings.image_generation.size_square',
    },
  ],
  effective_quality: 'low',
  effective_size: '1024x1024',
  prompt_enhancement_available: true,
};

// A Qwen offer: one quality, 1K and 2K sizes. The server has mapped the
// person's stored OpenAI quality onto the one Qwen offers.
const QWEN_OPTIONS: ImageGenerationOptions = {
  active_model: 'qwen-image-3.0-pro',
  provider: 'qwen',
  qualities: [{ value: 'standard', min_cost_usd: 0.034, max_cost_usd: 0.069 }],
  sizes: [
    {
      value: '1024x1536',
      orientation: 'portrait',
      tier: '1k',
      label_key: 'settings.image_generation.size_portrait',
    },
    {
      value: '1632x2448',
      orientation: 'portrait',
      tier: '2k',
      label_key: 'settings.image_generation.size_portrait',
    },
  ],
  effective_quality: 'standard',
  effective_size: '1632x2448',
  prompt_enhancement_available: false,
};

const enableSwitch = () => screen.getByRole('switch', { name: 'settings.image_generation.enable' });
const enhancementSwitch = () =>
  screen.queryByRole('switch', { name: 'settings.image_generation.prompt_enhancement' });

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

describe('ImageGenerationSettings — what the next image uses', () => {
  it('shows the server mapping of a stored value the model does not offer', () => {
    useAuth.mockReturnValue(
      authed({
        image_generation_default_quality: 'high',
        image_generation_default_size: '1632x2448',
      })
    );
    useImageGenerationOptions.mockReturnValue(dataQuery(QWEN_OPTIONS));
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    const [quality, size] = screen.getAllByRole('combobox');
    expect(quality).toHaveTextContent('settings.image_generation.quality_standard');
    // A size carries its tier, so two portraits of two resolutions read apart.
    expect(size).toHaveTextContent('2K (1632x2448)');
  });

  it('shows a stored value the model offers, even before the options refresh', () => {
    useAuth.mockReturnValue(authed({ image_generation_default_size: '1024x1536' }));
    useImageGenerationOptions.mockReturnValue(dataQuery(QWEN_OPTIONS));
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('1K (1024x1536)');
  });
});

describe('ImageGenerationSettings — enable toggle', () => {
  it('enabling generation persists it, refreshes and toasts', async () => {
    const ctx = authed({ image_generation_enabled: false });
    useAuth.mockReturnValue(ctx);
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    await user.click(enableSwitch());
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
    await user.click(enableSwitch());
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('does not persist when no user is authenticated', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    await user.click(enableSwitch());
    expect(patch).not.toHaveBeenCalled();
  });
});

describe('ImageGenerationSettings — prompt enhancement (ADR-315)', () => {
  it('is offered only when the server would honour it', () => {
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { unmount } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(enhancementSwitch()).toBeInTheDocument();
    expect(enhancementSwitch()).toHaveAccessibleDescription(
      'settings.image_generation.prompt_enhancement_description'
    );
    unmount();

    useImageGenerationOptions.mockReturnValue(dataQuery(QWEN_OPTIONS));
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(enhancementSwitch()).not.toBeInTheDocument();
  });

  it('is not offered while the options load or when they fail', () => {
    useImageGenerationOptions.mockReturnValue(loadingQuery());
    const { unmount } = renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(enhancementSwitch()).not.toBeInTheDocument();
    unmount();

    useImageGenerationOptions.mockReturnValue(errorQuery());
    renderWithProviders(<ImageGenerationSettings lng="en" />);
    expect(enhancementSwitch()).not.toBeInTheDocument();
  });

  it('reflects the stored choice and persists a change', async () => {
    const ctx = authed({ image_generation_prompt_enhancement: true });
    useAuth.mockReturnValue(ctx);
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);

    const toggle = enhancementSwitch();
    expect(toggle).toBeChecked();
    await user.click(toggle!);

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/u1', {
        image_generation_prompt_enhancement: false,
      })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
  });

  it('is operable from the keyboard', async () => {
    useImageGenerationOptions.mockReturnValue(dataQuery(OPTIONS));
    const { user } = renderWithProviders(<ImageGenerationSettings lng="en" />);

    enhancementSwitch()!.focus();
    await user.keyboard(' ');

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/u1', {
        image_generation_prompt_enhancement: true,
      })
    );
  });
});
