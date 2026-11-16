'use client';

import { forwardRef, useId, useSyncExternalStore } from 'react';
import type { LucideIcon, LucideProps } from 'lucide-react';
import { useIconStyle } from '@/lib/icon-style-context';
import { scopeIconArtwork, type IconArtwork, type IconStyle } from '@/lib/icon-style';

const forcedColorsQuery = '(forced-colors: active)';

/**
 * ONE media query list and ONE browser listener for every icon on the page.
 * Each `matchMedia` call builds a new list, and a page draws hundreds of icons
 * (≈590 on the home page, 2026-11-15): asked per icon and per render, that was
 * four lists and one listener per icon. The list is rebuilt only when
 * `window.matchMedia` itself is replaced, and the listener follows it.
 */
let forcedColors: { source: Window['matchMedia']; list: MediaQueryList } | null = null;
const forcedColorsListeners = new Set<() => void>();

function notifyForcedColors(): void {
  for (const listener of forcedColorsListeners) listener();
}

function forcedColorsList(): MediaQueryList {
  if (forcedColors?.source !== window.matchMedia) {
    const listening = forcedColorsListeners.size > 0;
    if (listening) forcedColors?.list.removeEventListener('change', notifyForcedColors);
    forcedColors = { source: window.matchMedia, list: window.matchMedia(forcedColorsQuery) };
    if (listening) forcedColors.list.addEventListener('change', notifyForcedColors);
  }
  return forcedColors.list;
}

function subscribeForcedColors(onChange: () => void): () => void {
  const list = forcedColorsList();
  if (forcedColorsListeners.size === 0) list.addEventListener('change', notifyForcedColors);
  forcedColorsListeners.add(onChange);
  return () => {
    forcedColorsListeners.delete(onChange);
    if (forcedColorsListeners.size === 0) {
      forcedColors?.list.removeEventListener('change', notifyForcedColors);
    }
  };
}
const readForcedColors = () => forcedColorsList().matches;
const serverForcedColors = () => false;

/** A compatible SVG boundary: callers keep their size, ref, labels and handlers. */
export function createAppIcon(
  name: string,
  LucideComponent: LucideIcon,
  variants: Readonly<Record<Exclude<IconStyle, 'lucide'>, IconArtwork>>,
  classNames: string
): LucideIcon {
  const Icon = forwardRef<SVGSVGElement, LucideProps>(function AppIcon(
    { children, fill = 'none', ...props },
    ref
  ) {
    const style = useIconStyle();
    const id = useId().replace(/[^a-zA-Z0-9_-]/g, '');
    const forcedColors = useSyncExternalStore(
      subscribeForcedColors,
      readForcedColors,
      serverForcedColors
    );
    if (style === 'lucide' || forcedColors) {
      return (
        <LucideComponent
          {...props}
          fill={fill}
          ref={ref}
          data-icon-style="lucide"
          data-icon-name={name}
        >
          {children}
        </LucideComponent>
      );
    }

    const artwork = variants[style];
    const { size = 24, className = '', absoluteStrokeWidth: _absolute, ...svgProps } = props;
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={size}
        height={size}
        viewBox={artwork.viewBox}
        fill={fill}
        aria-hidden={svgProps['aria-label'] || svgProps['aria-labelledby'] ? undefined : true}
        {...svgProps}
        ref={ref}
        className={`${classNames} app-icon app-icon-${style} ${className}`}
        data-icon-style={style}
        data-icon-name={name}
      >
        {/* Only checked-in, reviewed artwork reaches this boundary. Message HTML
            is sanitized separately and can select a known icon name only. */}
        <g
          className="app-icon-artwork"
          dangerouslySetInnerHTML={{ __html: scopeIconArtwork(artwork.body, `icon-${id}`) }}
        />
        {children}
      </svg>
    );
  });
  Icon.displayName = `AppIcon(${name})`;
  return Icon;
}
