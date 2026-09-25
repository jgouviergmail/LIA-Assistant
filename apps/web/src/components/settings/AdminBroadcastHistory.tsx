'use client';

/**
 * The sent-broadcasts history, under the admin send form (ADR-312).
 *
 * Each row states what an administrator needs to answer « who got what, and is
 * it still showing? »: when it was sent, the message as written, the audience
 * (everyone, or the named selection with the exact count of the rest), the
 * expiry chosen and whether it has passed, delivery and read receipts. Every
 * figure comes from the server's own aggregates — the page never counts its
 * own rows (ADR-185).
 *
 * A refresh after a send keeps the list mounted (`aria-busy`), never a
 * first-load skeleton: the reader keeps their place (frontend doctrine).
 */

import { useId, useState, type ReactNode } from 'react';
import { History, RotateCcw, UserCheck, Users } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton } from '@/components/ui/skeleton';
import { useBroadcastHistory, type BroadcastHistoryItem } from '@/hooks/useBroadcastHistory';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatInstant } from '@/lib/format-instant';
import { cn } from '@/lib/utils';

type Translate = ReturnType<typeof useTranslation>['t'];

/** A message longer than this (characters or lines) folds behind « Show more ». */
const FOLD_CHARS = 240;
const FOLD_LINES = 4;

/** Whether a message is long enough to fold. */
export function isFoldable(message: string): boolean {
  return message.length > FOLD_CHARS || message.split('\n').length > FOLD_LINES;
}

/** Names joined the reader's way (« A, B et C », « A、B和C »), plain commas if unsupported. */
function joinNames(names: string[], lng: Language): string {
  try {
    return new Intl.ListFormat(lng, { style: 'long', type: 'conjunction' }).format(names);
  } catch {
    return names.join(', ');
  }
}

function recipientsText(item: BroadcastHistoryItem, lng: Language, t: Translate): string {
  if (item.audience === 'all') return t('settings.admin.broadcast.history.to_everyone');
  const names = item.recipients.map(recipient => recipient.full_name || recipient.email);
  const rest = Math.max(0, item.recipients_total - names.length);
  const shown = joinNames(names, lng);
  return rest > 0
    ? t('settings.admin.broadcast.history.named_and_more', { names: shown, count: rest })
    : shown || t('settings.admin.broadcast.history.no_recipient_left');
}

function expiryText(item: BroadcastHistoryItem, lng: Language, t: Translate): string {
  if (item.expires_at === null) return t('settings.admin.broadcast.history.never_expires');
  const date = formatInstant(item.expires_at, lng);
  const when = item.is_expired
    ? t('settings.admin.broadcast.history.expired_on', { date })
    : t('settings.admin.broadcast.history.expires_on', { date });
  return item.expires_in_days === null
    ? when
    : `${when} · ${t('settings.admin.broadcast.history.delay_days', { count: item.expires_in_days })}`;
}

