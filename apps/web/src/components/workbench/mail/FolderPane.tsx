'use client';

/**
 * FolderPane — the mailbox's places (ADR-369, spec §6.3, mock-up « Main »).
 *
 * From `lg`, a named landmark of links beside the messages: « New message »
 * first, the system places (their role named in the reader's language), then
 * the person's own folders — Gmail's labels — each under its parent, the door
 * to the label manager where the provider has one, and the mailbox settings
 * every mailbox has. Below `lg`, a list above the messages as wide as the pane: a phone
 * draws a native one as narrow as it likes, and cuts the labels. It holds what the column
 * holds, in its order: each place, then the person's own under their title, each under its
 * parent and told whole. What a folder leaves
 * unread is the provider's own counter (ADR-185), read apart from the folders; a
 * folder it did not read draws none. A row dragged here lands on a place or on a
 * folder of the person's own (`takesDrop`), never on what is listed or on a view.
 */
import { useDroppable } from '@dnd-kit/core';
import Link from 'next/link';
import {
  Archive,
  Boxes,
  FileText,
  Folder,
  Inbox,
  type LucideIcon,
  OctagonAlert,
  Plus,
  Send,
  Settings2,
  Star,
  Tag,
  Tags,
  Trash2,
} from '@/lib/icons';
import { useId, useMemo } from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { folderTree, takesDrop } from '@/lib/workbench/mail';
import type { MailFolder, MailRole } from '@/lib/workbench/types';

import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';

const ROLE_ICONS: Readonly<Record<MailRole, LucideIcon>> = {
  inbox: Inbox,
  starred: Star,
  sent: Send,
  drafts: FileText,
  archive: Archive,
  all: Boxes,
  spam: OctagonAlert,
  trash: Trash2,
};

/** The steps a nested folder is drawn in from: a deep tree keeps a pane's width readable. */
const FOLDER_INDENT_REM = 0.75;
const FOLDER_INDENT_MAX_DEPTH = 4;
const FOLDER_PADDING_REM = 0.625;
/** Where an option's words start in the list: past the mark of the open one. */
const OPTION_PADDING_REM = 2;

export interface FolderPaneProps {
  lng: Language;
  folders: readonly MailFolder[] | undefined;
  /** The mailbox holds more folders than were read. */
  truncated?: boolean;
  openId: string;
  /** Gmail: the person's folders are labels (named and managed as such). */
  labels: boolean;
  hrefOf: (folderId: string) => string;
  /** Opens a folder from the phone's select. */
  onPick: (folderId: string) => void;
  onCompose: () => void;
  /** Opens the label manager; absent where the provider has no labels. */
  onManageLabels?: () => void;
  /** Opens the mailbox settings. */
  onSettings: () => void;
  /** A message is open: between `lg` and `xl` the pane steps aside for it. */
  readerOpen?: boolean;
  /** The pane as the person sized it on a large screen (its separator is the tool's). */
  pane?: WorkbenchPaneState;
  /** What each folder leaves unread, by its id; undefined until read. */
  unread?: Readonly<Record<string, number>>;
  /** Rows can be dragged here. */
  takesRows?: boolean;
}

/** A folder's name in the reader's language (a system place) or the person's own. */
export function useFolderName(lng: Language): (folder: MailFolder) => string {
  const { t } = useTranslation(lng);
  return folder =>
    folder.kind === 'system' && folder.role
      ? t(`workbench.mail.folders.${folder.role}`)
      : (folder.name ?? '');
}

/** The person's folders in their tree: sorted once per answer, not on every render. */
function useOwnFolders(folders: readonly MailFolder[] | undefined, lng: Language) {
  return useMemo(
    () =>
      folderTree(
        (folders ?? []).filter(folder => folder.kind === 'user'),
        lng
      ),
    [folders, lng]
  );
}

/** What the ear is told of a folder's link; undefined when its words say it all. */
function linkName(
  folder: MailFolder,
  name: string,
  depth: number,
  unread: number | undefined,
  unreadLabel: (name: string, count: number) => string
): string | undefined {
  const whole = depth > 0 ? (folder.name ?? undefined) : undefined;
  return unread ? unreadLabel(whole ?? name, unread) : whole;
}

