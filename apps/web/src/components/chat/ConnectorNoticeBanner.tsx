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
 *
 * S4 — condensation. One expired Google refresh token invalidates Gmail,
 * Calendar and Drive at once, so a single failure can stack three rows
 * (~120 px) in the band between the thread and the composer, a surface S0
 * measured as already tight. When every pending notice shares the same action
 * they collapse into one summary line, expandable on demand. Mixed sets stay
 * listed in full: no single sentence would be true of all of them (see
 * `summarizeNotices`). Expanding keeps each notice's own dismiss control —
 * condensing the display must not take away per-connector control.
 */

import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Link from 'next/link';

import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { ConnectorNotice } from '@/types/chat-state';

import { summarizeNotices } from './connector-notice-summary';

export interface ConnectorNoticeBannerProps {
  notices: ConnectorNotice[];
  onDismiss: (connectorType: string, action: ConnectorNotice['action']) => void;
}

function connectorLabel(connectorType: string): string {
  return isValidConnectorType(connectorType) ? CONNECTOR_LABELS[connectorType] : connectorType;
}

/** Shared row chrome — one amber line, whatever it carries. */
const ROW =
  'flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground/90';

const RECONNECT_LINK =
  'shrink-0 rounded-md bg-amber-500/20 px-2.5 py-1 font-medium text-amber-700 transition-colors hover:bg-amber-500/30 dark:text-amber-300';

export function ConnectorNoticeBanner({ notices, onDismiss }: ConnectorNoticeBannerProps) {
  const { t, i18n } = useTranslation();
  // URL language segment, same derivation as the dashboard cards.
  const lng = (i18n.language || 'fr').split('-')[0];
  const [expanded, setExpanded] = useState(false);

  if (notices.length === 0) return null;

  const summary = summarizeNotices(notices);
  // Built from the SETTINGS_SECTIONS table, not by hand: the token is then
  // checked at compile time, and a renamed section updates this link with it.
  const settingsHref = settingsSectionHref(lng, 'connectors');

  /** One notice, in full. */
  const renderNotice = (notice: ConnectorNotice) => {
    const label = connectorLabel(notice.connectorType);
    const message =
      notice.action === 'reconnect'
        ? t('chat.connector_notice.reconnect_message', { connector: label })
        : t('chat.connector_notice.rate_limit_message', { connector: label });
    return (
      <div key={`${notice.connectorType}-${notice.action}`} className={ROW}>
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
        <span className="min-w-0 flex-1">{message}</span>
        {notice.action === 'reconnect' && (
          <Link href={settingsHref} className={RECONNECT_LINK}>
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
  };

  // A single notice, or mixed actions: nothing can be summarised without
  // losing meaning — show them as they are.
  if (!summary) {
    return (
      <div className="space-y-1.5 px-4 pb-1.5" role="status">
        {notices.map(renderNotice)}
      </div>
    );
  }

  const summaryText =
    summary.action === 'reconnect'
      ? t('chat.connector_notice.summary_reconnect', { count: summary.count })
      : t('chat.connector_notice.summary_rate_limit', { count: summary.count });

  return (
    <div className="space-y-1.5 px-4 pb-1.5" role="status">
      <div className={ROW}>
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
        <span className="min-w-0 flex-1">{summaryText}</span>
        {summary.action === 'reconnect' && (
          <Link href={settingsHref} className={RECONNECT_LINK}>
            {t('chat.connector_notice.reconnect_button')}
          </Link>
        )}
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={
            expanded
              ? t('chat.connector_notice.summary_collapse')
              : t('chat.connector_notice.summary_expand')
          }
          onClick={() => setExpanded(open => !open)}
          className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
        {/* Dismissing the group must stay possible WITHOUT expanding it:
            condensing the display cannot cost the user a capability they had
            when the notices were listed one by one. */}
        <button
          type="button"
          aria-label={t('chat.connector_notice.dismiss')}
          onClick={() => notices.forEach(n => onDismiss(n.connectorType, n.action))}
          className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
      {expanded && notices.map(renderNotice)}
    </div>
  );
}
