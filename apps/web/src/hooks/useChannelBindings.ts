import { useCallback } from 'react';
import { useApiMutation } from './useApiMutation';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';
import { useApplicationResourceSync } from './useApplicationResourceSync';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

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
  const { t } = useTranslation();
  const {
    data: listData,
    loading,
    error,
    refetch,
    ownerId,
  } = useApplicationAccountQuery<ChannelBindingListResponse>(ENDPOINT, 'ChannelBindings');
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'channels', refetch, release);
  const refreshSaved = useCallback(async () => {
    try { await refetch(); }
    catch { if (isCurrent()) toast.error(t('settings.application_tools.sync_failed')); }
  }, [refetch, isCurrent, t]);

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
      if (!isCurrent()) return undefined;
      const result = await generateOtpMutation.mutate(
        `${ENDPOINT}/otp/generate?channel_type=${encodeURIComponent(channelType)}`
      );
      return isCurrent() ? result : undefined;
    },
    [generateOtpMutation, isCurrent]
  );

  const toggleBinding = useCallback(
    async (bindingId: string) => {
      if (!isCurrent()) return undefined;
      const result = await toggleMutation.mutate(`${ENDPOINT}/${bindingId}/toggle`);
      if (!isCurrent()) return undefined;
      if (result) await refreshSaved();
      return isCurrent() ? result : undefined;
    },
    [toggleMutation, isCurrent, refreshSaved]
  );

  const unlinkBinding = useCallback(
    async (bindingId: string) => {
      if (!isCurrent()) return;
      await deleteMutation.mutate(`${ENDPOINT}/${bindingId}`);
      if (isCurrent()) await refreshSaved();
    },
    [deleteMutation, isCurrent, refreshSaved]
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
