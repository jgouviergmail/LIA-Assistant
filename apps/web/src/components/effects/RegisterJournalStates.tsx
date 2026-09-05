'use client';

/**
 * The three states both transparency registers share (ADR-263, lot 4).
 *
 * Extracted rather than duplicated, and rather than absorbed into the
 * complexity ratchet: the error banner, the first-load skeleton and the
 * load-more footer are identical in the action journal and the consultation
 * journal, and each of them is a branch the reading component no longer has to
 * carry. Two copies of a loading rule is two places for the charter to be
 * broken in one of them only.
 *
 * Loading rules (charter): first load → skeleton geometry matching the real
 * list + one announcement for the route; refresh of a populated list →
 * `aria-busy` on the container, never an unmount.
 */

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export interface RegisterErrorProps {
  /** What went wrong, already translated by the caller. */
  message: string;
  /** Label of the retry control. */
  retryLabel: string;
  onRetry: () => void;
}

/** The register could not be read at all — the only state offering a retry. */
export function RegisterError({ message, retryLabel, onRetry }: RegisterErrorProps) {
  return (
    <Alert variant="error">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      </div>
    </Alert>
  );
}

export interface RegisterSkeletonProps {
  /** Identifies which register is loading, for the tests that assert geometry. */
  slot: string;
}

/** First load only: the geometry of the list that is about to appear. */
export function RegisterSkeleton({ slot }: RegisterSkeletonProps) {
  return (
    <div data-slot={slot} className="space-y-3">
      <LoadingAnnouncement />
      <Skeleton className="h-6 w-40" />
      {Array.from({ length: 5 }, (_, index) => (
        <Skeleton key={index} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  );
}

export interface RegisterLoadMoreProps {
  label: string;
  /** True while a further page is in flight — never on the first load. */
  busy: boolean;
  onLoadMore: () => void;
}

/** A journal loads more, it does not paginate. */
export function RegisterLoadMore({ label, busy, onLoadMore }: RegisterLoadMoreProps) {
  return (
    <div className="flex justify-center">
      <Button onClick={onLoadMore} isLoading={busy}>
        {label}
      </Button>
    </div>
  );
}

export interface RegisterHeaderProps {
  /** Title and description, on the left. */
  children: React.ReactNode;
  /** Export and refresh controls, on the right. */
  actions: React.ReactNode;
}

/** Both registers head their section the same way. */
export function RegisterHeader({ children, actions }: RegisterHeaderProps) {
  return (
    // Stacked on a phone, side by side from `sm` up — and NEVER a wrap decided
    // by the title. `justify-between` with a wrapping title put the toolbar on
    // a different line depending on how long the heading happened to be, so
    // the two registers of one page showed their buttons in two places, and
    // differently again in each of the six languages (reported 2026-09-05).
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 sm:flex-1">{children}</div>
      <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{actions}</div>
    </header>
  );
}

export interface RegisterFilterProps<TToken> {
  /** Localised name of the group, for a reader arriving by keyboard. */
  label: string;
  /** Every value the filter offers, ``undefined`` first meaning « all ». */
  tokens: readonly TToken[];
  selected: TToken;
  onSelect: (token: TToken) => void;
  /** The visible wording of one token. */
  renderToken: (token: TToken) => string;
  /** A stable React key — a token may legitimately be ``undefined``. */
  keyOf: (token: TToken) => string;
}

/**
 * One filter row, shared by both registers.
 *
 * They had a component each, identical but for the tokens and the wording,
 * which is how they came to differ in placement and in presence. One
 * implementation makes them the same row by construction rather than by
 * vigilance.
 *
 * A selected chip is stated with `aria-current` and guarded in the handler —
 * never `disabled` on the control the click just landed on, which blurs it and
 * drops it from the tab order.
 */
export function RegisterFilter<TToken>({
  label,
  tokens,
  selected,
  onSelect,
  renderToken,
  keyOf,
}: RegisterFilterProps<TToken>) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {tokens.map(token => (
        <Button
          key={keyOf(token)}
          variant="outline"
          size="sm"
          aria-current={selected === token ? 'true' : undefined}
          className={cn(selected === token && 'border-primary text-primary')}
          onClick={() => {
            if (selected !== token) onSelect(token);
          }}
        >
          {renderToken(token)}
        </Button>
      ))}
    </div>
  );
}
