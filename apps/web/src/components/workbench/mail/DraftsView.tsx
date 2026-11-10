'use client';

/**
 * DraftsView — the drafts, where the provider keeps drafts (ADR-369, ADR-344).
 *
 * Newest first, each with whom it is addressed to so far; opening one reads it
 * whole (its revision travels with it) into the composer, where it is edited
 * and sent once. A draft is moved to the trash by its own row — no dialog:
 * nothing in the trash is lost. « More drafts » exactly when the provider has
 * more.
 */
import { FileText, Trash2 } from '@/lib/icons';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { RowActions } from '@/components/ui/row-actions';
import { Skeleton } from '@/components/ui/skeleton';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { addressLabel } from '@/lib/workbench/mail';
import type { MailDraftSummary } from '@/lib/workbench/types';

export interface DraftsViewProps {
  lng: Language;
  drafts: WorkbenchPageState<MailDraftSummary>;
  /** The draft being read into the composer, if any. */
  opening: string | null;
  /** The drafts whose trash is on its way. */
  trashing: ReadonlySet<string>;
  whenOf: (draft: MailDraftSummary) => string | null;
  onOpen: (draft: MailDraftSummary) => void;
  onTrash: (draft: MailDraftSummary) => void;
}

export function DraftsView({
  lng,
  drafts,
  opening,
  trashing,
  whenOf,
  onOpen,
  onTrash,
}: DraftsViewProps) {
  const { t } = useTranslation(lng);
  if (drafts.loading) {
    return (
      <div className="space-y-2 p-4" aria-busy="true">
        {[1, 2, 3].map(index => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    );
  }
  if (drafts.items.length === 0) {
    return drafts.error ? (
      <EmptyState
        description={t('workbench.mail.drafts.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void drafts.refresh() }}
      />
    ) : (
      <EmptyState icon={FileText} title={t('workbench.mail.drafts.empty')} />
    );
  }
  return (
    <div aria-busy={drafts.loadingMore || undefined} className="min-h-0 flex-1 overflow-y-auto">
      <ul aria-label={t('workbench.mail.folders.drafts')}>
        {drafts.items.map(draft => {
          const to = draft.to.map(addressLabel).join(', ') || t('workbench.mail.drafts.nobody');
          const subject = draft.subject || t('workbench.mail.no_subject');
          const when = whenOf(draft);
          return (
            <li key={draft.id} className="flex items-start gap-3 border-b px-4 py-3">
              <button
                type="button"
                onClick={() => onOpen(draft)}
                aria-busy={opening === draft.id || undefined}
                className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm">
                    {t('workbench.mail.drafts.to', { names: to })}
                  </span>
                  {when && (
                    <time
                      dateTime={draft.updated_at ?? undefined}
                      className="shrink-0 text-xs tabular-nums text-muted-foreground"
                    >
                      {when}
                    </time>
                  )}
                </span>
                <span className="truncate font-semibold">{subject}</span>
                {draft.snippet && (
                  <span className="truncate text-sm text-muted-foreground">{draft.snippet}</span>
                )}
              </button>
              <RowActions
                menuLabel={t('workbench.mail.drafts.actions', { subject })}
                actions={[
                  {
                    key: 'trash',
                    label: t('workbench.mail.trash'),
                    icon: Trash2,
                    tone: 'destructive',
                    loading: trashing.has(draft.id),
                    onSelect: () => onTrash(draft),
                  },
                ]}
              />
            </li>
          );
        })}
      </ul>
      {drafts.error !== null && (
        <p role="status" className="px-4 pt-3 text-sm text-destructive">
          {t('workbench.mail.drafts.failed')}
        </p>
      )}
      {drafts.nextToken && (
        <div className="p-3 text-center">
          <Button
            variant="outline"
            size="sm"
            isLoading={drafts.loadingMore}
            onClick={() => void drafts.loadMore()}
          >
            {t('workbench.mail.drafts.more')}
          </Button>
        </div>
      )}
    </div>
  );
}
