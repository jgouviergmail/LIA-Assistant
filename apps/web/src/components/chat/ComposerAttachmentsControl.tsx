'use client';

/**
 * The « + » of the composer.
 *
 * ONE gesture when there is one thing to do: in a browser — a PWA included —
 * a click opens the file picker, because the browser's own chooser already
 * offers the camera next to the gallery. A MENU as soon as a second entry
 * exists: the Android shell's camera (Capacitor hands the WebView's bare
 * intent to the system without the capture intent a browser adds itself —
 * measured absent on a OneUI 9 device, 2026-09-04; iOS is excluded on
 * purpose, WKWebView offers "Take Photo" on an image input itself, ADR-246),
 * the person's knowledge-space documents when the spaces are on, and — since
 * 2026-10-24 — what LIA already gave them: a kept answer, a generated file.
 * Each picker attaches a COPY the API makes (`AttachSourcePickerDialog`). The
 * last entry is no attachment: a recording file imported as a MEETING, whose
 * page then opens (owner request 2026-10-24).
 */

import { useRef, useState, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bookmark,
  Camera,
  FileAudio,
  Images,
  Library,
  Paperclip,
  Plus,
  type LucideIcon,
} from 'lucide-react';

import { BookmarkPickerDialog } from '@/components/chat/BookmarkPickerDialog';
import { GeneratedFilePickerDialog } from '@/components/chat/GeneratedFilePickerDialog';
import { KnowledgeDocumentPickerDialog } from '@/components/chat/KnowledgeDocumentPickerDialog';
import { MeetingImportDialog } from '@/components/meetings/MeetingImportDialog';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import { fallbackLng, isLanguage } from '@/i18n/settings';
import { isAndroidShell } from '@/lib/native/shell';

/**
 * The composer's side buttons: 44 px wide on a phone, the comfortable touch
 * minimum, 40 px once the row is wider than `mobile` — so the typing area keeps
 * the width (owner arbitration 2026-09-03).
 */
export const COMPOSER_ACTION_BUTTON = 'h-12 w-11 shrink-0 self-end p-0 mobile:w-10';

/** Inert subscription for the shell-detection useSyncExternalStore gate. */
const shellSubscribe = () => () => {};

/**
 * Whether this render is happening inside the Android shell.
 *
 * The server has no shell to detect, so the answer cannot be read during the
 * first render without making the server's markup and the client's hydration
 * disagree. Same gate as EyesWidget: a server snapshot of `false` — the browser
 * branch, which is also the one that degrades correctly should detection never
 * run — then the client's own answer. `useSyncExternalStore` rather than a
 * mount effect, because setState-in-an-effect is a ratcheted violation.
 *
 * @returns True once the page has confirmed it runs inside a shell.
 */
function useInAndroidShell(): boolean {
  return useSyncExternalStore(
    shellSubscribe,
    () => isAndroidShell(),
    () => false
  );
}

type Picker = 'knowledge' | 'bookmark' | 'generated' | 'meeting_import';

interface Entry {
  key: string;
  icon: React.ReactNode;
  label: string;
  open: () => void;
}

export interface ComposerAttachmentsControlProps {
  t: (key: string) => string;
  attachmentsEnabled: boolean;
  knowledgeDocumentsEnabled?: boolean;
  /** The person's kept answers can be attached (the bookmark routes are mounted). */
  bookmarksEnabled?: boolean;
  /** The person's generated files can be attached. */
  generatedFilesEnabled?: boolean;
  /** A recording file can be imported as a meeting (the instance offers it). */
  meetingImportEnabled?: boolean;
  disabled: boolean;
  onPickFile: () => void;
  onTakePhoto: () => void;
  /** Room left in the message: the pickers bound their selection by it. */
  remaining: number;
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome;
}

