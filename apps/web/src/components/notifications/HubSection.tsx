'use client';

/**
 * One section of the notifications hub: a folded block, a page, a total.
 *
 * The hub stacks five of these. What they share — and what would drift if each
 * wrote it out — is not only the chrome but the ORDER of the states and the
 * three rules behind them:
 *
 * - the error is checked BEFORE emptiness: "nothing yet" on a failed fetch
 *   tells the reader LIA has been silent, which may be false;
 * - the first-load spinner is keyed on the absence of data, never on `error`
 *   (a refetch clears it and would unmount the list mid-refresh);
 * - the badge carries the EXACT total, so a folded section is choosable and a
 *   cap is stated rather than applied in silence (ADR-185).
 *
 * Folded by design, and folded means UNMOUNTED: `SettingsDisclosure` renders
 * children only while open, which is what lets five sections cost zero
 * requests on arrival. `onOpenChange` gates the query.
 */

import { useState, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Pagination } from '@/components/ui/pagination';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';

export interface HubSectionProps {
  icon: LucideIcon;
  /** Already translated. */
  title: string;
  /**
   * What this section holds, in one line, under the title.
   *
   * Load-bearing for the two FUTURE sections: reminders and routines list what
   * is COMING, while the three others list what already reached the reader. A
   * reminder is deleted the moment it fires, so looking for a history there
   * would be looking for something that cannot exist — the subtitle says so
   * instead of letting the reader find out by finding nothing.
   */
  subtitle: string;
  /** Already translated — shown in place of the list when the set is empty. */
  emptyLabel: string;
  /** Already translated — shown in place of the list when the fetch failed. */
  errorLabel: string;
  /** EXACT total over the whole set; also the folded badge. */
  total: number;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** Whether the section holds anything to render right now. */
  isEmpty: boolean;
  /** Notified on fold/unfold, so the caller can gate its query. */
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}

export function HubSection({
  icon,
  title,
  subtitle,
  emptyLabel,
  errorLabel,
  total,
  page,
  totalPages,
  onPageChange,
  firstLoad,
  loading,
  error,
  isEmpty,
  onOpenChange,
  children,
}: HubSectionProps) {
  const { t } = useTranslation();
  // Mirrored locally so the badge can say "—" before the first read rather
  // than "0", which would be a claim nobody has verified yet.
  const [opened, setOpened] = useState(false);

  return (
    <SettingsDisclosure
      icon={icon}
      title={title}
      badge={
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
          {opened && !firstLoad ? total : '—'}
        </span>
      }
      // Visible WHILE FOLDED: it is what the reader chooses from, and it is
      // the only thing telling them that reminders and routines list the
      // FUTURE rather than a history.
      description={subtitle}
      onOpenChange={open => {
        if (open) setOpened(true);
        onOpenChange(open);
      }}
    >
      {firstLoad ? (
        <div className="flex justify-center py-6">
          <LoadingSpinner className="h-5 w-5" />
        </div>
      ) : error ? (
        // BEFORE emptiness, deliberately: see the note at the top.
        <p role="alert" className="text-sm text-destructive">
          {errorLabel}
        </p>
      ) : isEmpty ? (
        <p className="text-sm italic text-muted-foreground">{emptyLabel}</p>
      ) : (
        <div className="space-y-3" aria-busy={loading || undefined}>
          {children}
          {totalPages > 1 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={onPageChange}
              totalItems={total}
              loading={loading}
              variant="centered"
              labels={{
                previous: t('common.previous'),
                next: t('common.next'),
                pageInfo: (current, count) =>
                  t('notifications_hub.page_info', { current, total: count }),
                totalItems: count => t('notifications_hub.total_items', { count }),
              }}
            />
          )}
        </div>
      )}
    </SettingsDisclosure>
  );
}
