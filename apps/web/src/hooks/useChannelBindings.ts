import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Channel binding from the API.
 */
export interface ChannelBinding {
  id: string;
  channel_type: string;
  channel_user_id: string;
  channel_username: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * OTP generation response.
 */
export interface OTPGenerateResponse {
  code: string;
  expires_in_seconds: number;
  bot_username: string | null;
  channel_type: string;
}

/**
 * Toggle response.
 */
export interface ChannelBindingToggleResponse {
  id: string;
  is_active: boolean;
}

/**
 * API list response shape.
 */
interface ChannelBindingListResponse {
  bindings: ChannelBinding[];
  total: number;
  telegram_bot_username: string | null;
}

const ENDPOINT = '/channels';

/**
 * Hook for channel bindings CRUD operations (Telegram, etc.).
 */
export function useChannelBindings() {
  // Query: list all bindings
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<ChannelBindingListResponse>(ENDPOINT, {
    componentName: 'ChannelBindings',
    initialData: { bindings: [], total: 0, telegram_bot_username: null },
  });

  const bindings = listData?.bindings ?? [];
  const total = listData?.total ?? 0;
  const telegramBotUsername = listData?.telegram_bot_username ?? null;

  // Mutations
  const generateOtpMutation = useApiMutation<{ channel_type: string }, OTPGenerateResponse>({
    method: 'POST',
    componentName: 'ChannelBindings',
  });

  const toggleMutation = useApiMutation<void, ChannelBindingToggleResponse>({
    method: 'PATCH',
    componentName: 'ChannelBindings',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'ChannelBindings',
  });

  // Handlers
  const generateOtp = useCallback(
    async (channelType: string = 'telegram') => {
      const result = await generateOtpMutation.mutate(
        `${ENDPOINT}/otp/generate?channel_type=${channelType}`
      );
      return result;
    },
    [generateOtpMutation]
  );

  const toggleBinding = useCallback(
    async (bindingId: string) => {
      const result = await toggleMutation.mutate(`${ENDPOINT}/${bindingId}/toggle`);
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            bindings: prev.bindings.map(b =>
              b.id === bindingId ? { ...b, is_active: result.is_active } : b
            ),
          };
        });
      }
      return result;
    },
    [toggleMutation, setData]
  );

  const unlinkBinding = useCallback(
    async (bindingId: string) => {
      await deleteMutation.mutate(`${ENDPOINT}/${bindingId}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          bindings: prev.bindings.filter(b => b.id !== bindingId),
          total: prev.total - 1,
        };
      });
    },
    [deleteMutation, setData]
  );

  return {
    // Data
    bindings,
    total,
    telegramBotUsername,
    loading,
    error,
    refetch,

    // Mutations
    generateOtp,
    toggleBinding,
    unlinkBinding,

    // Mutation states
    generatingOtp: generateOtpMutation.loading,
    toggling: toggleMutation.loading,
    unlinking: deleteMutation.loading,
  };
}
