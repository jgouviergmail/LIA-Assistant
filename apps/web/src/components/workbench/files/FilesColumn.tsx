'use client';

/**
 * FilesColumn — the list side of the files screen (ADR-369): the finder, the views,
 * what the folder offers, the acts on what is ticked, and the list. Files sent or
 * dropped belong to it alone: they go where the list stands, and a search stands
 * nowhere.
 */
import { FolderPlus, Search, Trash2, Upload, X } from 'lucide-react';
import Link from 'next/link';
import { useRef, useState, type ChangeEvent, type FormEvent, type RefObject } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import type { WorkbenchFilesState } from '@/hooks/useWorkbenchFiles';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import {
  FILE_ORDERS,
  FILE_VIEWS,
  trailTo,
  type FileOrder,
  type FileView,
} from '@/lib/workbench/files';
import { fileWord } from '@/lib/workbench/files-words';
import { fileSize } from '@/lib/workbench/mail';
import type { WorkbenchDriveItem, WorkbenchDriveQuota } from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import type { ListSelection } from '../useListSelection';
import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';
import { Breadcrumb } from './Breadcrumb';
import { FileList } from './FileList';
import type { FileAct, FilePlace } from './FileOrganizer';
import { FileSelectionBar } from './FileSelectionBar';
import { FileSendingLine, useFileDrop } from './FileSending';
import type { FilesScreen } from './useFilesScreen';
import { useFileSending } from './useFileSending';
import type { FileTrash } from './useFileTrash';

interface FilesColumnProps {
  lng: Language;
  provider: string | null;
  viewsOffered: boolean;
  screen: FilesScreen;
  state: WorkbenchFilesState;
  selection: ListSelection;
  trash: FileTrash;
  pane: WorkbenchPaneState;
  searchRef: RefObject<HTMLInputElement | null>;
  linkRef: (id: string, element: HTMLElement | null) => void;
  onAct: (act: FileAct) => void;
}

/** What an empty list says. */
function emptyKeyOf(searching: boolean, view: FileView | null): string {
  if (searching) return 'workbench.files.empty_search';
  return view ? 'workbench.files.empty_view' : 'workbench.files.empty_folder';
}

/** Where the list's items sit: a search's and a view's can sit anywhere. */
function listPlaceOf(screen: FilesScreen, state: WorkbenchFilesState): FilePlace {
  return screen.standing
    ? { trail: trailTo(state.folder.item), from: screen.address.folder }
    : { trail: [], from: undefined };
}

/** The item ticked alone, while the list still holds it. */
function tickedAlone(
  selected: ReadonlySet<string>,
  ticked: readonly WorkbenchDriveItem[]
): WorkbenchDriveItem | null {
  return selected.size === 1 ? (ticked[0] ?? null) : null;
}

export function FilesColumn({
  lng,
  provider,
  viewsOffered,
  screen,
  state,
  selection,
  trash,
  pane,
  searchRef,
  linkRef,
  onAct,
}: FilesColumnProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { availability } = useWorkbench();
  const { address, searching, standing, inTrash } = screen;
  const { selected, select, toggle } = selection;
  const { refresh: rereadList } = state.list;
  const sending = useFileSending({
    lng,
    maxBytes: availability.limits.upload_max_bytes,
    onSent: () => void rereadList(),
  });
  const onFiles = (files: File[]) => sending.send(files, address.folder);
  const drop = useFileDrop({ lng, enabled: standing, onFiles });
  const rowIds = state.list.items.map(item => item.id);
  const ticked = state.list.items.filter(item => selected.has(item.id));
  const listPlace = listPlaceOf(screen, state);
  const star = (item: WorkbenchDriveItem) => {
    state.star(item, !item.starred).catch((error: unknown) => {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
    });
  };

  return (
    <div
      {...pane.pane}
      {...drop.handlers}
      data-testid="files-drop"
      className={cn(
        'relative min-w-0 flex-col lg:border-r',
        paneWidth(pane, 'lg:w-[26rem] lg:flex-none'),
        address.file ? 'hidden lg:flex' : 'flex flex-1'
      )}
    >
      <ListHead
        lng={lng}
        provider={provider}
        viewsOffered={viewsOffered}
        screen={screen}
        state={state}
        trash={trash}
        searchRef={searchRef}
        onAct={onAct}
        onFiles={onFiles}
      />
      {sending.now && <FileSendingLine lng={lng} now={sending.now} onStop={sending.stop} />}
      {selected.size > 0 && (
        <FileSelectionBar
          lng={lng}
          rows={rowIds}
          selected={selected}
          bulkMax={availability.limits.bulk_max_items}
          only={tickedAlone(selected, ticked)}
          inTrash={inTrash}
          onSelect={select}
          onTrash={() => void trash.trashTicked()}
          onRestore={() => void trash.restoreTicked()}
          onDeleteForever={() => void trash.deleteTicked()}
          onMove={() => onAct({ kind: 'move', items: ticked, place: listPlace })}
          onRename={item => onAct({ kind: 'rename', item })}
          onCopy={item => onAct({ kind: 'copy', item, place: listPlace })}
        />
      )}
      <FileList
        lng={lng}
        list={state.list}
        emptyKey={emptyKeyOf(searching !== null, address.view)}
        selected={selected}
        onToggle={(item, range) => toggle(item.id, range ? rowIds : undefined)}
        openFile={address.file}
        zone={user?.timezone}
        folderHref={inTrash ? address.fileHref : address.folderHref}
        fileHref={address.fileHref}
        linkRef={linkRef}
        onStar={viewsOffered && !inTrash ? star : undefined}
      />
      {standing && !address.folder && (
        <DriveFoot lng={lng} provider={provider} viewsOffered={viewsOffered} />
      )}
      {drop.dragging && (
        <div className="pointer-events-none absolute inset-2 flex items-center justify-center rounded-lg border-2 border-dashed border-primary bg-background/90 text-sm font-medium">
          {t('workbench.files.drop_here')}
        </div>
      )}
    </div>
  );
}

