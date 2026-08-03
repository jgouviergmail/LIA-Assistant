'use client';

import Image from 'next/image';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

/**
 * The hero's visible avatar affordance — two portraits, side by side.
 *
 * The whole hero image is a click target that flips the avatar (audit F045
 * made it a real named button). That affordance is invisible, so the change
 * could read as accidental. This picker does not replace it: it makes the
 * choice VISIBLE, and turns a blind flip into a selection — pressing the
 * variant already active is a no-op rather than a surprise.
 *
 * Three constraints shape the markup, each of them load-bearing:
 *
 * - **Sibling of the full-surface button, never a descendant.** A `<button>`
 *   may not contain interactive elements; the hero's own test pins that.
 * - **Never unmounted, only faded.** On desktop the picker is discreet and
 *   appears on hover — but `display:none` (or a conditional render) would drop
 *   it from the tab order, so the very focus meant to reveal it could never
 *   reach it. It is always mounted, revealed by `opacity` on hover AND on
 *   `focus-within`.
 * - **44 px on touch, discreet on desktop.** Below `sm` the buttons are full
 *   targets and always visible; above it they shrink and fade in.
 */
export interface AvatarVariantPickerProps {
  /** Which variant is currently applied. */
  isMale: boolean;
  /** False until the stored preference has been read (SSR + first paint). */
  mounted: boolean;
  /** Both portraits for the CURRENT theme. */
  variants: { female: string; male: string };
  /** Called with the variant the reader picked (not a toggle). */
  onSelect: (male: boolean) => void;
  className?: string;
}

export function AvatarVariantPicker({
  isMale,
  mounted,
  variants,
  onSelect,
  className,
}: AvatarVariantPickerProps) {
  const { t } = useTranslation();

  const options = [
    { male: false, src: variants.female, label: t('dashboard.avatar_picker.female') },
    { male: true, src: variants.male, label: t('dashboard.avatar_picker.male') },
  ];

  return (
    <div
      role="group"
      aria-label={t('dashboard.avatar_picker.group_label')}
      className={cn(
        // Above the full-surface toggle (z-[5]) so a press lands here.
        'absolute right-3 top-3 z-20 flex items-center gap-1',
        'rounded-full border border-border/40 bg-background/70 p-1 backdrop-blur-md',
        'shadow-[var(--lia-shadow-sm)]',
        // Always visible on touch; discreet on desktop, revealed by hover or
        // by the keyboard reaching inside (never removed from the tab order).
        'opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100',
        'motion-safe:transition-opacity motion-safe:duration-200',
        className
      )}
    >
      {options.map(option => {
        const active = mounted && isMale === option.male;
        return (
          <button
            key={option.src}
            type="button"
            onClick={() => onSelect(option.male)}
            // Before mount nothing is known, so nothing is claimed: an
            // `aria-pressed="false"` would state a preference nobody expressed.
            aria-pressed={mounted ? isMale === option.male : undefined}
            aria-label={option.label}
            title={option.label}
            className={cn(
              'relative overflow-hidden rounded-full',
              // 44 px touch target; smaller once a pointer is driving.
              'h-11 w-11 sm:h-9 sm:w-9',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              'motion-safe:transition-transform motion-safe:hover:scale-105',
              active ? 'ring-2 ring-primary' : 'ring-1 ring-border/50 opacity-70 hover:opacity-100'
            )}
          >
            {/* `alt=""`: the button already carries the accessible name, and a
                described image inside it would be announced twice. */}
            <Image src={option.src} alt="" fill sizes="44px" className="object-cover" />
          </button>
        );
      })}
    </div>
  );
}
