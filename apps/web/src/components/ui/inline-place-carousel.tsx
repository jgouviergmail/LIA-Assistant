'use client';

import { useState, type FC } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Maximize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn, proxyGoogleImageUrl } from '@/lib/utils';
import { apiImageProps } from '@/lib/utils/api-resource-url';
import type { PhotoAuthor } from '@/lib/place-photos';
import { ImageLightbox } from './image-lightbox';
import { PhotoAttribution } from './photo-attribution';
import { usePlaceGallery } from './use-place-gallery';

interface InlinePlaceCarouselProps {
  images: string[];
  alt?: string;
  initialIndex?: number;
  className?: string;
  photoAuthors?: readonly (readonly PhotoAuthor[])[];
  sourceUrls?: readonly (string | undefined)[];
}

/** Manual, instance-scoped gallery. Only the current image is mounted/fetched. */
export const InlinePlaceCarousel: FC<InlinePlaceCarouselProps> = ({
  images,
  alt,
  initialIndex = 0,
  className,
  photoAuthors,
  sourceUrls,
}) => {
  const { t } = useTranslation();
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const imageProps = images.map(url => apiImageProps(proxyGoogleImageUrl(url) || url));
  const gallery = usePlaceGallery(
    imageProps.map(image => image.src),
    initialIndex
  );
  if (!images.length) return null;
  const navigation = images.length > 1;
  const imageAlt = alt || t('gallery.place_photo');
  const authors = photoAuthors?.[gallery.currentIndex];
  return (
    <>
      <div
        className={cn('lia-place-carousel', className)}
        role="group"
        aria-roledescription="carousel"
        aria-label={imageAlt}
        tabIndex={navigation ? 0 : undefined}
        onKeyDown={gallery.onKeyDown}
        onTouchStart={gallery.onTouchStart}
        onTouchMove={gallery.onTouchMove}
        onTouchEnd={gallery.onTouchEnd}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          {...imageProps[gallery.currentIndex]}
          alt={imageAlt}
          className="lia-place-carousel__image"
          loading="lazy"
          referrerPolicy="no-referrer"
          style={{ opacity: gallery.isLoaded ? 1 : 0 }}
          onLoad={() => gallery.onLoad(gallery.currentImage)}
          onError={() => gallery.onError(gallery.currentImage)}
          draggable={false}
        />
        <PhotoState failed={gallery.isFailed} loaded={gallery.isLoaded} />
        {navigation && (
          <>
            <button
              type="button"
              onClick={gallery.previous}
              className="lia-place-carousel__nav lia-place-carousel__nav--prev"
              aria-label={t('common.previous')}
            >
              <ChevronLeft className="w-5 h-5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={gallery.next}
              className="lia-place-carousel__nav lia-place-carousel__nav--next"
              aria-label={t('common.next')}
            >
              <ChevronRight className="w-5 h-5" aria-hidden="true" />
            </button>
            <div className="lia-place-carousel__dots">
              {images.map((_, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => gallery.select(index)}
                  className={cn(
                    'lia-place-carousel__dot',
                    index === gallery.currentIndex && 'lia-place-carousel__dot--active'
                  )}
                  aria-current={index === gallery.currentIndex ? 'true' : undefined}
                  aria-label={t('gallery.photo_counter', {
                    current: index + 1,
                    total: images.length,
                  })}
                />
              ))}
            </div>
            <div className="lia-place-carousel__counter">
              {gallery.currentIndex + 1} / {images.length}
            </div>
            <span role="status" aria-live="polite" className="sr-only">
              {t('gallery.photo_counter', {
                current: gallery.currentIndex + 1,
                total: images.length,
              })}
            </span>
          </>
        )}
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          disabled={gallery.isFailed}
          aria-label={t('gallery.expand_photo')}
          className="lia-place-carousel__nav lia-place-carousel__nav--expand"
        >
          <Maximize2 className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
      <PhotoAttribution authors={authors} sourceUrl={sourceUrls?.[gallery.currentIndex]} />
      {/* The dialog is outside the keyboard group: arrows must not navigate twice. */}
      <GalleryLightbox
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
        gallery={gallery}
        imageAlt={imageAlt}
        navigation={navigation}
        count={images.length}
        crossOrigin={imageProps[gallery.currentIndex]?.crossOrigin}
        authors={authors}
        sourceUrl={sourceUrls?.[gallery.currentIndex]}
      />
    </>
  );
};

function PhotoState({ failed, loaded }: { failed: boolean; loaded: boolean }) {
  const { t } = useTranslation();
  if (failed)
    return (
      <p className="lia-place-carousel__state" role="status">
        {t('gallery.photo_unavailable')}
      </p>
    );
  if (loaded) return null;
  return (
    <p className="lia-place-carousel__state lia-place-carousel__state--loading">
      {t('gallery.photo_loading')}
    </p>
  );
}

function GalleryLightbox({
  open,
  onClose,
  gallery,
  imageAlt,
  navigation,
  crossOrigin,
  authors,
  sourceUrl,
  count,
}: {
  open: boolean;
  onClose: () => void;
  gallery: ReturnType<typeof usePlaceGallery>;
  imageAlt: string;
  navigation: boolean;
  count: number;
  crossOrigin?: 'use-credentials';
  authors?: readonly PhotoAuthor[];
  sourceUrl?: string;
}) {
  if (!open || typeof document === 'undefined') return null;
  return createPortal(
    <ImageLightbox
      src={gallery.currentImage}
      crossOrigin={crossOrigin}
      alt={imageAlt}
      isOpen
      onClose={onClose}
      onPrev={navigation ? gallery.previous : undefined}
      onNext={navigation ? gallery.next : undefined}
      position={navigation ? { current: gallery.currentIndex + 1, total: count } : undefined}
      caption={<PhotoAttribution authors={authors} sourceUrl={sourceUrl} />}
    />,
    document.body
  );
}
