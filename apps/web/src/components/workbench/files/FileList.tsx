'use client';

/**
 * FileList — a folder's items, or a search's (ADR-369, mock-up « Fichiers »).
 *
 * Folders first, as Drive orders them. A folder opens in the list, a file in
 * the detail, a shortcut what it points at; a shortcut whose target the person
 * can no longer see is listed and says so. An empty folder and a search that
 * found nothing are told apart.
 */
import { ArrowUpRight, FileText, Folder } from 'lucide-react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { fileOf, folderOf } from '@/lib/workbench/files';
import { fileSize, receivedLabel } from '@/lib/workbench/mail';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

export interface FileListProps {
  lng: Language;
  list: WorkbenchPageState<WorkbenchDriveItem>;
  searching: boolean;
  openFile: string | null;
  zone: string | undefined;
  folderHref: (folderId: string) => string;
  fileHref: (fileId: string) => string;
  linkRef: (id: string, element: HTMLElement | null) => void;
}

export function FileList(props: FileListProps) {
  const { lng, list, searching } = props;
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
  if (list.items.length === 0) {
    return (
      <EmptyState
        className="flex-1"
        icon={Folder}
        description={t(searching ? 'workbench.files.empty_search' : 'workbench.files.empty_folder')}
      />
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <ul>
        {list.items.map(item => (
          <li key={item.id}>
            <FileRow {...props} item={item} />
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
  'flex items-center gap-3 border-b px-4 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring';

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
      className={`${ROW} hover:bg-muted aria-[current=true]:bg-primary/10`}
    >
      {body}
    </Link>
  );
}

function ItemIcon({ item }: { item: WorkbenchDriveItem }) {
  const Icon = item.kind === 'folder' || item.target_kind === 'folder' ? Folder : FileText;
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
