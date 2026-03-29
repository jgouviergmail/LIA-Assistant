'use client';

import { Globe } from 'lucide-react';
import { BrowserScreenshotData } from '@/types/chat';
import { useTranslation } from 'react-i18next';

interface BrowserScreenshotOverlayProps {
  screenshot: BrowserScreenshotData;
}

/**
 * Inline overlay displaying progressive browser screenshots in the chat flow.
 * Rendered inside ChatMessageList, just before the typing indicator.
 * Persists until replaced by a new screenshot or cleared by STREAM_DONE.
 * No auto-dismiss — the overlay represents ongoing browser activity.
 */
export function BrowserScreenshotOverlay({ screenshot }: BrowserScreenshotOverlayProps) {
  const { t } = useTranslation();

  const displayUrl =
    screenshot.url.length > 60 ? screenshot.url.slice(0, 57) + '...' : screenshot.url;

  return (
    <div
      role="status"
      aria-live="polite"
      className="mb-4 animate-message-enter mobile:flex mobile:flex-row-reverse mobile:gap-3"
    >
      {/* Avatar — matches LIA assistant avatar style */}
      <div className="hidden mobile:block flex-shrink-0">
        <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm">
          LIA
        </div>
      </div>

      {/* Screenshot card — styled like an assistant message bubble */}
      <div className="flex flex-col w-full mobile:flex-1 items-end">
        <div className="w-full max-w-[512px] rounded-xl shadow-md bg-card/70 backdrop-blur-md border border-border/20 rounded-tr-none mobile:rounded-tr-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30">
            <Globe className="h-3.5 w-3.5 text-primary flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">
                {screenshot.title || t('browser.screenshot.viewing')}
              </p>
              <p className="text-[10px] text-muted-foreground truncate">{displayUrl}</p>
            </div>
          </div>
          {/* Screenshot */}
          <div className="p-1.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/jpeg;base64,${screenshot.image_base64}`}
              alt={screenshot.title || 'Browser screenshot'}
              className="w-full rounded transition-opacity duration-300"
              loading="eager"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
