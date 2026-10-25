/**
 * The « + » offers the person's kept answers (owner request 2026-10-24).
 *
 * A kept answer joins the message as the document its knowledge space reads —
 * the request quoted, the answer, its date — copied by the API whatever state
 * its projection is in (ADR-291). The list is the bookmarks' own, searched by
 * the words of the request and the answer, a page and its exact total.
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bookmark as BookmarkIcon, MessageSquareText } from 'lucide-react';

import { AttachSourcePickerDialog, type PickerWords } from './AttachSourcePickerDialog';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import { useNeedlePage } from '@/hooks/useNeedlePage';
import { copyAttachSource } from '@/lib/attach-sources';
import { formatDate } from '@/lib/format';
import { fallbackLng, isLanguage } from '@/i18n/settings';
import type { Bookmark } from '@/types/bookmarks';

const WORDS: PickerWords = {
  title: 'chat.bookmark_picker.title',
  description: 'chat.bookmark_picker.description',
  searchPlaceholder: 'chat.bookmark_picker.search_placeholder',
  loading: 'chat.bookmark_picker.loading',
  empty: 'chat.bookmark_picker.empty',
  emptySearch: 'chat.bookmark_picker.empty_search',
  error: 'chat.bookmark_picker.error',
  moreHint: 'chat.attach_picker.more_hint',
  remaining: 'chat.attach_picker.remaining',
  attach: 'chat.attach_picker.attach',
  alreadyAttached: 'chat.attach_picker.already_attached',
  attachError: 'chat.attach_picker.attach_error',
};

/** How long a request or an answer reads in one row before it is cut. */
const LABEL_MAX_CHARS = 120;

/** The row's name: the person's request, else the opening of the answer. */
export function bookmarkLabel(bookmark: Bookmark): string {
  const source = bookmark.request_content?.trim() || bookmark.content.replace(/<[^>]*>/g, ' ');
  const line = source.replace(/\s+/g, ' ').trim();
  return line.length > LABEL_MAX_CHARS ? `${line.slice(0, LABEL_MAX_CHARS - 1)}…` : line;
}

interface BookmarkPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  remaining: number;
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome;
}

export function BookmarkPickerDialog(props: BookmarkPickerDialogProps) {
  const { i18n } = useTranslation();
  const [needle, setNeedle] = useState('');
  const page = useNeedlePage<Bookmark>('/bookmarks', needle, props.open);
  return (
    <AttachSourcePickerDialog<Bookmark>
      {...props}
      icon={BookmarkIcon}
      itemIcon={MessageSquareText}
      words={WORDS}
      needle={needle}
      onNeedleChange={setNeedle}
      page={page}
      idOf={bookmark => bookmark.id}
      labelOf={bookmarkLabel}
      metaOf={bookmark => (
        <span>
          {formatDate(
            bookmark.answered_at,
            isLanguage(i18n.language) ? i18n.language : fallbackLng,
            {
              dateStyle: 'medium',
            }
          )}
        </span>
      )}
      copy={bookmark => copyAttachSource({ kind: 'bookmark', id: bookmark.id })}
    />
  );
}