/** The menu's entries, in their order: the file, the camera, then the copies. */
function composerEntries(
  props: ComposerAttachmentsControlProps,
  inShell: boolean,
  openPicker: (picker: Picker) => void
): Entry[] {
  const { t } = props;
  const entries: Entry[] = [
    {
      key: 'file',
      icon: <Paperclip className="mr-2 h-4 w-4" aria-hidden="true" />,
      label: t('chat.attachments.attach_file'),
      open: props.onPickFile,
    },
  ];
  if (inShell)
    entries.push({
      key: 'photo',
      icon: <Camera className="mr-2 h-4 w-4" aria-hidden="true" />,
      label: t('chat.attachments.take_photo'),
      open: props.onTakePhoto,
    });
  const copies: Array<[boolean | undefined, Picker, LucideIcon, string]> = [
    [props.knowledgeDocumentsEnabled, 'knowledge', Library, 'from_knowledge'],
    [props.bookmarksEnabled, 'bookmark', Bookmark, 'from_bookmark'],
    [props.generatedFilesEnabled, 'generated', Images, 'from_generated'],
    [props.meetingImportEnabled, 'meeting_import', FileAudio, 'import_meeting'],
  ];
  for (const [enabled, picker, Icon, label] of copies) {
    if (!enabled) continue;
    entries.push({
      key: picker,
      icon: <Icon className="mr-2 h-4 w-4" aria-hidden="true" />,
      label: t(`chat.attachments.${label}`),
      open: () => openPicker(picker),
    });
  }
  return entries;
}

/** The import dialog in the composer, in the language the chat speaks. */
function ComposerMeetingImport({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { i18n } = useTranslation();
  const lng = isLanguage(i18n.language) ? i18n.language : fallbackLng;
  return <MeetingImportDialog lng={lng} open={open} onOpenChange={onOpenChange} />;
}

function ComposerPickers({
  props,
  open,
  onOpenChange,
}: {
  props: ComposerAttachmentsControlProps;
  open: Picker | null;
  onOpenChange: (picker: Picker | null) => void;
}) {
  const shared = {
    remaining: props.remaining,
    onAttached: props.onAttached,
  };
  const toggle = (picker: Picker) => (isOpen: boolean) => onOpenChange(isOpen ? picker : null);
  return (
    <>
      {props.knowledgeDocumentsEnabled && (
        <KnowledgeDocumentPickerDialog
          {...shared}
          open={open === 'knowledge'}
          onOpenChange={toggle('knowledge')}
        />
      )}
      {props.bookmarksEnabled && (
        <BookmarkPickerDialog
          {...shared}
          open={open === 'bookmark'}
          onOpenChange={toggle('bookmark')}
        />
      )}
      {props.generatedFilesEnabled && (
        <GeneratedFilePickerDialog
          {...shared}
          open={open === 'generated'}
          onOpenChange={toggle('generated')}
        />
      )}
      {props.meetingImportEnabled && (
        <ComposerMeetingImport
          open={open === 'meeting_import'}
          onOpenChange={toggle('meeting_import')}
        />
      )}
    </>
  );
}

export function ComposerAttachmentsControl(props: ComposerAttachmentsControlProps) {
  const { t, attachmentsEnabled, disabled } = props;
  const inShell = useInAndroidShell();
  const [picker, setPicker] = useState<Picker | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  if (!attachmentsEnabled) return null;

  const entries = composerEntries(props, inShell, setPicker);
  const single = entries.length === 1;

  const trigger = (
    <Button
      ref={triggerRef}
      type="button"
      variant="ghost"
      size="lg"
      className={COMPOSER_ACTION_BUTTON}
      disabled={disabled}
      onClick={single ? entries[0].open : undefined}
      aria-label={t('chat.attachments.add')}
    >
      <Plus className="h-5 w-5" aria-hidden="true" />
    </Button>
  );

  if (single) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipContent>{t('chat.attachments.add')}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {entries.map(entry => (
            <DropdownMenuItem
              key={entry.key}
              onSelect={() => {
                // Keep the task boundary the native file chooser needs. A
                // manual picker must capture the lasting button, not this item.
                setTimeout(() => {
                  if (entry.key !== 'file' && entry.key !== 'photo') {
                    triggerRef.current?.focus({ preventScroll: true });
                  }
                  entry.open();
                }, 0);
              }}
            >
              {entry.icon}
              {entry.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <ComposerPickers props={props} open={picker} onOpenChange={setPicker} />
    </>
  );
}
