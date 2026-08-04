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
 * children only while open, so no PAGE of rows is fetched for a section nobody
 * opened. `onOpenChange` gates that query.
 *
 * The badge is the exception, and the reason it exists: its total arrives with
 * the hub's single count read, so a folded section is chosen from rather than
 * opened to find out whether it holds anything.
 */

import type { ReactNode } from 'react';
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
  /**
   * EXACT total over the whole set; also the folded badge.
   *
   * `undefined` means NOT KNOWN YET — the badge then says "—" rather than
   * "0", which would be a claim nobody has verified. It stops being undefined
   * as soon as the hub's single count read lands, so a folded section is
   * choosable without opening it.
   */
  total: number | undefined;
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

  return (
    <SettingsDisclosure
      icon={icon}
      title={title}
      // The NUMBER only: `SettingsDisclosure` already wraps whatever it is
      // given in the house pill, and a second styled span nested one pill
      // inside another. "—" while NOTHING is known yet — never "0", which
      // would be a claim nobody has verified.
      badge={total === undefined ? '—' : total}
      // Every COUNT wears the primary tint, like every other badge in the app
      // (owner call, 2026-08-04) — a count is information, and a grey pill read
      // as decoration. Zero included: an empty section is a fact, not a
      // different kind of thing.
      //
      // The one exception is the UNKNOWN state, which is not a count at all:
      // "—" stays neutral so it cannot be mistaken for "there is something
      // here".
      badgeClassName={
        total === undefined ? undefined : 'border border-primary/20 bg-primary/10 text-primary'
      }
      // Visible WHILE FOLDED: it is what the reader chooses from, and it is
      // the only thing telling them that reminders and routines list the
      // FUTURE rather than a history.
      description={subtitle}
      onOpenChange={onOpenChange}
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
              totalItems={total ?? 0}
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