function FolderLink({
  folder,
  name,
  depth = 0,
  open,
  href,
  icon: Icon,
  unread,
  listed,
  takesRows = false,
  unreadLabel,
}: {
  folder: MailFolder;
  name: string;
  depth?: number;
  open: boolean;
  href: string;
  icon: LucideIcon;
  unread: number | undefined;
  listed: string;
  takesRows?: boolean;
  /** Says the name and the figure as one (the eye reads them apart). */
  unreadLabel: (name: string, count: number) => string;
}) {
  const indent = Math.min(depth, FOLDER_INDENT_MAX_DEPTH) * FOLDER_INDENT_REM;
  const { setNodeRef: setTarget, isOver } = useDroppable({
    id: folder.id,
    disabled: !takesRows || !takesDrop(folder, listed),
  });
  const told = linkName(folder, name, depth, unread, unreadLabel);
  return (
    <li ref={setTarget}>
      <Link
        href={href}
        scroll={false}
        aria-current={open ? 'page' : undefined}
        // What the eye reads from its place, the ear is told whole.
        aria-label={told}
        style={depth > 0 ? { paddingInlineStart: `${FOLDER_PADDING_REM + indent}rem` } : undefined}
        data-folder={folder.id}
        className={cn(
          'flex min-h-10 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          open ? 'bg-primary/10 font-semibold text-primary' : 'text-foreground hover:bg-muted',
          isOver && 'bg-primary/20 ring-2 ring-primary'
        )}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">{name}</span>
        {unread ? (
          <span className="shrink-0 text-xs font-semibold tabular-nums">{unread}</span>
        ) : null}
      </Link>
    </li>
  );
}

/** The doors at the foot of the pane, where the provider has them. */
function PaneDoors({
  lng,
  labels,
  onManageLabels,
  onSettings,
}: Pick<FolderPaneProps, 'lng' | 'labels' | 'onManageLabels' | 'onSettings'>) {
  const { t } = useTranslation(lng);
  return (
    <div className="mt-auto space-y-0.5 border-t pt-3">
      {onManageLabels && (
        <Button variant="ghost" className="w-full justify-start gap-2" onClick={onManageLabels}>
          <Tags className="h-4 w-4" aria-hidden="true" />
          {t(labels ? 'workbench.mail.manage_labels' : 'workbench.mail.manage_folders')}
        </Button>
      )}
      <Button variant="ghost" className="w-full justify-start gap-2" onClick={onSettings}>
        <Settings2 className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.settings_title')}
      </Button>
    </div>
  );
}

/** The column beside the messages (from `lg`). */
export function FolderColumn({
  lng,
  folders,
  truncated = false,
  openId,
  labels,
  hrefOf,
  onCompose,
  onManageLabels,
  onSettings,
  readerOpen = false,
  pane,
  unread,
  takesRows = false,
}: FolderPaneProps) {
  const { t } = useTranslation(lng);
  const nameOf = useFolderName(lng);
  const own = useOwnFolders(folders, lng);
  const unreadLabel = (name: string, count: number) =>
    t('workbench.mail.folder_unread', { name, count });
  const places = (folders ?? []).filter(folder => folder.kind === 'system');
  const ownTitle = t(labels ? 'workbench.mail.labels_title' : 'workbench.mail.own_folders_title');
  return (
    <nav
      {...pane?.pane}
      aria-label={t('workbench.mail.folders_title')}
      className={cn(
        'hidden shrink-0 flex-col gap-3 overflow-y-auto border-r p-3',
        paneWidth(pane, 'w-56'),
        readerOpen ? 'xl:flex' : 'lg:flex'
      )}
    >
      <Button onClick={onCompose} className="w-full justify-start gap-2">
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.new_message')}
      </Button>
      {folders === undefined ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map(index => (
            <Skeleton key={index} className="h-8 w-full" />
          ))}
        </div>
      ) : (
        <ul className="space-y-0.5">
          {places.map(folder => (
            <FolderLink
              key={folder.id}
              folder={folder}
              name={nameOf(folder)}
              open={folder.id === openId}
              href={hrefOf(folder.id)}
              icon={folder.role ? ROLE_ICONS[folder.role] : Folder}
              unread={unread?.[folder.id]}
              listed={openId}
              takesRows={takesRows}
              unreadLabel={unreadLabel}
            />
          ))}
        </ul>
      )}
      {own.length > 0 && (
        <section aria-label={ownTitle} className="space-y-1">
          <h2 className="px-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {ownTitle}
          </h2>
          <ul className="space-y-0.5">
            {own.map(({ folder, name, depth }) => (
              <FolderLink
                key={folder.id}
                folder={folder}
                name={name}
                depth={depth}
                open={folder.id === openId}
                href={hrefOf(folder.id)}
                icon={labels ? Tag : Folder}
                unread={unread?.[folder.id]}
                listed={openId}
                takesRows={takesRows}
                unreadLabel={unreadLabel}
              />
            ))}
          </ul>
        </section>
      )}
      {truncated && (
        <p role="status" className="px-2.5 text-xs text-muted-foreground">
          {t('workbench.mail.folders_truncated')}
        </p>
      )}
      <PaneDoors
        lng={lng}
        labels={labels}
        onManageLabels={onManageLabels}
        onSettings={onSettings}
      />
    </nav>
  );
}

