'use client';

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { InlinePlaceCarousel } from '@/components/ui/inline-place-carousel';
import { parsePlacePhotos } from '@/lib/place-photos';

export function PlacePhotoWrapper({
  children,
  ...props
}: {
  children?: ReactNode;
  [key: string]: unknown;
}) {
  const { t } = useTranslation();
  const enrichedValue = props['data-place-photos'];
  const legacyValue = props['data-photo-urls'];
  const enriched = typeof enrichedValue === 'string' ? enrichedValue : undefined;
  const legacy = typeof legacyValue === 'string' ? legacyValue : undefined;
  const photos = parsePlacePhotos(enriched ?? legacy);
  const suppliedName = props['data-place-name'];
  const alt =
    typeof suppliedName === 'string' && suppliedName.trim()
      ? suppliedName
      : t('gallery.place_photo');
  const suppliedClass = props.className;
  const className = typeof suppliedClass === 'string' ? suppliedClass : 'lia-place__photo';
  // Historical single-photo markup retains its original alt text and child behavior.
  if (!photos.length || (!enriched && photos.length === 1))
    return <div className={className}>{children}</div>;
  return (
    <div className={className}>
      <InlinePlaceCarousel
        images={photos.map(photo => photo.url)}
        photoAuthors={photos.map(photo => photo.authors)}
        sourceUrls={photos.map(photo => photo.sourceUrl)}
        alt={alt}
      />
    </div>
  );
}
