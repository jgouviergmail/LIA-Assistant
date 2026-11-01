'use client';

/**
 * FolderPane — the mailbox's places (ADR-369, spec §6.3, mock-up « Main »).
 *
 * From `lg`, a named landmark of links beside the messages: « New message »
 * first, the system places (their role named in the reader's language), then
 * the person's own folders — Gmail's labels — and the doors to the label
 * manager and the mailbox settings where the provider has them. Below `lg`, a
 * native select above the messages (what the keyboard and the screen reader
 * already know). No count is drawn beside a folder: one would be exact only
 * once every message of it was read (ADR-185).
 */
import Link from 'next/link';
import {
  Archive,
  FileText,
  Folder,
  Inbox,
  type LucideIcon,
  OctagonAlert,
  PenSquare,
  Send,
  Settings2,
  Star,
  Tag,
  Tags,
  Trash2,
} from 'lucide-react';
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { MailFolder, MailRole } from '@/lib/workbench/types';

import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';

const ROLE_ICONS: Readonly<Record<MailRole, LucideIcon>> = {
  inbox: Inbox,
  starred: Star,
  sent: Send,
  drafts: FileText,
  archive: Archive,
  spam: OctagonAlert,
  trash: Trash2,
};

export interface FolderPaneProps {
  lng: Language;
  folders: readonly MailFolder[] | undefined;
  openId: string;
  /** Gmail: the person's folders are labels (named and managed as such). */
  labels: boolean;
  hrefOf: (folderId: string) => string;
  /** Opens a folder from the phone's select. */
  onPick: (folderId: string) => void;
  onCompose: () => void;
  /** Opens the label manager; absent where the provider has no labels. */
  onManageLabels?: () => void;
  /** Opens the mailbox settings; absent where the provider has none. */
  onSettings?: () => void;
  /** A message is open: between `lg` and `xl` the pane steps aside for it. */
  readerOpen?: boolean;
  /** The pane as the person sized it on a large screen (its separator is the tool's). */
  pane?: WorkbenchPaneState;
}

/** A folder's name in the reader's language (a system place) or the person's own. */
export function useFolderName(lng: Language): (folder: MailFolder) => string {
  const { t } = useTranslation(lng);
  return folder =>
    folder.kind === 'system' && folder.role
      ? t(`workbench.mail.folders.${folder.role}`)
      : (folder.name ?? '');
}

function FolderLink({
  folder,
  name,
  open,
  href,
  icon: Icon,
}: {
  folder: MailFolder;
  name: string;
  open: boolean;
  href: string;
  icon: LucideIcon;
}) {
  return (
    <li>
      <Link
        href={href}
        scroll={false}
        aria-current={open ? 'page' : undefined}
        data-folder={folder.id}
        className={cn(
          'flex min-h-10 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          open ? 'bg-primary/10 font-semibold text-primary' : 'text-foreground hover:bg-muted'
        )}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">{name}</span>
      </Link>
    </li>
  );
}

/** The column beside the messages (from `lg`). */
export function FolderColumn({
  lng,
  folders,
  openId,
  labels,
  hrefOf,
  onCompose,
  onManageLabels,
  onSettings,
  readerOpen = false,
  pane,
}: FolderPaneProps) {
  const { t } = useTranslation(lng);
  const nameOf = useFolderName(lng);
  const own = (folders ?? []).filter(folder => folder.kind === 'user');
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
        <PenSquare className="h-4 w-4" aria-hidden="true" />
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
            {own.map(folder => (
              <FolderLink
                key={folder.id}
                folder={folder}
                name={nameOf(folder)}
                open={folder.id === openId}
                href={hrefOf(folder.id)}
                icon={labels ? Tag : Folder}
              />
            ))}
          </ul>
        </section>
      )}
      {(onManageLabels || onSettings) && (
        <div className="mt-auto space-y-0.5 border-t pt-3">
          {onManageLabels && (
            <Button variant="ghost" className="w-full justify-start gap-2" onClick={onManageLabels}>
              <Tags className="h-4 w-4" aria-hidden="true" />
              {t('workbench.mail.manage_labels')}
            </Button>
          )}
          {onSettings && (
            <Button variant="ghost" className="w-full justify-start gap-2" onClick={onSettings}>
              <Settings2 className="h-4 w-4" aria-hidden="true" />
              {t('workbench.mail.settings_title')}
            </Button>
          )}
        </div>
      )}
    </nav>
  );
}

/** The select above the messages (below `lg`). */
export function FolderSelect({ lng, folders, openId, labels, onPick }: FolderPaneProps) {
  const { t } = useTranslation(lng);
  const nameOf = useFolderName(lng);
  const id = useId();
  if (!folders || folders.length === 0) return null;
  const known = folders.some(folder => folder.id === openId);
  return (
    <div className="border-b px-4 py-3 lg:hidden">
      <Label id={`${id}-label`} htmlFor={id} className="sr-only">
        {t('workbench.mail.folder')}
      </Label>
      <select
        id={id}
        aria-labelledby={`${id}-label`}
        value={known ? openId : ''}
        onChange={event => onPick(event.target.value)}
        className="h-11 w-full rounded-md border border-input bg-card px-3 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {!known && (
          <option value="" disabled>
            {t('workbench.mail.folder')}
          </option>
        )}
        {folders.map(folder => (
          <option key={folder.id} value={folder.id}>
            {folder.kind === 'user'
              ? t(labels ? 'workbench.mail.label_option' : 'workbench.mail.folder_option', {
                  name: nameOf(folder),
                })
              : nameOf(folder)}
          </option>
        ))}
      </select>
    </div>
  );
}
