'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { downloadImage } from '@/lib/utils/download-image';
import { Download, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ImageLightboxProps {
  src: string;
  alt: string;
  isOpen: boolean;
  onClose: () => void;
  /** Minimum width for the lightbox image (ensures zoom effect) */
  minWidth?: number;
}

/** Focusable descendants, in DOM order. The dialog itself carries `tabIndex=-1`
 * and is excluded on purpose: it is a landing spot, not a tab stop. */
function focusablesIn(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  );
}

/**
 * ImageLightbox Component
 *
 * Displays images in a full-screen modal overlay with 3x zoom.
 * Features:
 * - Click outside to close
 * - ESC key to close
 * - Download button (fetch + blob for cross-origin support)
 * - Smooth fade-in animation
 * - Dark backdrop with glassmorphism
 * - Modal semantics: named `dialog`, focus taken on open, trapped while open
 *   and returned to the trigger on close
 */
export const ImageLightbox: React.FC<ImageLightboxProps> = ({
  src,
  alt,
  isOpen,
  onClose,
  minWidth,
}) => {
  const { t } = useTranslation();
  const [isDownloading, setIsDownloading] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Keyboard contract: Escape closes, Tab stays inside. Split from the focus
  // effect below because `onClose` is an inline arrow at every call site, so
  // this one re-runs on every parent render — swapping a listener is free,
  // moving focus is not.
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;

      // `aria-modal` tells assistive tech that the rest of the page is inert;
      // nothing in the DOM enforces that, so without this the very next Tab
      // walks out into content the user was just told did not exist.
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusables = focusablesIn(dialog);
      if (focusables.length === 0) return;

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;

      // Focus can sit outside the ring legitimately: on the dialog itself right
      // after opening, or on `body` after the download button disabled itself
      // under the user's fingers. Either way the next Tab belongs inside.
      if (!(active instanceof HTMLElement) || !dialog.contains(active) || active === dialog) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
        return;
      }
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Focus ownership and the scroll lock — keyed on `isOpen` ALONE. Depending on
  // `onClose` here would re-run this on every parent render (a streaming chat
  // message renders constantly while the lightbox is open), and each re-run
  // would restore focus to the thumbnail then bounce it back to the dialog,
  // stealing it from whichever control the keyboard user had reached.
  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = 'hidden';
    // Whoever had focus when the overlay opened — focus goes back there on
    // close, otherwise a keyboard user is dropped at the top of the document
    // and has to tab all the way back to the thumbnail they came from.
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Move focus into the dialog so screen readers announce it and Escape
    // reaches it without a prior tab.
    dialogRef.current?.focus();

    return () => {
      document.body.style.overflow = 'unset';
      previouslyFocused?.focus();
    };
  }, [isOpen]);

  const handleDownload = useCallback(async () => {
    setIsDownloading(true);
    try {
      await downloadImage(src, alt);
    } finally {
      setIsDownloading(false);
    }
  }, [src, alt]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop, as its own layer. role="presentation": closing by clicking
          outside is a pointer-only convenience (keyboard users have Escape and
          the named close button — audit F012/F045). Keeping the handler HERE
          rather than on the dialog is what lets the dialog stay a pure
          container: a div[role=dialog] carrying an onClick would owe a
          keyboard equivalent (jsx-a11y/click-events-have-key-events). */}
      <div
        role="presentation"
        className={cn(
          'absolute inset-0',
          'bg-background/95 backdrop-blur-md',
          'animate-in fade-in duration-300'
        )}
        onClick={onClose}
      />
      {/* The dialog spans the viewport so its controls keep their corner
          position, but stays pointer-transparent: clicks on the empty area fall
          through to the backdrop above, while the controls and the image opt
          back in. Both live inside the dialog, so a screen-reader user who
          lands here finds the close button without leaving the modal. `alt`
          names it — "photo of X" is exactly what is on screen. */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={alt}
        tabIndex={-1}
        className={cn(
          'absolute inset-0 flex items-center justify-center',
          'pointer-events-none focus:outline-none',
          'animate-in fade-in duration-300'
        )}
      >
        {/* Action buttons */}
        <div className="pointer-events-auto absolute top-4 right-4 z-10 flex items-center gap-2">
          {/* Download button */}
          <button
            onClick={handleDownload}
            disabled={isDownloading}
            className={cn(
              'p-2 rounded-full',
              'bg-background/80 hover:bg-background',
              'border border-border/50',
              'transition-all duration-200',
              'hover:scale-110',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            aria-label={t('common.download')}
          >
            {isDownloading ? (
              <Loader2 className="w-6 h-6 text-foreground animate-spin" />
            ) : (
              <Download className="w-6 h-6 text-foreground" />
            )}
          </button>

          {/* Close button */}
          <button
            onClick={onClose}
            className={cn(
              'p-2 rounded-full',
              'bg-background/80 hover:bg-background',
              'border border-border/50',
              'transition-all duration-200',
              'hover:scale-110'
            )}
            aria-label={t('common.close')}
          >
            <X className="w-6 h-6 text-foreground" />
          </button>
        </div>

        {/* Image container. No stop-propagation guard is needed any more: the
          backdrop is a sibling layer, not an ancestor, so a click on the image
          cannot reach it. */}
        <div
          className={cn(
            'pointer-events-auto relative max-w-7xl max-h-[90vh] p-4',
            'animate-in zoom-in-95 duration-300'
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            referrerPolicy="no-referrer"
            className={cn(
              'max-w-full max-h-[90vh] w-auto h-auto',
              'rounded-lg shadow-2xl',
              'border-2 border-border/30'
            )}
            style={{
              // Ensure minimum width for zoom effect (2x original display size)
              minWidth: minWidth ? `${minWidth}px` : undefined,
              width: 'auto',
              height: 'auto',
              maxWidth: '100%',
              maxHeight: '90vh',
            }}
          />
        </div>
      </div>
    </div>
  );
};