function HistoryRow({ item, lng, t }: { item: BroadcastHistoryItem; lng: Language; t: Translate }) {
  const [expanded, setExpanded] = useState(false);
  const foldable = isFoldable(item.message);
  const AudienceIcon = item.audience === 'all' ? Users : UserCheck;

  return (
    <li className="space-y-2 rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <time dateTime={item.sent_at} className="text-sm font-medium">
          {formatInstant(item.sent_at, lng)}
        </time>
        <div className="flex flex-wrap items-center gap-1.5">
          {item.is_expired && (
            <Badge variant="secondary">{t('settings.admin.broadcast.history.expired')}</Badge>
          )}
          <Badge icon={<AudienceIcon className="h-3 w-3" aria-hidden="true" />}>
            {item.audience === 'all'
              ? t('settings.admin.broadcast.all_users')
              : t('settings.admin.broadcast.selected_users')}
          </Badge>
        </div>
      </div>

      <p
        className={cn(
          'whitespace-pre-wrap break-words text-sm',
          foldable && !expanded && 'line-clamp-3'
        )}
      >
        {item.message}
      </p>
      {foldable && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(open => !open)}
          className="rounded text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {expanded
            ? t('settings.admin.broadcast.history.show_less')
            : t('settings.admin.broadcast.history.show_more')}
        </button>
      )}

      <dl className="grid gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
        <div className="flex gap-1">
          <dt className="shrink-0">{t('settings.admin.broadcast.history.recipients_label')}</dt>
          <dd className="min-w-0 break-words text-foreground">{recipientsText(item, lng, t)}</dd>
        </div>
        <div className="flex gap-1">
          <dt className="shrink-0">{t('settings.admin.broadcast.history.expiry_label')}</dt>
          <dd className="min-w-0 break-words">{expiryText(item, lng, t)}</dd>
        </div>
        <div className="flex gap-1">
          <dt className="shrink-0">{t('settings.admin.broadcast.history.delivery_label')}</dt>
          <dd className="min-w-0 break-words">
            {t('settings.admin.broadcast.history.delivery', {
              reached: item.reached_count,
              sent: item.fcm_sent,
              failed: item.fcm_failed,
            })}
          </dd>
        </div>
        <div className="flex gap-1">
          <dt className="shrink-0">{t('settings.admin.broadcast.history.reads_label')}</dt>
          <dd>{item.read_count}</dd>
        </div>
        {item.sender_name && (
          <div className="flex gap-1">
            <dt className="shrink-0">{t('settings.admin.broadcast.history.sender_label')}</dt>
            <dd className="min-w-0 break-words">{item.sender_name}</dd>
          </div>
        )}
      </dl>
    </li>
  );
}

export interface AdminBroadcastHistoryProps {
  lng: Language;
  /** Bumped by the send form after a broadcast leaves. */
  refreshKey: number;
}

export function AdminBroadcastHistory({ lng, refreshKey }: AdminBroadcastHistoryProps) {
  const { t } = useTranslation(lng);
  const history = useBroadcastHistory(refreshKey);
  const titleId = useId();
  const items = history.items ?? [];

  let body: ReactNode;
  if (history.firstLoad) {
    body = (
      <>
        <LoadingAnnouncement />
        <div className="space-y-3">
          {[0, 1].map(index => (
            <Skeleton key={index} className="h-28 w-full" />
          ))}
        </div>
      </>
    );
  } else if (history.error && history.items === undefined) {
    body = (
      <div className="flex flex-col items-center gap-2">
        <EmptyState icon={History} description={t('settings.admin.broadcast.history.load_error')} />
        <Button variant="outline" size="sm" onClick={() => void history.refetch()}>
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          {t('settings.admin.broadcast.history.retry')}
        </Button>
      </div>
    );
  } else if (history.total === 0) {
    body = <EmptyState icon={History} description={t('settings.admin.broadcast.history.empty')} />;
  } else {
    body = (
      <>
        <ul aria-busy={history.loading} aria-labelledby={titleId} className="space-y-3">
          {items.map(item => (
            <HistoryRow key={item.id} item={item} lng={lng} t={t} />
          ))}
        </ul>
        {history.totalPages > 1 && (
          <Pagination
            currentPage={history.page}
            totalPages={history.totalPages}
            onPageChange={history.setPage}
            totalItems={history.total}
            loading={history.loading}
            variant="justified"
            labels={{
              previous: t('common.previous'),
              next: t('common.next'),
              pageInfo: (current, pages) =>
                t('common.pagination.page_info', { current, total: pages }),
              totalItems: count => t('common.pagination.total_items', { count }),
            }}
          />
        )}
      </>
    );
  }

  return (
    <section aria-labelledby={titleId} className="space-y-3">
      {/* h4: the settings section above already titles itself with an h3. */}
      <h4 id={titleId} className="flex items-center gap-2 text-sm font-semibold">
        <History className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('settings.admin.broadcast.history.title')}
      </h4>
      {body}
    </section>
  );
}
