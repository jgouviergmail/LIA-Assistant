'use client';

/**
 * ConnectorNoticeBanner — actionable connector failure banners (Lot 3 P3,
 * ADR-134).
 *
 * Renders one banner per (connector, action) notice accumulated by the
 * reducer from `tool_error` execution steps. A "reconnect" notice links to
 * the connectors section of the settings; a "rate_limit" notice is
 * informational. Both are dismissible and cleared on the next message.
 * Renders nothing without notices.
 */

import { AlertTriangle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Link from 'next/link';

import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import type { ConnectorNotice } from '@/types/chat-state';

export interface ConnectorNoticeBannerProps {
  notices: ConnectorNotice[];
  onDismiss: (connectorType: string, action: ConnectorNotice['action']) => void;
}

function connectorLabel(connectorType: string): string {
  return isValidConnectorType(connectorType) ? CONNECTOR_LABELS[connectorType] : connectorType;
}

export function ConnectorNoticeBanner({ notices, onDismiss }: ConnectorNoticeBannerProps) {
  const { t, i18n } = useTranslation();
  // URL language segment, same derivation as the dashboard cards.
  const lng = (i18n.language || 'fr').split('-')[0];

  if (notices.length === 0) return null;

  return (
    <div className="space-y-1.5 px-4 pb-1.5" role="status">
      {notices.map(notice => {
        const label = connectorLabel(notice.connectorType);
        const message =
          notice.action === 'reconnect'
            ? t('chat.connector_notice.reconnect_message', { connector: label })
            : t('chat.connector_notice.rate_limit_message', { connector: label });
        return (
          <div
            key={`${notice.connectorType}-${notice.action}`}
            className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground/90"
          >
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
            <span className="min-w-0 flex-1">{message}</span>
            {notice.action === 'reconnect' && (
              <Link
                href={`/${lng}/dashboard/settings?section=connectors`}
                className="shrink-0 rounded-md bg-amber-500/20 px-2.5 py-1 font-medium text-amber-700 transition-colors hover:bg-amber-500/30 dark:text-amber-300"
              >
                {t('chat.connector_notice.reconnect_button')}
              </Link>
            )}
            <button
              type="button"
              aria-label={t('chat.connector_notice.dismiss')}
              onClick={() => onDismiss(notice.connectorType, notice.action)}
              className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
