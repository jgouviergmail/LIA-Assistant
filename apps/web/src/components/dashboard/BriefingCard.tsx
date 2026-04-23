'use client';

import { ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { resolveErrorCtaKey } from '@/lib/briefing-utils';
import type { CardSection, SectionData } from '@/types/briefing';
import { UpdatedAtBadge } from './UpdatedAtBadge';

/**
 * Per-card icon tone — applied ONLY to the SVG icon color (not the card chrome).
 * Card backgrounds, borders, orbs, badges all use the user's theme primary color.
 */
export type CardTone = 'sky' | 'violet' | 'amber' | 'rose' | 'emerald' | 'red';

const ICON_TONE: Record<CardTone, string> = {
  sky: 'text-sky-600 dark:text-sky-400',
  violet: 'text-violet-600 dark:text-violet-400',
  amber: 'text-amber-600 dark:text-amber-400',
  rose: 'text-rose-600 dark:text-rose-400',
  emerald: 'text-emerald-600 dark:text-emerald-400',
  red: 'text-red-600 dark:text-red-400',
};

export interface BriefingCardProps<T extends SectionData> {
  titleKey: string;
  icon: ReactNode;
  /** Tone applied ONLY to the icon SVG color — card chrome stays primary-themed */
  tone: CardTone;
  section: CardSection<T>;
  isRefreshing: boolean;
  onRefresh: () => void;
  renderContent: (data: T) => ReactNode;
  emptyStateKey: string;
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
 *  - Card chrome (background, border, orb, badge) uses the user's theme PRIMARY color
 *  - Icon SVG itself keeps its per-domain `tone` color
 *  - Subtle primary gradient overlay (top-right → transparent)
 *  - Hover: lift + shadow-2xl + icon scale
 *  - NOT_CONFIGURED → returns null (card hidden, layout reflows)
 *  - ERROR → red status accent (semantic) + message + CTA
 *  - Refresh overlay with backdrop-blur + spinner
 *  - Stagger entrance via animationDelay
 *  - Timestamp bottom-right, very discreet
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
  onErrorCta,
  staggerIndex,
  className,
  centerContent = false,
}: BriefingCardProps<T>) {
  const { t } = useTranslation();
  if (section.status === 'not_configured') return null;

  const isError = section.status === 'error';
  const ctaKey = isError ? resolveErrorCtaKey(section.error_code) : null;
  const titleLabel = t(titleKey);
  const iconColorClass = ICON_TONE[tone];

  const staggerStyle =
    staggerIndex !== undefined
      ? { animationDelay: `${Math.min(staggerIndex, 8) * 60}ms` }
      : undefined;

  return (
    <div
      role="region"
      aria-label={titleLabel}
      aria-busy={isRefreshing}
      style={staggerStyle}
      className={cn(
        'group relative overflow-hidden rounded-2xl border bg-card',
        'shadow-[var(--lia-shadow-md)]',
        'transition-all duration-300 ease-out',
        'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-500',
        'motion-safe:hover:-translate-y-1 motion-safe:hover:shadow-2xl',
        isError
          ? 'border-destructive/30'
          : 'border-border/50 hover:border-primary/30',
        isRefreshing && 'pointer-events-none',
        className,
      )}
    >
      {/* Primary-themed gradient overlay (top-right → transparent) */}
      {!isError && (
        <div
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/8 to-transparent opacity-60 dark:opacity-50"
          aria-hidden="true"
        />
      )}

      {/* Primary-themed ambient blur orb (top-right) */}
      {!isError && (
        <div
          className="pointer-events-none absolute -top-10 -right-10 h-32 w-32 rounded-full bg-primary opacity-15 blur-3xl transition-opacity duration-500 motion-safe:group-hover:opacity-25"
          aria-hidden="true"
        />
      )}

      <div className="relative flex flex-col h-[280px] p-5 sm:p-6 gap-4">
        {/* Header: icon badge (primary chrome) + title + timestamp + refresh — FIXED */}
        <div className="flex items-start justify-between gap-3 shrink-0">
          <div className="flex items-baseline gap-3 min-w-0">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20',
                'transition-transform duration-300',
                'motion-safe:group-hover:scale-110 motion-safe:group-hover:rotate-3 self-center',
                iconColorClass,
              )}
              aria-hidden="true"
            >
              {icon}
            </div>
            <h3 className="text-sm font-semibold text-foreground tracking-tight truncate">
              {titleLabel}
            </h3>
            {!isError && (
              <UpdatedAtBadge
                generatedAt={section.generated_at}
                className="shrink-0"
              />
            )}
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label={t('dashboard.briefing.refresh_section', { section: titleLabel })}
            className={cn(
              'shrink-0 rounded-lg p-2 transition-all duration-200',
              'text-muted-foreground/50 hover:text-foreground hover:bg-muted/60',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              // Mobile: always visible (no hover on touch devices).
              // Desktop (sm+): hidden until card hover, with a subtle rotate.
              'opacity-100 sm:opacity-0 sm:group-hover:opacity-100 motion-safe:sm:group-hover:rotate-12',
              isRefreshing && 'opacity-100',
            )}
          >
            <RefreshCw className={cn('h-3.5 w-3.5', isRefreshing && 'motion-safe:animate-spin')} />
          </button>
        </div>

        {/* Body — SCROLLABLE (scrollbar hidden for cleaner look) */}
        <div className="flex-1 min-h-0 overflow-y-auto scrollbar-hide flex flex-col">
          {section.status === 'ok' && section.data && (
            <div
              className={cn(
                'motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300',
                centerContent && 'flex-1 flex flex-col items-center justify-center text-center',
              )}
            >
              {renderContent(section.data)}
            </div>
          )}

          {section.status === 'empty' && (
            <div className="flex-1 flex items-center justify-center text-center text-sm text-muted-foreground/80 italic py-2">
              {t(emptyStateKey)}
            </div>
          )}

          {isError && (
            <div className="flex-1 flex flex-col gap-2 justify-center">
              <p className="text-sm text-foreground/80 leading-snug">
                {section.error_message || t('dashboard.briefing.errors.generic')}
              </p>
              {ctaKey && onErrorCta && (
                <button
                  type="button"
                  onClick={onErrorCta}
                  className="self-start text-xs font-medium text-primary hover:text-primary/80 underline underline-offset-2 transition-colors"
                >
                  {t(ctaKey)}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Refresh overlay */}
        {isRefreshing && (
          <div
            className="absolute inset-0 rounded-2xl bg-card/70 backdrop-blur-sm flex items-center justify-center motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200"
            aria-hidden="true"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 ring-2 ring-primary/20">
              <RefreshCw className={cn('h-5 w-5 motion-safe:animate-spin', iconColorClass)} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
