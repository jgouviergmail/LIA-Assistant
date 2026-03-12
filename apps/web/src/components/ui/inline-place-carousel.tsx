'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { isImageLoaded, markImageLoaded } from '@/lib/image-cache';
import { CAROUSEL_SWIPE_THRESHOLD_PX } from '@/lib/constants';

interface InlinePlaceCarouselProps {
  /** Array of image URLs */
  images: string[];
  /** Alt text for images */
  alt?: string;
  /** Initial image index (default: 0) */
  initialIndex?: number;
  /** Optional class name for the container */
  className?: string;
}

/**
 * InlinePlaceCarousel - Inline carousel for place photos
 *
 * Displays directly within the Place card with the same dimensions
 * as the original photo.
 *
 * Features:
 * - Navigation via left/right arrows
 * - Swipe left/right on mobile
 * - Position indicators (dots)
 * - Keyboard: ArrowLeft, ArrowRight
 * - Fade transition between images
 * - Loading state with global cache
 */
export const InlinePlaceCarousel: React.FC<InlinePlaceCarouselProps> = ({
  images,
  alt,
  initialIndex = 0,
  className,
}) => {
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  // Touch/swipe state
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);

  // Loading state per image
  const [loadedImages, setLoadedImages] = useState<Set<string>>(() => {
    // Initialize with already cached images
    return new Set(images.filter(src => isImageLoaded(src)));
  });

  const currentImage = images[currentIndex];
  const isCurrentLoaded = loadedImages.has(currentImage);

  // Handle image load
  const handleImageLoad = useCallback((src: string) => {
    markImageLoaded(src);
    setLoadedImages(prev => new Set(prev).add(src));
  }, []);

  // Navigation logic (DRY - used by click handlers, keyboard, and swipe)
  const navigatePrevious = useCallback(() => {
    setCurrentIndex(prev => (prev > 0 ? prev - 1 : images.length - 1));
  }, [images.length]);

  const navigateNext = useCallback(() => {
    setCurrentIndex(prev => (prev < images.length - 1 ? prev + 1 : 0));
  }, [images.length]);

  // Click handlers (with stopPropagation)
  const handlePreviousClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      navigatePrevious();
    },
    [navigatePrevious]
  );

  const handleNextClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      navigateNext();
    },
    [navigateNext]
  );

  // Touch handlers for swipe
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchEndX.current = null;
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    touchEndX.current = e.touches[0].clientX;
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (touchStartX.current === null || touchEndX.current === null) return;

    const deltaX = touchStartX.current - touchEndX.current;

    if (Math.abs(deltaX) > CAROUSEL_SWIPE_THRESHOLD_PX) {
      if (deltaX > 0) {
        // Swipe left → next image
        navigateNext();
      } else {
        // Swipe right → previous image
        navigatePrevious();
      }
    }

    // Reset
    touchStartX.current = null;
    touchEndX.current = null;
  }, [navigateNext, navigatePrevious]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        navigatePrevious();
      } else if (e.key === 'ArrowRight') {
        navigateNext();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [navigatePrevious, navigateNext]);

  if (images.length === 0) return null;

  const showNavigation = images.length > 1;

  return (
    <div
      className={cn('lia-place-carousel', className)}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Current image */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={currentImage}
        alt={alt || t('gallery.place_photo')}
        className="lia-place-carousel__image"
        style={{ opacity: isCurrentLoaded ? 1 : 0 }}
        onLoad={() => handleImageLoad(currentImage)}
        draggable={false}
      />

      {/* Navigation arrows */}
      {showNavigation && (
        <>
          <button
            onClick={handlePreviousClick}
            className="lia-place-carousel__nav lia-place-carousel__nav--prev"
            aria-label={t('common.previous')}
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <button
            onClick={handleNextClick}
            className="lia-place-carousel__nav lia-place-carousel__nav--next"
            aria-label={t('common.next')}
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </>
      )}

      {/* Dots indicator */}
      {showNavigation && (
        <div className="lia-place-carousel__dots">
          {images.map((_, idx) => (
            <button
              key={idx}
              onClick={e => {
                e.stopPropagation();
                setCurrentIndex(idx);
              }}
              className={cn(
                'lia-place-carousel__dot',
                idx === currentIndex && 'lia-place-carousel__dot--active'
              )}
              aria-label={t('gallery.photo_counter', { current: idx + 1, total: images.length })}
            />
          ))}
        </div>
      )}

      {/* Counter badge */}
      {showNavigation && (
        <div className="lia-place-carousel__counter">
          {currentIndex + 1} / {images.length}
        </div>
      )}
    </div>
  );
};
