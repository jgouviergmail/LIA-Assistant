import { useContext } from 'react';
import { BroadcastContext } from '@/lib/broadcast';

/**
 * Hook to access broadcast context.
 *
 * Note: BroadcastProvider has its own SSE and FCM listeners for broadcasts.
 * This hook is primarily used by BroadcastModal to display broadcasts.
 *
 * @example
 * ```tsx
 * const { currentBroadcast, showModal, handleDismiss } = useBroadcast();
 * ```
 *
 * @throws {Error} If used outside of BroadcastProvider
 */
export const useBroadcast = () => {
  const context = useContext(BroadcastContext);

  if (context === undefined) {
    throw new Error('useBroadcast must be used within a BroadcastProvider');
  }

  return context;
};
