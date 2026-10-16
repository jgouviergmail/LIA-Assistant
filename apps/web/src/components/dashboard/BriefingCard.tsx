'use client';

import { ReactNode, useEffect, useId, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DOMAIN_CHIP_TONE, DOMAIN_ICON_TONE, type DomainTone } from '@/lib/domain-tone';
import { cn } from '@/lib/utils';
import { resolveErrorCtaKey, timeAgoLabel } from '@/lib/briefing-utils';
import type { CardSection, SectionData } from '@/types/briefing';
import { DASHBOARD_TILE_FRAME, TILE_ICON_BADGE, TileAmbience } from './DashboardTile';
import { UpdatedAtBadge } from './UpdatedAtBadge';

/**
 * The domain colour code shared with notification chips. A restrained icon
 * badge and top rule make cards easy to scan; the solid surface, text and
 * interaction states continue to follow the user's theme.
 */
export type CardTone = DomainTone;

/**
 * Freshness badge in the card header (D-04, extracted — CC discipline).
 * On OK/empty it dates the live/cache fetch; on error it dates the STALE
 * payload shown below (honesty: the timestamp belongs to the data, and an
 * error with no stale data shows no timestamp).
 */
function CardFreshnessBadge<T extends SectionData>({
  section,
  isError,
  justRefreshed,
}: {
  section: CardSection<T>;
  isError: boolean;
  justRefreshed: boolean;
}) {
  if (!isError) {
    return (
      <UpdatedAtBadge
        generatedAt={section.generated_at}
        showJustUpdated={justRefreshed}
        fromCache={section.from_cache}
        className="min-w-0 break-words text-right"
      />
    );
  }
  if (!section.stale_generated_at) return null;
  return (
    <UpdatedAtBadge
      generatedAt={section.stale_generated_at}
      fromCache
      className="min-w-0 break-words text-right"
    />
  );
}

/**
 * Error body (D-04, extracted — CC discipline): the message, the honest
 * freshness line (age of the shown stale data + last attempt), and the CTA.
 * Layout compacts to a banner when stale data rides below it.
 */
