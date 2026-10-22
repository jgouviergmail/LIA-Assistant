'use client';

import { useLayoutEffect, useRef, type ComponentProps, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { mountPlaceMap } from '@/lib/google-place-map';
import { PlaceMapDetails, PlaceMapTitle } from './place-map-details';

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
  const phone = useMediaQuery('(max-width: 639px)');
  const title = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    const map = controller.current;
    if (phone) map?.clearDetails();
    else map?.showDetails(popup.place.ref, popup.element, popup.header, onDismiss);
    return () => map?.clearDetails();
  }, [phone, popup, controller, onDismiss]);

  const details = (
    <PlaceMapDetails place={popup.place} route={route} onRetry={onRetry} showTitle={false} />
  );
  if (!phone)
    return (
      <>
        {createPortal(<PlaceMapTitle place={popup.place} />, popup.header)}
        {createPortal(details, popup.element)}
      </>
    );

  return (
    <Dialog open onOpenChange={open => !open && onDismiss()}>
      <DialogContent
        className="lia-place-details-dialog top-auto translate-y-0"
        aria-describedby={undefined}
        onOpenAutoFocus={event => {
          event.preventDefault();
          title.current?.focus();
        }}
        onCloseAutoFocus={event => {
          if (popup.invoker?.isConnected) {
            event.preventDefault();
            popup.invoker.focus({ preventScroll: true });
          }
        }}
      >
        <div className="lia-place-details-dialog__body">
          <div className="lia-place-details-dialog__heading">
            <DialogTitle asChild>
              <PlaceMapTitle ref={title} place={popup.place} tabIndex={-1} />
            </DialogTitle>
          </div>
          <div className="lia-place-details-dialog__facts">{details}</div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
