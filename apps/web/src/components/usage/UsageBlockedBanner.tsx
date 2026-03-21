'use client';

import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface UsageBlockedBannerProps {
  /** Reason for blocking (from admin or system) */
  blockReason: string | null;
}

/**
 * Alert banner displayed above the chat input when user is blocked.
 *
 * Shows a destructive-themed alert with the block reason if provided.
 */
export function UsageBlockedBanner({ blockReason }: UsageBlockedBannerProps) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 bg-destructive/10 border-b border-destructive/30 px-4 py-3">
      <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
      <div className="text-xs">
        <span className="font-semibold text-destructive">{t('usage_limits.blocked.title')}</span>
        <span className="text-destructive/80 ml-1">{t('usage_limits.blocked.message')}</span>
        {blockReason && <p className="mt-0.5 text-destructive/60 italic">{blockReason}</p>}
      </div>
    </div>
  );
}
