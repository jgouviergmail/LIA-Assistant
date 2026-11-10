'use client';

/**
 * FileList — a folder's items, or a search's (ADR-369, mock-up « Fichiers »).
 *
 * Folders first, in the order Drive was asked for; each item's icon says what it
 * is. A folder opens in the list, a file in the detail, a shortcut what it points
 * at; a shortcut whose target the person can no longer see is listed and says so.
 * An empty folder, an empty view and a search that found nothing are told apart.
 * Each item has its box for an act on several, and its star on a drive that keeps
 * them.
 */
import {
  ArrowUpRight,
  File,
  FileArchive,
  FileAudio,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Folder,
  Presentation,
  Star,
  type LucideIcon,
} from '@/lib/icons';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { fileKind, fileOf, folderOf, type FileKind } from '@/lib/workbench/files';
import { fileSize, receivedLabel } from '@/lib/workbench/mail';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

/** Each kind's icon: completeness enforced by the type. */
const KIND_ICONS: Readonly<Record<FileKind, LucideIcon>> = {
  folder: Folder,
  document: FileText,
  spreadsheet: FileSpreadsheet,
  presentation: Presentation,
  pdf: FileText,
  image: FileImage,
  audio: FileAudio,
  video: FileVideo,
  archive: FileArchive,
  file: File,
};

export interface FileListProps {
  lng: Language;
  list: WorkbenchPageState<WorkbenchDriveItem>;
  /** What an empty list says. */
  emptyKey: string;
  selected: ReadonlySet<string>;
  /** @param range - Shift was held: a range, not one item. */
  onToggle: (item: WorkbenchDriveItem, range: boolean) => void;
  openFile: string | null;
  zone: string | undefined;
  folderHref: (folderId: string) => string;
  fileHref: (fileId: string) => string;
  linkRef: (id: string, element: HTMLElement | null) => void;
  /** Sets an item's star, on a drive that keeps them. */
  onStar?: (item: WorkbenchDriveItem) => void;
}

export function FileList(props: FileListProps) {
  const { lng, list, emptyKey, onStar } = props;
  const { t } = useTranslation(lng);
  if (list.loading) {
    return (
      <div className="space-y-2 p-3" aria-busy="true">
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-full" />
      </div>
    );
  }
  if (list.error) {
    const refusal = workbenchRefusal(list.error);
    return (
      <EmptyState
        className="flex-1"
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void list.refresh() }}
      />
    );
  }
  // A page may come back empty with more to read: a trash that lists fewer than it read.
  if (list.items.length === 0 && !list.nextToken) {
    return <EmptyState className="flex-1" icon={Folder} description={t(emptyKey)} />;
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <ul>
        {list.items.map(item => (
          <li
            key={item.id}
            className="flex items-center border-b hover:bg-muted has-[[aria-current=true]]:bg-primary/10"
          >
            <Checkbox
              checked={props.selected.has(item.id)}
              onChange={event => props.onToggle(item, shifted(event.nativeEvent))}
              aria-label={t('workbench.files.select_item', {
                name: item.name || t('workbench.files.no_name'),
              })}
              className="ml-4"
            />
            <FileRow {...props} item={item} />
            {onStar && <StarButton lng={lng} item={item} onStar={onStar} />}
          </li>
        ))}
      </ul>
      {list.nextToken && (
        <div className="p-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            isLoading={list.loadingMore}
            onClick={() => void list.loadMore()}
          >
            {t('workbench.files.more')}
          </Button>
        </div>
      )}
    </div>
  );
}

const ROW =
  'flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring';

/** Whether Shift was held: a checkbox's change comes from its click. */
function shifted(event: Event): boolean {
  return event instanceof MouseEvent && event.shiftKey;
}

function FileRow({
  lng,
  item,
  openFile,
  zone,
  folderHref,
  fileHref,
  linkRef,
}: FileListProps & { item: WorkbenchDriveItem }) {
  const { t } = useTranslation(lng);
  const folder = folderOf(item);
  const file = fileOf(item);
  const meta = [
    receivedLabel(item.modified_at, new Date(), zone, lng),
    item.size === null ? null : fileSize(item.size, lng),
  ].filter(Boolean);
  const body = (
    <>
      <ItemIcon item={item} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">
          {item.name || t('workbench.files.no_name')}
          {item.kind === 'shortcut' && (
            <span className="sr-only"> ({t('workbench.files.shortcut')})</span>
          )}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {folder || file ? meta.join(' · ') : t('workbench.files.shortcut_gone')}
        </span>
      </span>
    </>
  );
  const target = folder ?? file;
  if (!target) return <div className={`${ROW} opacity-70`}>{body}</div>;
  return (
    <Link
      ref={element => linkRef(target, element)}
      href={folder ? folderHref(folder) : fileHref(target)}
      scroll={false}
      aria-current={file !== null && file === openFile ? 'true' : undefined}
      className={ROW}
    >
      {body}
    </Link>
  );
}

function StarButton({
  lng,
  item,
  onStar,
}: {
  lng: Language;
  item: WorkbenchDriveItem;
  onStar: (item: WorkbenchDriveItem) => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <Button
      variant="ghost"
      size="icon"
      className="mr-1 shrink-0"
      aria-pressed={item.starred}
      aria-label={t(item.starred ? 'workbench.files.unstar' : 'workbench.files.star')}
      onClick={() => onStar(item)}
    >
      <Star
        className={item.starred ? 'h-4 w-4 fill-current text-primary' : 'h-4 w-4'}
        aria-hidden="true"
      />
    </Button>
  );
}

function ItemIcon({ item }: { item: WorkbenchDriveItem }) {
  const Icon = KIND_ICONS[fileKind(item)];
  return (
    <span className="relative shrink-0">
      <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
      {item.kind === 'shortcut' && (
        <ArrowUpRight
          className="absolute -bottom-1 -right-1 h-3 w-3 rounded-full bg-card text-foreground"
          aria-hidden="true"
        />
      )}
    </span>
  );
}
