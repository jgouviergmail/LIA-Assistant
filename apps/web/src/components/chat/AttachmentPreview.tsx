/**
 * Horizontal scrollable preview strip for pending attachments.
 *
 * Displayed above the ChatInput textarea. Shows:
 * - Image thumbnails (via object URL)
 * - PDF file icons
 * - Upload progress overlay
 * - Remove button (X)
 *
 * Phase: evolution F4 — File Attachments & Vision Analysis
 * Created: 2026-03-09
 */

'use client';

import { X, FileText, Loader2 } from 'lucide-react';
import type { PendingAttachment } from '@/hooks/useFileUpload';
import { formatFileSize } from '@/lib/utils/image-compress';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';

interface AttachmentPreviewProps {
  attachments: PendingAttachment[];
  onRemove: (tempId: string) => void;
}

export default function AttachmentPreview({ attachments, onRemove }: AttachmentPreviewProps) {
  const { t } = useTranslation();
  if (attachments.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto py-2 px-1 chat-scrollbar">
      {attachments.map(att => (
        <div
          key={att.tempId}
          className="relative flex-shrink-0 w-20 h-20 rounded-lg border border-border bg-muted overflow-hidden group"
        >
          {/* Content */}
          {att.contentType === 'image' && att.previewUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element -- Local blob preview URL, no optimization needed */
            <img src={att.previewUrl} alt={att.filename} className="w-full h-full object-cover" />
          ) : (
            <div className="flex flex-col items-center justify-center h-full p-1">
              <FileText className="h-8 w-8 text-muted-foreground" />
              <span className="text-[9px] text-muted-foreground truncate w-full text-center mt-0.5">
                {att.filename}
              </span>
            </div>
          )}

          {/* Upload progress overlay */}
          {att.status === 'uploading' && (
            <div className="absolute inset-0 bg-background/70 flex items-center justify-center">
              <div className="relative">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="absolute inset-0 flex items-center justify-center text-[9px] font-medium">
                  {att.progress}%
                </span>
              </div>
            </div>
          )}

          {/* Error overlay */}
          {att.status === 'error' && (
            <div className="absolute inset-0 bg-destructive/20 flex items-center justify-center">
              <span className="text-[10px] text-destructive font-medium">!</span>
            </div>
          )}

          {/* Remove button — always visible on mobile (no hover), visible on hover/focus on desktop */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => onRemove(att.tempId)}
                className="absolute top-0.5 right-0.5 rounded-full bg-background/80 p-0.5 opacity-100 mobile:opacity-0 mobile:group-hover:opacity-100 mobile:focus:opacity-100 transition-opacity hover:bg-destructive hover:text-destructive-foreground"
                aria-label={t('chat.attachments.remove')}
              >
                <X className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent>{t('chat.attachments.remove')}</TooltipContent>
          </Tooltip>

          {/* File size badge */}
          <div className="absolute bottom-0.5 left-0.5 bg-background/80 rounded px-1">
            <span className="text-[8px] text-muted-foreground">{formatFileSize(att.size)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
