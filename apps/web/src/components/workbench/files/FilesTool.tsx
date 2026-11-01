'use client';

/**
 * FilesTool — the « Tools » files screen (ADR-369, spec §6, mock-up « Fichiers »).
 *
 * My Drive and its folders open IN the list (`?folder=`, pushed, so « back »
 * goes up a level); a Drive-wide search, run on Enter, replaces the listing and
 * says so, and ends when the person opens another folder. A file opens in the
 * detail (`?file=`): opening pushes, closing replaces; below `lg` it takes the
 * list's place and the focus follows it there and back. Shared drives are not
 * listed — the root says so.
 */
import { Search, X } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRef, useState, type FormEvent, type RefObject } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { Input } from '@/components/ui/input';
import { useConfirm } from '@/components/ui/use-confirm';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchFiles, type FilesListing } from '@/hooks/useWorkbenchFiles';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { toolPath, WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT } from '@/lib/workbench/tools';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { Breadcrumb } from './Breadcrumb';
import { FileDetail } from './FileDetail';
import { FileList } from './FileList';

/** A search, and the folder it was started in (opening another one ends it). */
interface FilesSearch {
  q: string;
  fullText: boolean;
  from: string | null;
}

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
  return <ReadyFiles lng={lng} />;
}

function useFilesAddress(lng: Language) {
  const router = useRouter();
  const params = useSearchParams();
  const folder = params.get('folder');
  const file = params.get('file');
  const base = buildLocalizedPath(toolPath('files'), lng);
  const at = (place: { folder: string | null; file?: string }) => {
    const query = new URLSearchParams();
    if (place.folder) query.set('folder', place.folder);
    if (place.file) query.set('file', place.file);
    const search = query.toString();
    return search ? `${base}?${search}` : base;
  };
  return {
    folder,
    file,
    folderHref: (folderId: string | null) => at({ folder: folderId }),
    fileHref: (fileId: string) => at({ folder, file: fileId }),
    closeFile: () => router.replace(at({ folder }), { scroll: false }),
  };
}

function ReadyFiles({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { availability } = useWorkbench();
  const { confirm, confirmDialog } = useConfirm();
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const address = useFilesAddress(lng);
  // On a large screen the person sizes the list beside the detail.
  const listPane = useWorkbenchPane(lng, 'files.list');
  const [search, setSearch] = useState<FilesSearch | null>(null);
  const searching = search !== null && search.from === address.folder ? search : null;
  const listing: FilesListing = searching
    ? { kind: 'search', q: searching.q, fullText: searching.fullText }
    : { kind: 'folder', folderId: address.folder };
  const state = useWorkbenchFiles(listing);
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

  const trash = async (file: WorkbenchFileDetail) => {
    const confirmed = await confirm({
      title: t('workbench.files.trash_title', { name: file.name || t('workbench.files.no_name') }),
      description: t('workbench.files.trash_description'),
      confirmLabel: t('workbench.files.trash'),
    });
    if (!confirmed) return;
    try {
      const outcome = await state.trash([file.id]);
      if (outcome?.done.includes(file.id)) {
        address.closeFile();
        toast.success(t('workbench.files.trashed'));
      } else toast.error(t('workbench.files.failed'));
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
    }
  };

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="files" />
      <section
        aria-label={t('workbench.tools.files.label')}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <div
          {...listPane.pane}
          className={cn(
            'min-w-0 flex-col lg:border-r',
            paneWidth(listPane, 'lg:w-[26rem] lg:flex-none'),
            address.file ? 'hidden lg:flex' : 'flex flex-1'
          )}
        >
          <FileFinder
            lng={lng}
            searchRef={searchRef}
            onSearch={(q, fullText) => setSearch(q ? { q, fullText, from: address.folder } : null)}
          />
          {searching ? (
            <SearchNotice lng={lng} q={searching.q} onClear={() => setSearch(null)} />
          ) : (
            <Breadcrumb
              lng={lng}
              folderId={address.folder}
              folder={state.folder.item}
              hrefOf={address.folderHref}
            />
          )}
          <FileList
            lng={lng}
            list={state.list}
            searching={searching !== null}
            openFile={address.file}
            zone={user?.timezone}
            folderHref={address.folderHref}
            fileHref={address.fileHref}
            linkRef={linkRef}
          />
          {!searching && !address.folder && (
            <p className="border-t px-4 py-2 text-xs text-muted-foreground">
              {t('workbench.files.shared_drives')}
            </p>
          )}
        </div>
        <PaneSeparator
          {...listPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
        />
        {address.file ? (
          <div className="flex min-w-0 flex-1">
            <FileDetail
              lng={lng}
              file={open.item}
              loading={open.loading}
              error={open.error}
              zone={user?.timezone}
              maxBytes={availability.limits.download_max_bytes}
              closeRef={closeRef}
              onClose={address.closeFile}
              onRetry={() => void open.refresh()}
              onTrash={() => open.item && void trash(open.item)}
            />
          </div>
        ) : (
          <div className="hidden min-w-0 flex-1 items-center justify-center lg:flex">
            <EmptyState title={t('workbench.files.pick_file')} />
          </div>
        )}
      </section>
      {confirmDialog}
    </>
  );
}

interface FileFinderProps {
  lng: Language;
  searchRef: RefObject<HTMLInputElement | null>;
  onSearch: (words: string, fullText: boolean) => void;
}

/** The words, searched on Enter across the whole Drive — names, or the content too. */
function FileFinder({ lng, searchRef, onSearch }: FileFinderProps) {
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
          aria-label={t('workbench.files.search_label')}
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
function SearchNotice({ lng, q, onClear }: { lng: Language; q: string; onClear: () => void }) {
  const { t } = useTranslation(lng);
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-2 border-b px-3 py-2 text-sm"
    >
      <span className="min-w-0 truncate">{t('workbench.files.results', { q })}</span>
      <Button variant="ghost" size="sm" className="shrink-0 gap-1" onClick={onClear}>
        <X className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.clear_search')}
      </Button>
    </div>
  );
}