function CardErrorBody<T extends SectionData>({
  section,
  ctaKey,
  onErrorCta,
  busy,
}: {
  section: CardSection<T>;
  ctaKey: string | null;
  onErrorCta?: (trigger: HTMLButtonElement) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const hasFreshnessLine =
    section.last_attempt_at !== null ||
    (section.data !== null && section.stale_generated_at !== null);
  return (
    <div className={cn('flex flex-col gap-2', section.data ? 'shrink-0' : 'flex-1 justify-center')}>
      <p className="text-sm text-foreground/80 leading-snug">
        {section.error_message || t('dashboard.briefing.errors.generic')}
      </p>
      {hasFreshnessLine && (
        <p className="text-xs text-muted-foreground leading-snug" role="status">
          {section.data &&
            section.stale_generated_at &&
            t('dashboard.briefing.stale_data_age', {
              ago: timeAgoLabel(t, section.stale_generated_at),
            }) + ' · '}
          {section.last_attempt_at &&
            t('dashboard.briefing.last_attempt_ago', {
              ago: timeAgoLabel(t, section.last_attempt_at),
            })}
        </p>
      )}
      {ctaKey && onErrorCta && (
        <button
          type="button"
          aria-disabled={busy}
          onClick={event => {
            if (!busy) onErrorCta(event.currentTarget);
          }}
          className="self-start text-xs font-medium text-primary hover:text-primary/90 underline underline-offset-2 transition-colors"
        >
          {t(ctaKey)}
        </button>
      )}
    </div>
  );
}

export interface BriefingCardProps<T extends SectionData> {
  titleKey: string;
  icon: ReactNode;
  /** Domain accent for the icon badge and decorative rule. */
  tone: CardTone;
  section: CardSection<T>;
  isRefreshing: boolean;
  onRefresh: () => void;
  renderContent: (data: T) => ReactNode;
  emptyStateKey: string;
  /** Interpolation values of the empty-state sentence (e.g. the window it names). */
  emptyStateValues?: Record<string, string | number>;
  onErrorCta?: () => void;
  staggerIndex?: number;
  className?: string;
  /** When true, the OK content is vertically + horizontally centered inside the body. */
  centerContent?: boolean;
}

/**
 * Briefing card — handles 4 status states (OK/EMPTY/ERROR/NOT_CONFIGURED).
 *
 * Visual contract:
 *  - Solid theme-aware material, restrained domain accents, no hover movement
 *  - Equal card height; the full received payload lives in a keyboard-accessible scroll area
 *  - NOT_CONFIGURED → returns null (card hidden, layout reflows)
 *  - ERROR → red status accent (semantic) + message + CTA
 *  - Refresh keeps the content readable and the focused button mounted
 *  - Stagger entrance via animationDelay
 *  - Freshness and visible refresh control grouped on the title row, wrapping when needed
 */
export function BriefingCard<T extends SectionData>({
  titleKey,
  icon,
  tone,
  section,
  isRefreshing,
  onRefresh,
  renderContent,
  emptyStateKey,
  emptyStateValues,
  onErrorCta,
  staggerIndex,
  className,
  centerContent = false,
}: BriefingCardProps<T>) {
  const { t } = useTranslation();
  const titleId = useId();

  // F5: light up the dormant "just updated ✨" badge on a completed refresh
  // (isRefreshing true → false), for ~1.6 s. Hooks run before the early return
  // below to respect the Rules of Hooks.
  const [justRefreshed, setJustRefreshed] = useState(false);
  const recoveryTrigger = useRef<HTMLButtonElement | null>(null);
  const refreshControl = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (section.status === 'error' || !recoveryTrigger.current) return;
    if (!recoveryTrigger.current.isConnected && document.activeElement === document.body) {
      refreshControl.current?.focus();
    }
    recoveryTrigger.current = null;
  }, [section.status]);
  const prevRefreshingRef = useRef(isRefreshing);
  useEffect(() => {
    const wasRefreshing = prevRefreshingRef.current;
    prevRefreshingRef.current = isRefreshing;
    if (wasRefreshing && !isRefreshing) {
      setJustRefreshed(true);
      const id = setTimeout(() => setJustRefreshed(false), 1600);
      return () => clearTimeout(id);
    }
  }, [isRefreshing]);

  if (section.status === 'not_configured') return null;

  const isError = section.status === 'error';
  const ctaKey = isError ? resolveErrorCtaKey(section.error_code) : null;
  const errorAction =
    ctaKey === 'dashboard.briefing.actions.retry' ||
    ctaKey === 'dashboard.briefing.actions.retry_later'
      ? (trigger: HTMLButtonElement) => {
          if (document.activeElement === trigger) recoveryTrigger.current = trigger;
          onRefresh();
        }
      : onErrorCta;
  const titleLabel = t(titleKey);
  const iconColorClass = DOMAIN_ICON_TONE[tone];

  const staggerStyle =
    staggerIndex !== undefined
      ? { animationDelay: `${Math.min(staggerIndex, 8) * 60}ms` }
      : undefined;

  return (
    <div
      role="region"
      aria-label={titleLabel}
      aria-busy={isRefreshing}
      // A stable focus anchor for cards whose rows can DISAPPEAR under the
      // reader (cancelling a reminder). Radix returns focus to the trigger it
      // opened from; when that trigger was inside the removed row, focus falls
      // to <body> and the keyboard user restarts at the top of the page.
      // `-1` adds no tab stop — it only makes this named region a legal
      // destination for a deliberate `.focus()`, and it survives every state
      // the card can reach, the empty one included.
      tabIndex={-1}
      style={staggerStyle}
      className={cn(
        DASHBOARD_TILE_FRAME,
        'min-w-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-500',
        isError && 'border-destructive/30',
        className
      )}
    >
      {/* The user's theme stays in the material; domain colour is a small scan cue. */}
      {!isError && <TileAmbience />}
      <div
        className={cn(
          'pointer-events-none absolute inset-x-5 top-0 h-0.5 rounded-b-full bg-current opacity-50 sm:inset-x-6',
          isError ? 'text-destructive' : iconColorClass
        )}
        aria-hidden="true"
      />

      <div className="relative flex h-[420px] flex-col gap-4 p-5 sm:h-[470px] sm:p-6">
        {/* Header stays outside the scroll area; long labels wrap instead of clipping. */}
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border/60 pb-4">
          <div className="flex min-w-0 flex-1 basis-28 items-center gap-3">
            <div
              className={cn(TILE_ICON_BADGE, DOMAIN_CHIP_TONE[tone], 'border ring-0')}
              aria-hidden="true"
            >
              {icon}
            </div>
            <h3
              id={titleId}
              className="min-w-0 break-words text-base font-semibold leading-snug text-foreground tracking-tight"
            >
              {titleLabel}
            </h3>
          </div>
          <div className="ml-auto flex min-w-0 max-w-full items-center gap-2 [&_time]:text-xs">
            <CardFreshnessBadge section={section} isError={isError} justRefreshed={justRefreshed} />
            <button
              ref={refreshControl}
              type="button"
              onClick={() => {
                if (!isRefreshing) onRefresh();
              }}
              aria-disabled={isRefreshing}
              aria-label={t('dashboard.briefing.refresh_section', { section: titleLabel })}
              className={cn(
                'flex size-10 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-card transition-colors duration-150 active:scale-[0.98]',
                'text-muted-foreground hover:text-foreground hover:bg-muted/60',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card',
                isRefreshing && 'cursor-wait text-primary'
              )}
            >
              <RefreshCw
                aria-hidden="true"
                className={cn('h-4 w-4', isRefreshing && 'motion-safe:animate-spin')}
              />
            </button>
          </div>
        </div>

        {/* A named focus stop lets keyboard readers scroll even cards with no actions.
            Native scrolling preserves every item and its position during refresh. */}
        <div
          role="group"
          aria-labelledby={titleId}
          tabIndex={0}
          className="chat-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto rounded-md pb-1 pr-2 [scrollbar-gutter:stable] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
        >
          <CardBody
            section={section}
            renderContent={renderContent}
            centerContent={centerContent}
            emptyStateKey={emptyStateKey}
            emptyStateValues={emptyStateValues}
            ctaKey={ctaKey}
            onErrorCta={errorAction}
            busy={isRefreshing}
          />
        </div>
      </div>
    </div>
  );
}

/** Keep one content owner across OK and stale-error transitions. */
function CardBody<T extends SectionData>({
  section,
  renderContent,
  centerContent,
  emptyStateKey,
  emptyStateValues,
  ctaKey,
  onErrorCta,
  busy,
}: Pick<
  BriefingCardProps<T>,
  'section' | 'renderContent' | 'centerContent' | 'emptyStateKey' | 'emptyStateValues'
> & {
  ctaKey: string | null;
  onErrorCta?: (trigger: HTMLButtonElement) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const isError = section.status === 'error';
  return (
    <>
      {isError && (
        <CardErrorBody section={section} ctaKey={ctaKey} onErrorCta={onErrorCta} busy={busy} />
      )}
      {section.data && (section.status === 'ok' || isError) && (
        <div
          className={cn(
            'shrink-0',
            isError && 'mt-3 border-t border-border/60 pt-3',
            centerContent && 'flex-1 flex flex-col items-center justify-center text-center'
          )}
        >
          {renderContent(section.data)}
        </div>
      )}
      {section.status === 'empty' && (
        <div className="flex-1 flex items-center justify-center text-center text-sm text-muted-foreground italic py-2">
          {t(emptyStateKey, emptyStateValues)}
        </div>
      )}
    </>
  );
}
