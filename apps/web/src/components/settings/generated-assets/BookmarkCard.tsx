'use client';

/**
 * One kept answer (ADR-282).
 *
 * The request that produced it, quoted and clamped; the answer rendered by the
 * chat's own component (`MarkdownContent`, so markdown AND the `lia-response`
 * HTML documents keep their form); the answer's date; and the three things a
 * person came for — share it, download it as Markdown, let it go.
 *
 * Two rules from the galleries: a download is built client-side from what is
 * already local (the chat's export path), and delete asks first.
 */

import { ChevronDown, ChevronUp, Download, Share2, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { MarkdownContent } from '@/components/chat/MarkdownContent';
import { Button } from '@/components/ui/button';
import { useConfirm } from '@/components/ui/use-confirm';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { bookmarkExportBaseName, bookmarkToMarkdown } from '@/lib/bookmarks/markdown';
import { formatDate } from '@/lib/format';
import { messageToPlainText } from '@/lib/message-clipboard';
import { downloadMarkdown } from '@/lib/utils/download-markdown';
import { cn } from '@/lib/utils';
import type { Bookmark } from '@/types/bookmarks';

export interface BookmarkCardProps {
  lng: Language;
  bookmark: Bookmark;
  onDeleted: () => void;
}

/** Below this many characters the answer is shown whole; above, it folds. */
const FOLD_THRESHOLD = 600;

export function BookmarkCard({ lng, bookmark, onDeleted }: BookmarkCardProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [expanded, setExpanded] = useState(false);
  const { mutate: remove } = useApiMutation<undefined, undefined>({
    method: 'DELETE',
    componentName: 'BookmarkCard',
  });

  const answeredOn = formatDate(bookmark.answered_at, lng, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  const foldable = bookmark.content.length > FOLD_THRESHOLD;
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  const share = async () => {
    try {
      await navigator.share({ title: 'LIA', text: messageToPlainText(bookmark.content) });
    } catch (error) {
      // A dismissed share sheet reports AbortError — a non-event, not a failure.
      if (error instanceof DOMException && error.name === 'AbortError') return;
      toast.error(t('settings.bookmarks.share_error'));
    }
  };

  const download = () => {
    downloadMarkdown(
      bookmarkToMarkdown(bookmark, {
        request: t('settings.bookmarks.export_request'),
        answer: t('settings.bookmarks.export_answer'),
        kept: t('settings.bookmarks.export_kept', { when: answeredOn }),
      }),
      bookmarkExportBaseName(bookmark)
    );
  };

  const deleteOne = async () => {
    const ok = await confirm({
      title: t('settings.bookmarks.confirm_delete_title'),
      description: t('settings.bookmarks.confirm_delete_description'),
      confirmLabel: t('common.delete'),
      destructive: true,
    });
    if (!ok) return;
    try {
      await remove(`/bookmarks/${bookmark.id}`, undefined);
    } catch {
      toast.error(t('common.error'));
      return;
    }
    toast.success(t('settings.bookmarks.deleted'));
    onDeleted();
  };

  return (
    <li
      data-testid="bookmark-card"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <p className="text-xs text-muted-foreground">
        {t('settings.bookmarks.answered_at', { when: answeredOn })}
      </p>

      {/* The request, as a quotation: what the answer answers. A message LIA
          sent on its own initiative had no request, and says so rather than
          borrowing the person's previous words. */}
      <blockquote className="border-l-2 border-primary/40 pl-3 text-sm">
        <span className="block text-xs font-medium text-muted-foreground">
          {t('settings.bookmarks.request')}
        </span>
        {bookmark.request_content ? (
          <span
            className="line-clamp-3 whitespace-pre-line break-words"
            title={bookmark.request_content}
          >
            {bookmark.request_content}
          </span>
        ) : (
          <span className="italic text-muted-foreground">{t('settings.bookmarks.no_request')}</span>
        )}
      </blockquote>

      <div
        className={cn(
          'relative overflow-hidden rounded-lg border border-border/60 bg-background px-3 py-2 text-sm',
          foldable && !expanded && 'max-h-64'
        )}
      >
        <MarkdownContent content={bookmark.content} isUser={false} />
        {foldable && !expanded && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background to-transparent"
          />
        )}
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-1 pt-1">
        {foldable && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(previous => !previous)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronUp className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            )}
            {expanded ? t('settings.bookmarks.show_less') : t('settings.bookmarks.show_more')}
          </Button>
        )}
        <span className="flex-1" />
        {canShare && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void share()}
            aria-label={t('settings.bookmarks.share')}
          >
            <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={download}
          aria-label={t('settings.bookmarks.download')}
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void deleteOne()}
          aria-label={t('settings.bookmarks.delete')}
          className="text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
      {confirmDialog}
    </li>
  );
}
