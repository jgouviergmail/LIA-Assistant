import Link from 'next/link';

import { MapIcon } from './map-icons';
import { brickHref } from '@/lib/maps/links';
import type { BrickRef, MapPage } from '@/lib/maps/types';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';

/**
 * A link between the maps. A bare hash stays a plain anchor — the page listens
 * to `hashchange`, so following it selects without navigating — while a path
 * goes through the router like every other page of the site.
 */
export function MapLink({
  href,
  className,
  children,
  ...rest
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
  'data-tone'?: string;
}) {
  if (href.startsWith('#')) {
    return (
      <a href={href} className={className} {...rest}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={className} {...rest}>
      {children}
    </Link>
  );
}

/** A brick as a chip: its icon, its name, its tone — and its address. */
export function BrickChip({
  brick,
  from,
  lng,
}: {
  brick: BrickRef;
  /** The page the chip is drawn on: a brick of that same map is a local hash. */
  from: MapPage;
  lng: Language;
}) {
  return (
    <MapLink
      href={brickHref(brick.id, brick.kind, from, lng)}
      className={cn('lm-chip', brick.kind === 'technical' && 'is-tech')}
      data-tone={brick.tone}
    >
      <MapIcon name={brick.icon} size={14} />
      {brick.name}
    </MapLink>
  );
}
