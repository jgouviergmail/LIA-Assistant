'use client';

/**
 * FilesTool — the « Tools » files screen (ADR-369, spec §6, mock-up « Fichiers »).
 *
 * My Drive and its folders open IN the list (`?folder=`, pushed, so « back »
 * goes up a level); a Drive-wide search, run on Enter, replaces the listing and
 * says so, and ends when the person opens another folder. A file opens in the
 * detail (`?file=`): opening pushes, closing replaces; below `lg` it takes the
 * list's place and the focus follows it there and back. A folder is ordered by
 * Drive, since a page sorted here would only be a page; a search keeps Drive's
 * order. A drive that keeps them has its views (`?view=`), across the folders: they
 * stand nowhere, like a search, and a search takes over from them; in the trash
 * everything opens as an item, a folder's contents being listed nowhere. Items ticked
 * go to the trash or to another folder together, each
 * answered; a folder opens nowhere else, so its rename is the one ticked alone. A
 * new folder and files sent or dropped go where the list stands, and a search stands
 * nowhere. Shared drives are not listed — the root says so.
 */
import { useRef, useState, type RefObject } from 'react';
import { toast } from 'sonner';

import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchFiles } from '@/hooks/useWorkbenchFiles';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { copyText } from '@/lib/workbench/copy';
import { parentOf } from '@/lib/workbench/files';
import { WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT } from '@/lib/workbench/tools';
import { DRIVE_ORIGIN } from '@/lib/workbench/mail-compose';
import type {
  AttachableFile,
  WorkbenchActOutcome,
  WorkbenchFileDetail,
} from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { useListSelection } from '../useListSelection';
import { useFileAssist } from '../assist/useFileAssist';
import { useToolBridges } from '../useToolBridges';
import { PANE_SEPARATOR_CLASS, useWorkbenchPane } from '../useWorkbenchPane';
import { FileDetail } from './FileDetail';
import { FileOrganizer, type FileAct, type FilePlace } from './FileOrganizer';
import { FilesColumn } from './FilesColumn';
import { useFileTrash, type FileTrash } from './useFileTrash';
import { useFilesScreen, type FilesScreen } from './useFilesScreen';
import { useToolConfirm } from '../ToolForm';

export function FilesTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'files');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="files" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="files" />
      </>
    );
  }
  return (
    <ReadyFiles
      lng={lng}
      provider={tool.provider}
      bounds={tool.bounds}
      viewsOffered={tool.features.includes('file_views')}
    />
  );
}

function ReadyFiles({
  lng,
  provider,
  bounds,
  viewsOffered,
}: {
  lng: Language;
  provider: string | null;
  bounds: Record<string, number>;
  viewsOffered: boolean;
}) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useToolConfirm();
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const screen = useFilesScreen(lng, viewsOffered);
  const { address } = screen;
  // On a large screen the person sizes the list beside the detail.
  const listPane = useWorkbenchPane(lng, 'files.list');
  const [act, setAct] = useState<FileAct | null>(null);
  const state = useWorkbenchFiles(screen.listing);
  const selection = useListSelection(JSON.stringify(screen.listing));
  const { selected, select } = selection;
  const open = useWorkbenchItem<WorkbenchFileDetail>(
    address.file ? '/workbench/files/file' : null,
    { id: address.file ?? undefined }
  );
  const searchRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const linkRef = useDrillDownFocus(address.file, {
    enabled: !desktop,
    opened: closeRef,
    fallback: searchRef,
  });
  const trash = useFileTrash({
    lng,
    provider,
    state,
    confirm,
    selected,
    select,
    openFile: address.file,
    closeFile: address.closeFile,
  });
  const moved = (outcome: WorkbenchActOutcome) =>
    select(new Set([...selected].filter(id => !outcome.done.includes(id))));

  return (
    <>
      <WorkbenchToolHeader
        lng={lng}
        tool="files"
        shortcuts={[
          {
            key: '/',
            labelKey: 'workbench.shortcuts.search',
            run: () => searchRef.current?.focus(),
          },
        ]}
        onRefresh={async options => {
          await Promise.all([
            state.list.refresh(options),
            state.folder.refresh(options),
            open.refresh(options),
          ]);
        }}
      />
      <section
        aria-label={t('workbench.tools.files.label')}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <FilesColumn
          lng={lng}
          provider={provider}
          viewsOffered={viewsOffered}
          screen={screen}
          state={state}
          selection={selection}
          trash={trash}
          pane={listPane}
          searchRef={searchRef}
          linkRef={linkRef}
          onAct={setAct}
        />
        <PaneSeparator
          {...listPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
        />
        <FilePane
          lng={lng}
          provider={provider}
          screen={screen}
          open={open}
          trash={trash}
          closeRef={closeRef}
          onAct={setAct}
          onEdited={() => {
            void open.refresh();
            void state.list.refresh();
          }}
        />
      </section>
      {confirmDialog}
      <FileOrganizer
        lng={lng}
        provider={provider}
        act={act}
        folderId={address.folder}
        nameMax={bounds.file_name_max_chars}
        state={state}
        onClose={() => setAct(null)}
        onChanged={() => {
          if (address.file) void open.refresh();
        }}
        onMoved={moved}
      />
    </>
  );
}