/** One folder of the list: the eye reads it from its place, the ear is told it whole. */
function FolderOption({
  folder,
  name,
  depth = 0,
  icon: Icon,
  unread,
  unreadLabel,
}: {
  folder: MailFolder;
  name: string;
  depth?: number;
  icon: LucideIcon;
  unread: number | undefined;
  unreadLabel: (name: string, count: number) => string;
}) {
  const indent = Math.min(depth, FOLDER_INDENT_MAX_DEPTH) * FOLDER_INDENT_REM;
  const whole = folder.kind === 'user' ? (folder.name ?? name) : name;
  return (
    <SelectItem
      value={folder.id}
      textValue={name}
      style={depth > 0 ? { paddingInlineStart: `${OPTION_PADDING_REM + indent}rem` } : undefined}
      className="[&>span:last-child]:min-w-0 [&>span:last-child]:flex-1"
    >
      <span className="flex min-w-0 items-center gap-2">
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span aria-hidden="true" className="min-w-0 flex-1 break-words">
          {name}
        </span>
        {unread ? (
          <span aria-hidden="true" className="shrink-0 text-xs font-semibold tabular-nums">
            {unread}
          </span>
        ) : null}
        <span className="sr-only">{unread ? unreadLabel(whole, unread) : whole}</span>
      </span>
    </SelectItem>
  );
}

/** The list above the messages (below `lg`). */
export function FolderSelect({
  lng,
  folders,
  truncated = false,
  openId,
  labels,
  onPick,
  unread,
}: FolderPaneProps) {
  const { t } = useTranslation(lng);
  const nameOf = useFolderName(lng);
  const id = useId();
  const own = useOwnFolders(folders, lng);
  if (!folders || folders.length === 0) return null;
  const known = folders.some(folder => folder.id === openId);
  const unreadLabel = (name: string, count: number) =>
    t('workbench.mail.folder_unread', { name, count });
  const places = folders.filter(folder => folder.kind !== 'user');
  return (
    <div className="border-b px-3 py-2 lg:hidden">
      <Label id={`${id}-label`} className="sr-only">
        {t('workbench.mail.folder')}
      </Label>
      <Select value={known ? openId : ''} onValueChange={onPick}>
        <SelectTrigger
          aria-labelledby={`${id}-label`}
          className="h-11 rounded-md bg-card font-semibold"
        >
          <SelectValue placeholder={t('workbench.mail.folder')} />
        </SelectTrigger>
        <SelectContent className="w-[var(--radix-select-trigger-width)]">
          {places.map(folder => (
            <FolderOption
              key={folder.id}
              folder={folder}
              name={nameOf(folder)}
              icon={folder.role ? ROLE_ICONS[folder.role] : Folder}
              unread={unread?.[folder.id]}
              unreadLabel={unreadLabel}
            />
          ))}
          {own.length > 0 && (
            <SelectGroup>
              <SelectLabel>
                {t(labels ? 'workbench.mail.labels_title' : 'workbench.mail.own_folders_title')}
              </SelectLabel>
              {own.map(({ folder, name, depth }) => (
                <FolderOption
                  key={folder.id}
                  folder={folder}
                  name={name}
                  depth={depth}
                  icon={labels ? Tag : Folder}
                  unread={unread?.[folder.id]}
                  unreadLabel={unreadLabel}
                />
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>
      {truncated && (
        <p role="status" className="mt-2 text-xs text-muted-foreground">
          {t('workbench.mail.folders_truncated')}
        </p>
      )}
    </div>
  );
}
