'use client';

import React, { useCallback, useEffect, useState } from 'react';
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

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

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
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center',
        'bg-background/95 backdrop-blur-md',
        'animate-in fade-in duration-300'
      )}
      onClick={onClose}
    >
      {/* Action buttons */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        {/* Download button */}
        <button
          onClick={e => {
            e.stopPropagation();
            handleDownload();
          }}
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

      {/* Image container - 3x larger than original */}
      <div
        className={cn('relative max-w-7xl max-h-[90vh] p-4', 'animate-in zoom-in-95 duration-300')}
        onClick={e => e.stopPropagation()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
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
  );
};
