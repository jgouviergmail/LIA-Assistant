/**
 * RelationAvatar — deterministic initials avatar for the personal CRM.
 *
 * No photos exist in this domain (names come from loops/calls/stars), so the
 * avatar is the visual anchor: up to two initials on a tint derived stably
 * from the name — the same person keeps the same color across visits and
 * surfaces. Decorative (the name is always rendered next to it).
 */

import { cn } from '@/lib/utils';

/**
 * Charter-friendly tint pairs (bg wash + readable text, both themes).
 *
 * Light-mode text is `-800`, not `-700`: measured on the production bundle,
 * emerald/amber/teal at `-700` land on 4.31 / 4.18 / 4.33:1 over their own
 * wash — under the 4.5:1 AA floor. One uniform rule beats three per-hue
 * exceptions, and the avatar's initials are read by anyone with low vision
 * even though the element is decorative for screen readers.
 */
const TINTS = [
  'bg-primary/15 text-primary',
  'bg-sky-500/15 text-sky-800 dark:text-sky-300',
  'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300',
  'bg-amber-500/15 text-amber-800 dark:text-amber-300',
  'bg-violet-500/15 text-violet-800 dark:text-violet-300',
  'bg-rose-500/15 text-rose-800 dark:text-rose-300',
  'bg-teal-500/15 text-teal-800 dark:text-teal-300',
  'bg-indigo-500/15 text-indigo-800 dark:text-indigo-300',
] as const;

/** Stable non-negative hash of a display name (accent-insensitive enough). */
function nameHash(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

/** Up to two initials: first letters of the first two words. */
export function relationInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map(word => word[0]?.toUpperCase() ?? '');
  return letters.join('') || '?';
}

export function RelationAvatar({
  name,
  size = 'md',
  className,
}: {
  name: string;
  /** md = overview card, lg = detail header. */
  size?: 'md' | 'lg';
  className?: string;
}) {
  const tint = TINTS[nameHash(name) % TINTS.length];
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 select-none items-center justify-center rounded-full font-semibold',
        size === 'lg' ? 'h-14 w-14 text-lg' : 'h-10 w-10 text-sm',
        tint,
        className
      )}
    >
      {relationInitials(name)}
    </span>
  );
}
