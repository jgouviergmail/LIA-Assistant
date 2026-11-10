'use client';

import { useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { MapPin } from '@/lib/icons';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { mountPlaceMap } from '@/lib/google-place-map';

export interface MapPopupTarget {
  ref: string;
  label: string;
  element: HTMLDivElement;
  header: HTMLDivElement;
  invoker: HTMLElement | null;
}

/** Shared native anchor / phone dialog mechanics, independent of route capability. */
export function MapDetailsPopup({
  popup,
  controller,
  children,
  onDismiss,
}: {
  popup: MapPopupTarget;
  controller: RefObject<ReturnType<typeof mountPlaceMap> | null>;
  children: ReactNode;
  onDismiss(): void;
}) {
  const phone = useMediaQuery('(max-width: 639px)');
  const title = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    const map = controller.current;
    if (phone) map?.clearDetails();
    else map?.showDetails(popup.ref, popup.element, popup.header, onDismiss);
    return () => map?.clearDetails();
  }, [phone, popup, controller, onDismiss]);
  const heading = (
    <h3 ref={title} tabIndex={phone ? -1 : undefined} className="lia-place-details__title">
      <MapPin size={19} className="text-primary" aria-hidden="true" />
      <span>{popup.label}</span>
    </h3>
  );
  if (!phone)
    return (
      <>
        {createPortal(heading, popup.header)}
        {createPortal(children, popup.element)}
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
            <DialogTitle asChild>{heading}</DialogTitle>
          </div>
          <div className="lia-place-details-dialog__facts">{children}</div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
