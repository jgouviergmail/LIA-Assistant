/**
 * One linked sync source of a space — a Drive folder, a Gmail label (ADR-262).
 *
 * The two sources have the same lifecycle (idle/syncing/completed/error), the
 * same two actions and the same counters, so they have ONE card: the status
 * tone comes from the shared table, the icon and the wording from the caller.
 * Two copies of this markup drifted on the `idle` tone alone before.
 */

'use client';

import { useTranslation } from 'react-i18next';
import { AlertCircle, CheckCircle, Clock, Loader2, RefreshCw, Unlink } from 'lucide-react';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { RowActions } from '@/components/ui/row-actions';
import { lifecycleTone } from '@/lib/status-tone';
import type { RAGSourceSyncStatus } from '@/types/rag-spaces';

export interface SourceSyncCardProps {
  /** The source's own icon (a folder, an envelope). */
  icon: ReactNode;
  /** The folder name, the label name — never truncated by us, by CSS. */
  title: string;
  status: RAGSourceSyncStatus;
  /** i18n keys for the four lifecycle states, in the caller's namespace. */
  statusKeys: Record<RAGSourceSyncStatus, string>;
  /** "3 synced" / "12 files" — already-translated strings. */
  syncedLabel: string;
  totalLabel: string;
  lastSyncAt: string | null;
  /** Translated "Last synced {time}" builder — the caller owns the wording. */
  lastSyncedLabel: (time: string) => string;
  errorMessage: string | null;
  onSync: () => void;
  onUnlink: () => void;
  syncing?: boolean;
  syncTitle: string;
  unlinkTitle: string;
}

/** Icon per lifecycle state; the COLOUR is the shared table's, never ours. */
function statusIcon(status: RAGSourceSyncStatus) {
  switch (status) {
    case 'syncing':
      return <Loader2 className="h-3 w-3 animate-spin" />;
    case 'completed':
      return <CheckCircle className="h-3 w-3" />;
    case 'error':
      return <AlertCircle className="h-3 w-3" />;
    default:
      return <Clock className="h-3 w-3" />;
  }
}

/** Compact elapsed time without date-fns (minutes, hours, then days). */
export function formatRelativeTime(dateString: string): string {
  const diffMs = Date.now() - new Date(dateString).getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMinutes < 1) return '< 1 min';
  if (diffMinutes < 60) return `${diffMinutes} min`;
  if (diffHours < 24) return `${diffHours}h`;
  return `${diffDays}d`;
}

export function SourceSyncCard({
  icon,
  title,
  status,
  statusKeys,
  syncedLabel,
  totalLabel,
  lastSyncAt,
  lastSyncedLabel,
  errorMessage,
  onSync,
  onUnlink,
  syncing,
  syncTitle,
  unlinkTitle,
}: SourceSyncCardProps) {
  const { t } = useTranslation();

  return (
    <Card className="group">
      <CardContent className="p-4 flex items-center gap-3">
        <div className="shrink-0 rounded-lg bg-primary/10 p-2">{icon}</div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{title}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
            <Badge variant={lifecycleTone(status)} size="sm" icon={statusIcon(status)}>
              {t(statusKeys[status] ?? statusKeys.idle)}
            </Badge>
            <span>
              {syncedLabel}
              {' / '}
              {totalLabel}
            </span>
            {lastSyncAt && (
              <>
                <span>&middot;</span>
                <span>{lastSyncedLabel(formatRelativeTime(lastSyncAt))}</span>
              </>
            )}
          </div>
          {status === 'error' && errorMessage && (
            <p className="mt-1 text-xs text-destructive truncate">{errorMessage}</p>
          )}
        </div>

        {/* ADR-208: never `opacity-0 group-hover` — a keyboard focus would land
            on an invisible control. RowActions shows every action from `sm` up
            and folds them into a named "⋮" menu on phones. */}
        <RowActions
          // The "⋮" trigger NAMES ITS ROW: a list renders one per source, and
          // an anonymous "Actions" reads the same on every one (ADR-208).
          menuLabel={t('common.actions_for', { name: title })}
          actions={[
            {
              key: 'sync',
              label: syncTitle,
              icon: RefreshCw,
              onSelect: onSync,
              disabled: syncing || status === 'syncing',
              loading: status === 'syncing',
            },
            {
              key: 'unlink',
              label: unlinkTitle,
              icon: Unlink,
              tone: 'destructive',
              onSelect: onUnlink,
            },
          ]}
        />
      </CardContent>
    </Card>
  );
}
