'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Expand } from 'lucide-react';
import { ImageLightbox } from '@/components/ui/image-lightbox';
import { CAROUSEL_SWIPE_THRESHOLD_PX } from '@/lib/constants';
import { cn } from '@/lib/utils';

/**
 * The gallery carousel of the landing ("LIA, en vrai") — one implementation
 * shared by the app captures and the slide deck, which used to carry two
 * copies of the same ~90 lines.
 *
 * What the redesign changes, and why:
 * - The stage carries the ASSET's own ratio, so the picture fills its frame
 *   instead of floating inside a fixed-height box (a 0.88-ratio capture in a
 *   768x620 frame left 29 % of the stage empty; the home page left 47 %).
 * - What letterboxing remains is filled by an out-of-focus copy of the same
 *   picture. Served at 32 px (~1 KB) it also arrives first, so it doubles as
 *   the progressive placeholder while the full image decodes.
 * - Controls are ALWAYS visible: the previous arrows were `opacity-0
 *   group-hover:opacity-100`, i.e. permanently invisible on touch devices
 *   (audit F038, the half that survived the dot fix).
 * - Thumbnails are ratio-matched and scroll on one snapping rail instead of
 *   wrapping into rows of unreadable top-left crops.
 * - Arrow keys, Home/End and swipe drive the stage (WAI-ARIA carousel group).
 */

/** One view of a landing gallery. */
export interface CarouselSlide {
  /** Stable identity — React key and thumbnail id. */
  key: string;
  /** Public path of the full-size asset. */
  src: string;
  /** Translated name of the view: image alt text and thumbnail button name. */
  label: string;
  /**
   * Translated line shown under the stage. It is also the carousel's live
   * region, so this is what a screen reader hears when the view changes.
   */
  caption: string;
}

export type CarouselVariant = 'portrait' | 'wide';

interface Frame {
  /** Stage ratio — the asset's own. */
  aspect: string;
  /** Width cap: the picture is never stretched past its useful size. */
  max: string;
  /** `sizes` of the stage image at that cap. */
  sizes: string;
  /** Thumbnail box, ratio-matched to the stage so the crop stays faithful. */
  thumb: string;
  thumbSizes: string;
}

/**
 * App captures are 1106x1258 (~7/8 — the taller home page lands in the ambient
 * bands); deck slides are 4128x2304, which is exactly 43/24.
 */
const FRAMES: Record<CarouselVariant, Frame> = {
  portrait: {
    aspect: 'aspect-[7/8]',
    max: 'max-w-[34rem]',
    sizes: '(max-width: 600px) 100vw, 544px',
    thumb: 'h-20 w-[4.375rem] mobile:h-24 mobile:w-[5.25rem]',
    thumbSizes: '84px',
  },
  wide: {
    aspect: 'aspect-[43/24]',
    max: 'max-w-5xl',
    sizes: '(max-width: 1024px) 100vw, 1024px',
    thumb: 'h-14 w-[6.25rem] mobile:h-16 mobile:w-[7.1875rem]',
    thumbSizes: '115px',
  },
};

const ARROW_CLASS =
  'absolute top-1/2 z-10 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full ' +
  'border border-border/70 bg-background/75 text-foreground shadow-lg backdrop-blur-md ' +
  'transition hover:scale-105 hover:bg-background focus-visible:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-primary motion-reduce:transition-none';

export interface LandingCarouselProps {
  slides: readonly CarouselSlide[];
  variant: CarouselVariant;
  /** Accessible name of the carousel group (translated). */
  label: string;
  /**
   * Offer a full-screen view. Reserved for assets light enough to be fetched
   * at full size on demand — the app captures weigh ~100-700 KB, where a deck
   * slide weighs 2 MB and is already served at its readable width.
   */
  zoomable?: boolean;
}