/** Where an open file sits: its own ancestors say it, wherever the list stands. */
function filePlaceOf(file: WorkbenchFileDetail): FilePlace {
  return { trail: file.ancestors, from: parentOf(file) };
}

/** The file opened, or what the empty side says; below `lg` it takes the list's place. */
function FilePane({
  lng,
  provider,
  screen,
  open,
  trash,
  closeRef,
  onAct,
  onEdited,
}: {
  lng: Language;
  provider: string | null;
  screen: FilesScreen;
  open: WorkbenchItemState<WorkbenchFileDetail>;
  trash: FileTrash;
  closeRef: RefObject<HTMLButtonElement | null>;
  onAct: (act: FileAct) => void;
  onEdited: () => void;
}) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { availability } = useWorkbench();
  const { ask, go, offers } = useToolBridges(lng);
  const { panel: assistPanel, ...assist } = useFileAssist(lng, open.item);
  const { address, inTrash } = screen;
  if (!address.file) {
    return (
      <div className="hidden min-w-0 flex-1 items-center justify-center lg:flex">
        <EmptyState title={t('workbench.files.pick_file')} />
      </div>
    );
  }
  const copyLink = (url: string) => {
    copyText(url).then(
      () => toast.success(t('workbench.files.link_copied')),
      () => toast.error(t('workbench.files.failed'))
    );
  };
  return (
    <div className="flex min-w-0 flex-1">
      <FileDetail
        provider={provider}
        lng={lng}
        file={open.item}
        loading={open.loading}
        error={open.error}
        zone={user?.timezone}
        maxBytes={availability.limits.download_max_bytes}
        closeRef={closeRef}
        onClose={address.closeFile}
        onRetry={() => void open.refresh()}
        inTrash={inTrash}
        onTrash={() => open.item && void trash.trashOpen(open.item)}
        onRestore={file => void trash.restoreOpen(file)}
        onDeleteForever={file => void trash.deleteOpen(file)}
        onRename={file => onAct({ kind: 'rename', item: file })}
        onMove={file => onAct({ kind: 'move', items: [file], place: filePlaceOf(file) })}
        onCopy={file => onAct({ kind: 'copy', item: file, place: filePlaceOf(file) })}
        onShare={file => onAct({ kind: 'share', item: file })}
        onMail={
          offers('compose')
            ? file => go({ kind: 'compose', to: '', file: attachableOf(file) })
            : undefined
        }
        onCopyLink={copyLink}
        onEdited={onEdited}
        onAsk={file => ask(t('workbench.ask.file', { name: file.name }))}
        assist={assist}
        assistPanel={assistPanel}
      />
    </div>
  );
}

/** A file as a new message carries it: read on the drive when the message leaves. */
function attachableOf(file: WorkbenchFileDetail): AttachableFile {
  return {
    id: file.id,
    filename: file.name,
    mime_type: file.mime_type,
    size: file.size ?? 0,
    origin: DRIVE_ORIGIN,
    expires_at: null,
  };
}
