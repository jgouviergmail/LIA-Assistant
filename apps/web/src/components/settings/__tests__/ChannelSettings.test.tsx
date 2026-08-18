/**
 * ChannelSettings — the loading state, the empty/link affordance with OTP
 * generation, the bound-channel status with its active toggle (success + error),
 * and the destructive unlink flow (confirm → delete → toast).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type {
  ChannelBinding,
  useChannelBindings as useChannelBindingsFn,
} from '@/hooks/useChannelBindings';

const { useChannelBindings } = vi.hoisted(() => ({ useChannelBindings: vi.fn() }));
vi.mock('@/hooks/useChannelBindings', () => ({ useChannelBindings }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ChannelSettings } from '../ChannelSettings';

type ChannelsHook = ReturnType<typeof useChannelBindingsFn>;

function binding(over: Partial<ChannelBinding> = {}): ChannelBinding {
  return {
    id: 'b1',
    channel_type: 'telegram',
    channel_user_id: '12345',
    channel_username: 'alice',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

function hook(over: Partial<ChannelsHook> = {}) {
  return {
    bindings: [],
    total: 0,
    telegramBotUsername: 'LIABot',
    loading: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    generateOtp: vi.fn().mockResolvedValue(null),
    toggleBinding: vi.fn().mockResolvedValue(undefined),
    unlinkBinding: vi.fn().mockResolvedValue(undefined),
    generatingOtp: false,
    toggling: false,
    unlinking: false,
    ...over,
  };
}

function renderChannels() {
  return renderWithProviders(
    <ChannelSettings lng="en" />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('ChannelSettings — unbound', () => {
  it('shows a spinner while the bindings load', () => {
    useChannelBindings.mockReturnValue(hook({ loading: true, bindings: [] }));
    renderChannels();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('offers to link Telegram with the bot handle when none is bound', () => {
    useChannelBindings.mockReturnValue(hook({ bindings: [], telegramBotUsername: 'LIABot' }));
    renderChannels();
    expect(screen.getByText('settings.channels.empty_with_bot')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '@LIABot' })).toHaveAttribute(
      'href',
      'https://t.me/LIABot'
    );
    expect(
      screen.getByRole('button', { name: 'settings.channels.link_button' })
    ).toBeInTheDocument();
  });

  it('generates an OTP and reveals the code to send', async () => {
    const generateOtp = vi.fn().mockResolvedValue({
      code: '123456',
      expires_in_seconds: 300,
      bot_username: 'LIABot',
      channel_type: 'telegram',
    });
    useChannelBindings.mockReturnValue(hook({ bindings: [], generateOtp }));
    const { user } = renderChannels();
    await user.click(screen.getByRole('button', { name: 'settings.channels.link_button' }));
    expect(generateOtp).toHaveBeenCalledWith('telegram');
    expect(await screen.findByText('123456')).toBeInTheDocument();
  });
});

describe('ChannelSettings — bound', () => {
  it('reflects the active binding and toggles it', async () => {
    const toggleBinding = vi.fn().mockResolvedValue({ id: 'b1', is_active: false });
    useChannelBindings.mockReturnValue(
      hook({ bindings: [binding({ is_active: true })], toggleBinding })
    );
    const { user } = renderChannels();
    expect(screen.getByRole('switch')).toBeChecked();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toggleBinding).toHaveBeenCalledWith('b1'));
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when toggling fails', async () => {
    const toggleBinding = vi.fn().mockRejectedValue(new Error('boom'));
    useChannelBindings.mockReturnValue(hook({ bindings: [binding()], toggleBinding }));
    const { user } = renderChannels();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('unlinks the binding after confirmation', async () => {
    const unlinkBinding = vi.fn().mockResolvedValue(undefined);
    useChannelBindings.mockReturnValue(hook({ bindings: [binding()], unlinkBinding }));
    const { user } = renderChannels();
    await user.click(screen.getByRole('button', { name: 'settings.channels.unlink_button' }));
    // The confirm dialog opens with its own unlink action carrying the same
    // label as the card button; wait for the dialog, then click the action.
    await screen.findByText('settings.channels.unlink_confirm_title');
    const unlinkButtons = screen.getAllByRole('button', {
      name: 'settings.channels.unlink_button',
    });
    await user.click(unlinkButtons[unlinkButtons.length - 1]);
    await waitFor(() => expect(unlinkBinding).toHaveBeenCalledWith('b1'));
    expect(toast.success).toHaveBeenCalledTimes(1);
  });
});