export function LandingCarousel({
  slides,
  variant,
  label,
  zoomable = false,
}: LandingCarouselProps) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);

  const frame = FRAMES[variant];
  const total = slides.length;
  const active = slides[index];

  const goTo = useCallback((next: number) => setIndex((next + total) % total), [total]);

  // Keep the active thumbnail in view. `scrollIntoView()` would also scroll the
  // DOCUMENT — the rail sits mid-page — and drag the reader away from the
  // section; writing the rail's own scrollLeft cannot. Smoothness and its
  // reduced-motion opt-out are left to CSS on the rail itself.
  useEffect(() => {
    const rail = railRef.current;
    const thumb = thumbRefs.current[index];
    if (!rail || !thumb) return;
    rail.scrollLeft = thumb.offsetLeft - (rail.clientWidth - thumb.offsetWidth) / 2;
  }, [index]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowLeft':
        event.preventDefault();
        goTo(index - 1);
        break;
      case 'ArrowRight':
        event.preventDefault();
        goTo(index + 1);
        break;
      case 'Home':
        event.preventDefault();
        goTo(0);
        break;
      case 'End':
        event.preventDefault();
        goTo(total - 1);
        break;
    }
  };

  const handleTouchStart = (event: React.TouchEvent) => {
    touchStartX.current = event.touches[0].clientX;
    touchEndX.current = null;
  };

  const handleTouchMove = (event: React.TouchEvent) => {
    touchEndX.current = event.touches[0].clientX;
  };

  const handleTouchEnd = () => {
    const start = touchStartX.current;
    const end = touchEndX.current;
    touchStartX.current = null;
    touchEndX.current = null;
    if (start === null || end === null) return;
    const deltaX = start - end;
    if (Math.abs(deltaX) <= CAROUSEL_SWIPE_THRESHOLD_PX) return;
    goTo(deltaX > 0 ? index + 1 : index - 1);
  };

  // A gallery with nothing in it renders nothing. Not defensive padding: the
  // slides are built from translated inventories in six locales, and `goTo`
  // divides by `total` — one empty list would make the index NaN and take the
  // whole PUBLIC page down on `active.src`.
  if (total === 0) return null;

  return (
    <div className="w-full">
      {/* Stage. The focusable group is the keyboard and swipe surface (same
          WAI-ARIA carousel shape as InlinePlaceCarousel); the frame inside it
          is what the eye reads as the device. */}
      <div
        role="group"
        aria-label={label}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        className={cn(
          'relative mx-auto w-full rounded-2xl focus-visible:outline-none',
          'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-4',
          'focus-visible:ring-offset-background',
          frame.max
        )}
      >
        <div
          className={cn(
            'relative w-full overflow-hidden rounded-2xl border border-border/70 bg-card/50',
            frame.aspect
          )}
        >
          {/* Ambient: the picture's own light, out of focus, fills whatever the
              frame does not. 32 px source — it lands before the sharp one. */}
          <Image
            key={`${active.src}#ambient`}
            src={active.src}
            alt=""
            aria-hidden="true"
            fill
            sizes="32px"
            className="scale-110 object-cover opacity-45 blur-2xl saturate-150"
          />
          <div aria-hidden="true" className="absolute inset-0 bg-background/30" />
          <Image
            key={active.src}
            src={active.src}
            alt={active.label}
            fill
            sizes={frame.sizes}
            className="object-contain"
          />

          <button
            type="button"
            onClick={() => goTo(index - 1)}
            aria-label={t('common.previous')}
            className={cn(ARROW_CLASS, 'left-3')}
          >
            <ChevronLeft aria-hidden="true" className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => goTo(index + 1)}
            aria-label={t('common.next')}
            className={cn(ARROW_CLASS, 'right-3')}
          >
            <ChevronRight aria-hidden="true" className="h-5 w-5" />
          </button>

          {/* Position, as a chip on the stage. Decorative on purpose: the
              caption below is the live region that announces the change. */}
          <p
            aria-hidden="true"
            className="absolute bottom-3 left-3 z-10 rounded-full border border-border/60 bg-background/75 px-3 py-1 text-xs font-semibold tabular-nums text-muted-foreground backdrop-blur-md"
          >
            {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
          </p>

          {zoomable && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              aria-label={t('common.expand_image')}
              className="absolute right-3 top-3 z-10 grid h-10 w-10 place-items-center rounded-full border border-border/70 bg-background/75 text-foreground shadow-lg backdrop-blur-md transition hover:scale-105 hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary motion-reduce:transition-none"
            >
              <Expand aria-hidden="true" className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Caption — and the carousel's live region. Capped to a readable
          measure so the longest capture name still holds one line. */}
      <p
        aria-live="polite"
        className="mx-auto mt-5 max-w-3xl text-center text-sm font-medium text-muted-foreground"
      >
        {active.caption}
      </p>

      {/* Thumbnail rail: one snapping row that scrolls, instead of rows of
          wrapped crops. Capped to the stage width so the two align; `relative`
          makes it the offsetParent the centring effect measures against; the
          scrollbar is hidden (`scrollbar-hide`, the shared utility) because
          the cropped thumbnail at the edge already says there is more. */}
      <div
        ref={railRef}
        className={cn(
          'scrollbar-hide relative mx-auto mt-6 flex snap-x gap-2.5 overflow-x-auto',
          'scroll-smooth py-1 motion-reduce:scroll-auto',
          frame.max
        )}
      >
        {slides.map((slide, i) => (
          <button
            key={slide.key}
            ref={el => {
              thumbRefs.current[i] = el;
            }}
            type="button"
            onClick={() => setIndex(i)}
            aria-label={slide.label}
            aria-current={i === index ? 'true' : undefined}
            className={cn(
              'relative shrink-0 snap-center overflow-hidden rounded-lg border-2 transition',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
              'motion-reduce:transition-none',
              frame.thumb,
              i === index
                ? 'border-primary opacity-100 shadow-md'
                : 'border-border/40 opacity-55 hover:border-border hover:opacity-90'
            )}
          >
            <Image
              src={slide.src}
              alt=""
              fill
              sizes={frame.thumbSizes}
              className="object-cover object-top"
            />
          </button>
        ))}
      </div>

      {zoomable && expanded && (
        <ImageLightbox
          src={active.src}
          alt={active.label}
          isOpen={expanded}
          onClose={() => setExpanded(false)}
        />
      )}
    </div>
  );
}
