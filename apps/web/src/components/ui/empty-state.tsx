import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';
import { Button } from './button';

/**
 * "There is nothing here" — said the same way everywhere, with a way out.
 *
 * Seven hand-written empty states had four vertical paddings, two icon sizes
 * and four different ways of fading the icon. That was the visible half of the
 * problem. The other half: six of the seven offered NO action, so a reader who
 * arrived at "no connection yet" had no route to creating one.
 *
 * Hence the two rules this component encodes:
 *
 *  - **`variant="page"` requires an action.** A whole screen that says "empty"
 *    and offers nothing is a dead end. The type makes it impossible.
 *  - **`reason` distinguishes no-data from no-match.** A user who has never
 *    created anything and a user whose filter matched nothing need different
 *    words and different exits; one branch for both serves neither.
 */
const emptyStateVariants = cva('flex flex-col items-center text-center', {
  variants: {
    variant: {
      /** Inside a card or a settings section: compact, no framing of its own. */
      section: 'gap-2 py-8',
      /** A whole screen or list area: framed, roomier, always actionable. */
      page: 'gap-3 rounded-lg border border-dashed p-12',
    },
  },
  defaultVariants: { variant: 'section' },
});

/** Icon size per variant — one decision, not one per call site. */
const ICON_SIZE: Record<'section' | 'page', string> = {
  section: 'h-8 w-8',
  page: 'h-12 w-12',
};

/** What the reader can do about the emptiness. */
type EmptyStateAction = { label: string; icon?: LucideIcon } & (
  | { onClick: () => void; href?: never }
  | { href: string; onClick?: never }
);

interface EmptyStateBaseProps extends VariantProps<typeof emptyStateVariants> {
  /** Decorative glyph; the words carry the meaning, so it is aria-hidden. */
  icon?: LucideIcon;
  /** Optional heading, for states that deserve a title as well as a sentence. */
  title?: string;
  /** The message itself — already resolved from the active locale. */
  description?: string;
  /** Why it is empty: nothing exists yet, or nothing matched the filter. */
  reason?: 'no-data' | 'no-match';
  className?: string;
}

/**
 * A section may be empty with nothing to offer; a page may not.
 *
 * Splitting the props this way is what makes "a page always has a way out" a
 * compile-time fact rather than a review comment.
 */
export type EmptyStateProps =
  | (EmptyStateBaseProps & { variant?: 'section'; action?: EmptyStateAction })
  | (EmptyStateBaseProps & { variant: 'page'; action: EmptyStateAction });

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  reason = 'no-data',
  variant = 'section',
  className,
}: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      data-reason={reason}
      className={cn(emptyStateVariants({ variant }), className)}
    >
      {Icon && (
        <Icon className={cn(ICON_SIZE[variant], 'text-muted-foreground')} aria-hidden="true" />
      )}
      {/* Deliberately NOT a heading. The right level depends on the host — a
          page whose h1 sits above it, a settings section already introduced by
          its own title — and a fixed `<h3>` reproduced the very h1 -> h3 jump
          this lot set out to remove on the Spaces screen. An empty state is a
          message about the current state, not a permanent section of the
          document outline. */}
      {title && <p className="text-base font-semibold text-foreground">{title}</p>}
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      {action && <EmptyStateActionButton action={action} />}
    </div>
  );
}

/** The action, as a link or a button, with its optional leading icon. */
function EmptyStateActionButton({ action }: { action: EmptyStateAction }) {
  const ActionIcon = action.icon;
  const content = (
    <>
      {ActionIcon && <ActionIcon className="h-4 w-4" aria-hidden="true" />}
      {action.label}
    </>
  );

  return action.href ? (
    <Button asChild className="mt-2">
      <Link href={action.href}>{content}</Link>
    </Button>
  ) : (
    <Button className="mt-2" onClick={action.onClick}>
      {content}
    </Button>
  );
}
