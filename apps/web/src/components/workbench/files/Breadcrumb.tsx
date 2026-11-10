'use client';

/**
 * Breadcrumb — where the open folder lives, from My Drive down (ADR-369).
 *
 * The folders come from the open folder's own detail: the API walked them up to
 * My Drive under a bounded depth. When the walk stopped short, or the folder
 * lives outside My Drive (shared with the person), the gap is drawn « … » and
 * named for a screen reader — never a path invented to fill it.
 */
import { ChevronRight } from '@/lib/icons';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { fileWord } from '@/lib/workbench/files-words';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';

export interface BreadcrumbProps {
  lng: Language;
  /** The connector serving the tool: the top of the drive is named after it. */
  provider?: string | null;
  /** The open folder; null at My Drive. */
  folderId: string | null;
  /** Its detail, once read. */
  folder: WorkbenchFileDetail | undefined;
  hrefOf: (folderId: string | null) => string;
}

export function Breadcrumb({ lng, provider, folderId, folder, hrefOf }: BreadcrumbProps) {
  const { t } = useTranslation(lng);
  const crumbs: ReactNode[] = [];
  if (folder && (folder.ancestors_truncated || !folder.in_my_drive)) {
    crumbs.push(
      <span key="gap" title={t('workbench.files.hidden_folders')}>
        <span aria-hidden="true">…</span>
        <span className="sr-only">{t('workbench.files.hidden_folders')}</span>
      </span>
    );
  }
  for (const ancestor of folder?.ancestors ?? []) {
    crumbs.push(
      <Link key={ancestor.id} href={hrefOf(ancestor.id)} className={LINK}>
        {ancestor.name || t('workbench.files.no_name')}
      </Link>
    );
  }
  if (folderId) {
    crumbs.push(
      folder ? (
        <span key="here" aria-current="page" className="truncate font-medium text-foreground">
          {folder.name || t('workbench.files.no_name')}
        </span>
      ) : (
        <Skeleton key="here" className="h-4 w-24" />
      )
    );
  }
  return (
    <nav aria-label={t('workbench.files.breadcrumb')} className="border-b px-3 py-2">
      <ol className="flex min-w-0 flex-wrap items-center gap-1 text-sm text-muted-foreground">
        <li className="min-w-0">
          {folderId ? (
            <Link href={hrefOf(null)} className={LINK}>
              {t(fileWord(provider, 'my_drive'))}
            </Link>
          ) : (
            <span aria-current="page" className="font-medium text-foreground">
              {t(fileWord(provider, 'my_drive'))}
            </span>
          )}
        </li>
        {crumbs.map((crumb, index) => (
          <li key={index} className="flex min-w-0 items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {crumb}
          </li>
        ))}
      </ol>
    </nav>
  );
}

const LINK =
  'truncate rounded-sm text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
