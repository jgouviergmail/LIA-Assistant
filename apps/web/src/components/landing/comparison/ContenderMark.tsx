import { cn } from '@/lib/utils';

import { CONTENDER_MARKS, type ContenderId } from './comparison-data';

const SIZES = {
  sm: { chip: 'size-6 rounded-md', image: 'size-4', pixels: 16 },
  md: { chip: 'size-9 rounded-lg', image: 'size-6', pixels: 24 },
  lg: { chip: 'size-11 rounded-xl', image: 'size-7', pixels: 28 },
} as const;

/**
 * A product's own mark on a white chip whatever the theme: a mark is drawn for
 * a light ground (Hermes Agent's black portrait vanishes on a dark card), so
 * the chip, not the theme, is what it stands on (as `MCPKnownServerIcon`).
 * Decorative: the product's name always sits beside it, or the surrounding
 * text names it. Server-safe: markup only.
 */
export function ContenderMark({
  id,
  size,
  className,
}: {
  id: ContenderId;
  size: keyof typeof SIZES;
  className?: string;
}) {
  const scale = SIZES[size];
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center border bg-white',
        scale.chip,
        className
      )}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- a static product mark of public/, no optimizer */}
      <img
        src={CONTENDER_MARKS[id]}
        alt=""
        width={scale.pixels}
        height={scale.pixels}
        loading="lazy"
        decoding="async"
        className={cn('object-contain', scale.image)}
      />
    </span>
  );
}
