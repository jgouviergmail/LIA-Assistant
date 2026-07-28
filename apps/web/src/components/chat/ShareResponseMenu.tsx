import { useCallback } from 'react';
import { Download, MoreHorizontal, Share2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { downloadMarkdown } from '@/lib/utils/download-markdown';

/** Two-digit zero-pad for the filename date components. */
function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** `lia-YYYY-MM-DD-HH-mm`, stamped from the user's local clock. */
function exportBaseName(timestamp: Date): string {
  const date = `${timestamp.getFullYear()}-${pad2(timestamp.getMonth() + 1)}-${pad2(timestamp.getDate())}`;
  return `lia-${date}-${pad2(timestamp.getHours())}-${pad2(timestamp.getMinutes())}`;
}

export interface ShareResponseMenuProps {
  /** Raw markdown of the assistant response. */
  content: string;
  /** When the response landed — stamps the export filename (local time). */
  timestamp: Date;
}

/**
 * "…" menu at the end of the assistant bubble action row (UX P4): the
 * platform share sheet where `navigator.share` exists, and a dated `.md`
 * export everywhere. Share availability is FEATURE detection, never platform
 * sniffing — desktop Chrome/Edge on Windows expose `navigator.share` too.
 * Non-modal like every navigation menu (ADR-171: modal Radix menus turn
 * `body` into a scrollport and break sticky headers).
 */
export function ShareResponseMenu({ content, timestamp }: ShareResponseMenuProps) {
  const { t } = useTranslation();
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  const handleShare = useCallback(async () => {
    try {
      await navigator.share({ title: 'LIA', text: content });
    } catch (err) {
      // A dismissed share sheet reports AbortError — a non-event, not a failure.
      if (err instanceof DOMException && err.name === 'AbortError') return;
      toast.error(t('chat.message.share_error'));
    }
  }, [content, t]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('chat.message.more_actions')}
          className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors"
        >
          <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {canShare && (
          <DropdownMenuItem onSelect={() => void handleShare()}>
            <Share2 className="text-muted-foreground" />
            {t('chat.message.share')}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => downloadMarkdown(content, exportBaseName(timestamp))}>
          <Download className="text-muted-foreground" />
          {t('chat.message.download_md')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
