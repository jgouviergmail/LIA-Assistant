'use client';

import { useMemo, type ComponentProps, type RefObject } from 'react';
import type { mountPlaceMap } from '@/lib/google-place-map';
import { PlaceMapDetails } from './place-map-details';
import { MapDetailsPopup } from './map-details-popup';

type DetailsProps = ComponentProps<typeof PlaceMapDetails>;
export interface PlacePopup {
  place: DetailsProps['place'];
  element: HTMLDivElement;
  header: HTMLDivElement;
  invoker: HTMLElement | null;
}

/** A phone needs the viewport's width; desktop keeps the native map anchor. */
export function PlaceMapPopup({
  popup,
  controller,
  route,
  onRetry,
  onDismiss,
}: {
  popup: PlacePopup;
  controller: RefObject<ReturnType<typeof mountPlaceMap> | null>;
  route: DetailsProps['route'];
  onRetry(): void;
  onDismiss(): void;
}) {
  const target = useMemo(
    () => ({ ...popup, ref: popup.place.ref, label: popup.place.label }),
    [popup]
  );
  return (
    <MapDetailsPopup popup={target} controller={controller} onDismiss={onDismiss}>
      <PlaceMapDetails place={popup.place} route={route} onRetry={onRetry} showTitle={false} />
    </MapDetailsPopup>
  );
}
