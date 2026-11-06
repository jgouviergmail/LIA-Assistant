'use client';

/**
 * Where the files screen stands (ADR-369): the address rides the query string, a
 * search holds until the person leaves where it started, and all the rest follows
 * from those two: what the list shows, and what its place offers.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import type { FilesListing } from '@/hooks/useWorkbenchFiles';
import type { Language } from '@/i18n/settings';
import { fileViewOf, type FileOrder, type FileView } from '@/lib/workbench/files';
import { toolPath } from '@/lib/workbench/tools';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

/** A search, and the folder or the view it was started in (leaving it ends it). */
interface FilesSearch {
  q: string;
  fullText: boolean;
  from: string | null;
}

function useFilesAddress(lng: Language, viewsOffered: boolean) {
  const router = useRouter();
  const params = useSearchParams();
  const folder = params.get('folder');
  const file = params.get('file');
  const view = viewsOffered ? fileViewOf(params.get('view')) : null;
  const base = buildLocalizedPath(toolPath('files'), lng);
  const at = (place: { folder: string | null; file?: string; view?: FileView | null }) => {
    const query = new URLSearchParams();
    if (place.view) query.set('view', place.view);
    if (place.folder) query.set('folder', place.folder);
    if (place.file) query.set('file', place.file);
    const search = query.toString();
    return search ? `${base}?${search}` : base;
  };
  return {
    folder,
    file,
    view,
    folderHref: (folderId: string | null) => at({ folder: folderId }),
    viewHref: (item: FileView | null) => at({ folder: null, view: item }),
    fileHref: (fileId: string) => at({ folder, file: fileId, view }),
    closeFile: () => router.replace(at({ folder, view }), { scroll: false }),
  };
}

/** What the list shows: a search first, then a view, else the folder. */
function listingOf(
  searching: FilesSearch | null,
  view: FileView | null,
  folderId: string | null,
  order: FileOrder
): FilesListing {
  if (searching) return { kind: 'search', q: searching.q, fullText: searching.fullText };
  return view ? { kind: 'view', view } : { kind: 'folder', folderId, order };
}

export type FilesScreen = ReturnType<typeof useFilesScreen>;

export function useFilesScreen(lng: Language, viewsOffered: boolean) {
  const address = useFilesAddress(lng, viewsOffered);
  const [search, setSearch] = useState<FilesSearch | null>(null);
  const [order, setOrder] = useState<FileOrder>('name');
  const place = address.view ?? address.folder;
  const searching = search !== null && search.from === place ? search : null;
  return {
    address,
    searching,
    order,
    setOrder,
    /** The list stands in a folder: what is new goes there. */
    standing: searching === null && address.view === null,
    // A search takes over the view: what it finds is alive, whatever view it started from.
    inTrash: address.view === 'trash' && searching === null,
    listing: listingOf(searching, address.view, address.folder, order),
    search: (q: string, fullText: boolean) => setSearch(q ? { q, fullText, from: place } : null),
    clearSearch: () => setSearch(null),
  };
}