/** What stands above the list: the finder, the views, and what the place offers. */
function ListHead({
  lng,
  provider,
  viewsOffered,
  screen,
  state,
  trash,
  searchRef,
  onAct,
  onFiles,
}: Pick<
  FilesColumnProps,
  'lng' | 'provider' | 'viewsOffered' | 'screen' | 'state' | 'trash' | 'searchRef' | 'onAct'
> & { onFiles: (files: File[]) => void }) {
  const { t } = useTranslation(lng);
  const { address, searching, standing, inTrash } = screen;
  return (
    <>
      <FileFinder provider={provider} lng={lng} searchRef={searchRef} onSearch={screen.search} />
      {viewsOffered && (
        <FileViews lng={lng} provider={provider} view={address.view} hrefOf={address.viewHref} />
      )}
      {inTrash && (
        <div className="flex justify-end border-b px-3 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-destructive hover:text-destructive"
            onClick={() => void trash.empty()}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.empty_trash')}
          </Button>
        </div>
      )}
      {searching && (
        <SearchNotice lng={lng} provider={provider} q={searching.q} onClear={screen.clearSearch} />
      )}
      {standing && (
        <Breadcrumb
          provider={provider}
          lng={lng}
          folderId={address.folder}
          folder={state.folder.item}
          hrefOf={address.folderHref}
        />
      )}
      {standing && (
        <FolderBar
          lng={lng}
          order={screen.order}
          onOrder={screen.setOrder}
          onNewFolder={() => onAct({ kind: 'folder' })}
          onFiles={onFiles}
        />
      )}
    </>
  );
}

/** What the top of the drive adds below the list. */
function DriveFoot({
  lng,
  provider,
  viewsOffered,
}: {
  lng: Language;
  provider: string | null;
  viewsOffered: boolean;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {!viewsOffered && (
        <p className="border-t px-4 py-2 text-xs text-muted-foreground">
          {t(fileWord(provider, 'shared_drives'))}
        </p>
      )}
      <QuotaLine lng={lng} />
    </>
  );
}

