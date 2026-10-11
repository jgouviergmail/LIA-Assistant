'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { spiritAsset, type SpiritExpression, type SpiritVariant } from './catalogue';
import { useSpiritPlayback } from './playback';

export interface SpiritAvatarProps {
  variant: SpiritVariant;
  expression: SpiritExpression;
  animate?: boolean;
  size?: number;
  className?: string;
}

/** Native transparent WebP playback. No animated image stays mounted while suspended. */
export function SpiritAvatar({
  variant,
  expression,
  animate = false,
  size = 40,
  className,
}: SpiritAvatarProps) {
  const { rootRef, playing } = useSpiritPlayback(animate);
  const [failedSources, setFailedSources] = useState<ReadonlySet<string>>(() => new Set());
  const candidates = [
    ...(playing ? [spiritAsset(variant, expression, true)] : []),
    spiritAsset(variant, expression, false),
    spiritAsset(variant, 'neutral', false),
  ];
  const source = candidates.find(candidate => !failedSources.has(candidate));
  return (
    <span
      ref={rootRef}
      data-spirit-avatar={variant}
      data-expression={expression}
      aria-hidden="true"
      className={cn('inline-flex shrink-0 items-center justify-center', className)}
      style={{ width: size, height: size }}
    >
      {source ? (
        // eslint-disable-next-line @next/next/no-img-element -- local animated WebP must retain its native frames
        <img
          key={source}
          src={source}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          decoding="async"
          draggable={false}
          className="pointer-events-none h-full w-full select-none object-contain"
          onError={() => setFailedSources(previous => new Set(previous).add(source))}
        />
      ) : (
        <span className="text-xs font-bold">LIA</span>
      )}
    </span>
  );
}
