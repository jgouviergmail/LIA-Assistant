'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
 * - Navigation is shown when there is more than one view. Those controls are
 *   always visible: the previous arrows were `opacity-0
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
  /** Native ratio for a full-page capture, kept readable in a narrower frame. */
  aspectRatio?: number;
}

export type CarouselVariant = 'portrait' | 'wide' | 'application';

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
 * App captures include viewport and full-page views, fitted inside a portrait
 * frame with ambient bands. The presentation uses a wide frame.
 */
const FRAMES: Record<CarouselVariant, Frame> = {
  application: {
    aspect: 'aspect-[3/2]',
    max: 'max-w-6xl',
    sizes: '(max-width: 1152px) 100vw, 1152px',
    thumb: 'h-14 w-20 mobile:h-16 mobile:w-24',
    thumbSizes: '96px',
  },
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
  /** Keep preview geometry uniform; full-page originals remain available in the lightbox. */
  uniformFrame?: boolean;
}

/** Selection stays above the variable-height image in a mixed gallery. */
function CarouselThumbnailRail({
  slides,
  index,
  frame,
  variant,
  mixedFormats,
  railRef,
  thumbRefs,
  onSelect,
}: {
  slides: readonly CarouselSlide[];
  index: number;
  frame: Frame;
  variant: CarouselVariant;
  mixedFormats: boolean;
  railRef: React.RefObject<HTMLDivElement | null>;
  thumbRefs: React.RefObject<(HTMLButtonElement | null)[]>;
  onSelect: (index: number) => void;
}) {
  if (slides.length < 2) return null;
  return (
    <div
      ref={railRef}
      className={cn(
        'scrollbar-hide relative mx-auto flex snap-x gap-2.5 overflow-x-auto',
        'scroll-smooth py-1 motion-reduce:scroll-auto',
        mixedFormats ? 'mb-4' : 'mt-6',
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
          onClick={() => onSelect(i)}
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
            unoptimized={variant === 'application'}
            alt=""
            fill
            sizes={frame.thumbSizes}
            className="object-cover object-top"
          />
        </button>
      ))}
    </div>
  );
}

/** Both arrow positions stay fixed when full-page and viewport captures alternate. */
function CarouselNavigation({
  total,
  index,
  inline,
  onPrevious,
  onNext,
}: {
  total: number;
  index: number;
  inline: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const { t } = useTranslation();
  if (total < 2) return null;
  return (
    <div className={inline ? 'mb-3 flex items-center justify-center gap-4' : 'contents'}>
      <button
        type="button"
        onClick={onPrevious}
        aria-label={t('common.previous')}
        className={cn(ARROW_CLASS, inline ? 'static translate-y-0' : 'left-3')}
      >
        <ChevronLeft aria-hidden="true" className="h-5 w-5" />
      </button>
      {inline && (
        <p aria-hidden="true" className="text-xs font-semibold tabular-nums text-muted-foreground">
          {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
        </p>
      )}
      <button
        type="button"
        onClick={onNext}
        aria-label={t('common.next')}
        className={cn(ARROW_CLASS, inline ? 'static translate-y-0' : 'right-3')}
      >
        <ChevronRight aria-hidden="true" className="h-5 w-5" />
      </button>
    </div>
  );
}

/** Preview geometry can vary without changing the original opened by the lightbox. */
function CarouselImageStage({
  active,
  frame,
  variant,
  uniformFrame,
  index,
  total,
  mixedFormats,
  zoomable,
  onExpand,
  onTouchStart,
  onTouchMove,
  onTouchEnd,
}: {
  active: CarouselSlide;
  frame: Frame;
  variant: CarouselVariant;
  uniformFrame: boolean;
  index: number;
  total: number;
  mixedFormats: boolean;
  zoomable: boolean;
  onExpand: () => void;
  onTouchStart: React.TouchEventHandler<HTMLDivElement>;
  onTouchMove: React.TouchEventHandler<HTMLDivElement>;
  onTouchEnd: React.TouchEventHandler<HTMLDivElement>;
}) {
  const { t } = useTranslation();
  const portrait = active.aspectRatio !== undefined && active.aspectRatio < 1;

  return (
    <div
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      className={cn(
        'relative mx-auto w-full overflow-hidden rounded-2xl border border-border/70 bg-card/50',
        frame.aspect,
        portrait && !uniformFrame && 'max-w-[34rem]'
      )}
      style={!uniformFrame && active.aspectRatio ? { aspectRatio: active.aspectRatio } : undefined}
    >
      {/* Ambient light fills the frame. Application proofs use their
          revisioned originals, shared by the browser cache with the
          sharp image; decks retain the small optimized source. */}
      <Image
        key={`${active.src}#ambient`}
        src={active.src}
        unoptimized={variant === 'application'}
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
        unoptimized={variant === 'application'}
        alt={active.label}
        fill
        sizes={frame.sizes}
        className={portrait && uniformFrame ? 'object-cover object-top' : 'object-contain'}
      />

      {/* Position, as a chip on the stage. Decorative on purpose: the
          caption below is the live region that announces the change. */}
      {total > 1 && !mixedFormats && (
        <p
          aria-hidden="true"
          className="absolute bottom-3 left-3 z-10 rounded-full border border-border/60 bg-background/75 px-3 py-1 text-xs font-semibold tabular-nums text-muted-foreground backdrop-blur-md"
        >
          {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
        </p>
      )}

      {zoomable && (
        <button
          type="button"
          onClick={onExpand}
          aria-label={t('common.expand_image')}
          className="absolute right-3 top-3 z-10 grid h-10 w-10 place-items-center rounded-full border border-border/70 bg-background/75 text-foreground shadow-lg backdrop-blur-md transition hover:scale-105 hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary motion-reduce:transition-none"
        >
          <Expand aria-hidden="true" className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export function LandingCarousel({
  slides,
  variant,
  label,
  zoomable = false,
  uniformFrame = false,
}: LandingCarouselProps) {
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);

  const frame = FRAMES[variant];
  const total = slides.length;
  const active = slides[index];
  const mixedFormats =
    !uniformFrame && slides.some(slide => slide.aspectRatio !== undefined && slide.aspectRatio < 1);

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
    if (total < 2) return;
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

  const thumbnailRail = (
    <CarouselThumbnailRail
      slides={slides}
      index={index}
      frame={frame}
      variant={variant}
      mixedFormats={mixedFormats}
      railRef={railRef}
      thumbRefs={thumbRefs}
      onSelect={setIndex}
    />
  );

  return (
    <div className="w-full">
      {/* Stage. The focusable group is the keyboard and swipe surface (same
          WAI-ARIA carousel shape as InlinePlaceCarousel); the frame inside it
          is what the eye reads as the device. */}
      <div
        role="group"
        aria-label={label}
        tabIndex={total > 1 ? 0 : undefined}
        onKeyDown={handleKeyDown}
        className={cn(
          'relative mx-auto w-full rounded-2xl focus-visible:outline-none',
          'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-4',
          'focus-visible:ring-offset-background',
          frame.max
        )}
      >
        {mixedFormats && thumbnailRail}
        <CarouselNavigation
          total={total}
          index={index}
          inline={mixedFormats}
          onPrevious={() => goTo(index - 1)}
          onNext={() => goTo(index + 1)}
        />
        <CarouselImageStage
          active={active}
          frame={frame}
          variant={variant}
          uniformFrame={uniformFrame}
          index={index}
          total={total}
          mixedFormats={mixedFormats}
          zoomable={zoomable}
          onExpand={() => setExpanded(true)}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        />
      </div>

      {/* Caption — and the carousel's live region. Capped to a readable
          measure so the longest capture name still holds one line. */}
      <p
        aria-live="polite"
        className="mx-auto mt-5 max-w-3xl text-center text-sm font-medium text-muted-foreground"
      >
        {active.caption}
      </p>

      {!mixedFormats && thumbnailRail}

      {/* Landing scroll effects can make a fixed descendant relative to the
          section. Mount the viewer outside that hierarchy to fill the screen. */}
      {zoomable &&
        expanded &&
        createPortal(
          <ImageLightbox
            src={active.src}
            alt={active.label}
            isOpen={expanded}
            onClose={() => setExpanded(false)}
          />,
          document.body
        )}
    </div>
  );
}