/** What the account uses of its drive; nothing is said of what cannot be read. */
function QuotaLine({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { item: quota } = useWorkbenchItem<WorkbenchDriveQuota>('/workbench/files/quota', {});
  if (!quota) return null;
  const used = fileSize(quota.used, lng);
  return (
    <div className="flex items-center gap-2 border-t px-4 py-2 text-xs text-muted-foreground">
      <span className="min-w-0 flex-1 truncate">
        {quota.total === null
          ? t('workbench.files.quota_used', { used })
          : t('workbench.files.quota', { used, total: fileSize(quota.total, lng) })}
      </span>
      {quota.total !== null && (
        <progress
          className="h-1.5 w-20 shrink-0 accent-primary"
          max={quota.total}
          value={quota.used}
          aria-label={t('workbench.files.quota_label')}
        />
      )}
    </div>
  );
}

/** The drive itself, and what it keeps across its folders. */
function FileViews({
  lng,
  provider,
  view,
  hrefOf,
}: {
  lng: Language;
  provider: string | null;
  view: FileView | null;
  hrefOf: (view: FileView | null) => string;
}) {
  const { t } = useTranslation(lng);
  const link = 'whitespace-nowrap rounded-md px-2 py-1 text-xs hover:bg-muted';
  const views: readonly (FileView | null)[] = [null, ...FILE_VIEWS];
  return (
    <nav
      aria-label={t('workbench.files.views')}
      className="flex gap-1 overflow-x-auto border-b px-3 py-1.5"
    >
      {views.map(item => (
        <Link
          key={item ?? 'drive'}
          href={hrefOf(item)}
          scroll={false}
          aria-current={item === view ? 'page' : undefined}
          className={cn(link, item === view && 'bg-primary/10 font-medium')}
        >
          {item ? t(`workbench.files.view_${item}`) : t(fileWord(provider, 'my_drive'))}
        </Link>
      ))}
    </nav>
  );
}

/** What the folder offers: a new one in it, and its order, asked of the provider. */
function FolderBar({
  lng,
  order,
  onOrder,
  onNewFolder,
  onFiles,
}: {
  lng: Language;
  order: FileOrder;
  onOrder: (order: FileOrder) => void;
  onNewFolder: () => void;
  onFiles: (files: File[]) => void;
}) {
  const { t } = useTranslation(lng);
  const chooser = useRef<HTMLInputElement>(null);
  const chosen = (event: ChangeEvent<HTMLInputElement>) => {
    onFiles([...(event.target.files ?? [])]);
    // The same file chosen again is a new choice.
    event.target.value = '';
  };
  return (
    <div className="flex flex-wrap items-center gap-1 border-b px-3 py-1.5">
      <Button variant="ghost" size="sm" className="gap-1.5" onClick={onNewFolder}>
        <FolderPlus className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.new_folder')}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="gap-1.5"
        onClick={() => chooser.current?.click()}
      >
        <Upload className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.send')}
      </Button>
      <input
        ref={chooser}
        type="file"
        multiple
        hidden
        aria-label={t('workbench.files.send_files')}
        onChange={chosen}
      />
      <select
        aria-label={t('workbench.files.sort_label')}
        value={order}
        onChange={event => onOrder(FILE_ORDERS.find(item => item === event.target.value) ?? 'name')}
        className="ml-auto h-8 rounded-md border bg-background px-2 text-xs"
      >
        {FILE_ORDERS.map(item => (
          <option key={item} value={item}>
            {t(`workbench.files.sort_${item}`)}
          </option>
        ))}
      </select>
    </div>
  );
}

interface FileFinderProps {
  lng: Language;
  provider: string | null;
  searchRef: RefObject<HTMLInputElement | null>;
  onSearch: (words: string, fullText: boolean) => void;
}

/** The words, searched on Enter across the whole Drive — names, or the content too. */
function FileFinder({ lng, provider, searchRef, onSearch }: FileFinderProps) {
  const { t } = useTranslation(lng);
  const [typed, setTyped] = useState('');
  const [fullText, setFullText] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSearch(typed.trim(), fullText);
  };
  return (
    <form role="search" onSubmit={submit} className="space-y-2 border-b p-3">
      <div className="flex gap-2">
        <Input
          ref={searchRef}
          type="search"
          aria-label={t(fileWord(provider, 'search_label'))}
          placeholder={t('workbench.files.search_placeholder')}
          value={typed}
          enterKeyHint="search"
          onChange={event => setTyped(event.target.value)}
        />
        <Button
          type="submit"
          variant="outline"
          size="icon"
          aria-label={t('workbench.files.search')}
        >
          <Search className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={fullText} onChange={event => setFullText(event.target.checked)} />
        {t('workbench.files.full_text')}
      </label>
    </form>
  );
}

/** A search replaces the listing, and says so. */
function SearchNotice({
  lng,
  provider,
  q,
  onClear,
}: {
  lng: Language;
  provider: string | null;
  q: string;
  onClear: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-2 border-b px-3 py-2 text-sm"
    >
      <span className="min-w-0 truncate">{t(fileWord(provider, 'results'), { q })}</span>
      <Button variant="ghost" size="sm" className="shrink-0 gap-1" onClick={onClear}>
        <X className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.clear_search')}
      </Button>
    </div>
  );
}
