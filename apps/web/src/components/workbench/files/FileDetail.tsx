'use client';

/**
 * FileDetail — one Drive file, and what can be done with it (ADR-369).
 *
 * Its facts (changed, created, size, owners, where it lives), its downloads —
 * a Google document once per format it exports to, any other file as itself,
 * none the provider says is past the published ceiling (said instead) —
 * « Open in Drive » (Google's own page, in a new tab that cannot reach back),
 * and the trash.
 */
import { Download, ExternalLink, Trash2, X } from 'lucide-react';
import type { ReactNode, Ref } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { downloadUrl, instantLabel, isTooLarge } from '@/lib/workbench/files';
import { fileSize } from '@/lib/workbench/mail';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';

export interface FileDetailProps {
  lng: Language;
  file: WorkbenchFileDetail | undefined;
  loading: boolean;
  error: unknown;
  zone: string | undefined;
  /** The published download ceiling, in bytes. */
  maxBytes: number;
  onClose: () => void;
  onRetry: () => void;
  onTrash: () => void;
  closeRef?: Ref<HTMLButtonElement>;
}

export function FileDetail(props: FileDetailProps) {
  const { lng, file, loading, error, onClose, onRetry, closeRef } = props;
  const { t } = useTranslation(lng);
  let content: ReactNode;
  if (file) content = <DetailBody {...props} file={file} />;
  else if (loading) {
    content = (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else {
    const refusal = workbenchRefusal(error);
    content = (
      <EmptyState
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.files.read_failed')}
        action={{ label: t('workbench.states.retry'), onClick: onRetry }}
      />
    );
  }
  return (
    <article
      aria-label={file?.name || t('workbench.files.file_title')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex justify-end border-b px-2 py-1.5">
        <Button
          ref={closeRef}
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label={t('workbench.files.close_file')}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {content}
    </article>
  );
}

function DetailBody({
  lng,
  file,
  zone,
  maxBytes,
  onTrash,
}: FileDetailProps & { file: WorkbenchFileDetail }) {
  const { t } = useTranslation(lng);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <h2 className="break-words text-lg font-bold">
          {file.name || t('workbench.files.no_name')}
        </h2>
        <FileFacts lng={lng} file={file} zone={zone} />
        {file.description && (
          <p className="whitespace-pre-wrap break-words text-sm">{file.description}</p>
        )}
        <Downloads lng={lng} file={file} maxBytes={maxBytes} />
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t p-3">
        {file.web_url && (
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <a href={file.web_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              {t('workbench.files.open_in_drive')}
            </a>
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-destructive hover:text-destructive"
          onClick={onTrash}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('workbench.files.trash')}
        </Button>
      </div>
    </>
  );
}

function FileFacts({
  lng,
  file,
  zone,
}: {
  lng: Language;
  file: WorkbenchFileDetail;
  zone: string | undefined;
}) {
  const { t } = useTranslation(lng);
  const facts: [string, string | null][] = [
    [t('workbench.files.facts.modified'), instantLabel(file.modified_at, zone, lng)],
    [t('workbench.files.facts.created'), instantLabel(file.created_at, zone, lng)],
    [t('workbench.files.facts.size'), file.size === null ? null : fileSize(file.size, lng)],
    [t('workbench.files.facts.owners'), file.owners.join(', ') || null],
    [t('workbench.files.facts.location'), locationOf(file, t)],
  ];
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {facts
        .filter((fact): fact is [string, string] => fact[1] !== null)
        .map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
    </dl>
  );
}

/** Where the file lives: My Drive and its folders, or « outside My Drive ». */
function locationOf(file: WorkbenchFileDetail, t: (key: string) => string): string {
  const folders = file.ancestors.map(folder => folder.name || t('workbench.files.no_name'));
  if (!file.in_my_drive) {
    return folders.length ? ['…', ...folders].join(' › ') : t('workbench.files.outside_my_drive');
  }
  return [t('workbench.files.my_drive'), ...folders].join(' › ');
}

function Downloads({
  lng,
  file,
  maxBytes,
}: {
  lng: Language;
  file: WorkbenchFileDetail;
  maxBytes: number;
}) {
  const { t } = useTranslation(lng);
  if (!file.downloadable) {
    return <p className="text-sm text-muted-foreground">{t('workbench.files.drive_only')}</p>;
  }
  if (isTooLarge(file, maxBytes)) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('workbench.files.too_large', { max: fileSize(maxBytes, lng) })}
      </p>
    );
  }
  const offered = file.formats.length ? file.formats : [null];
  return (
    <ul className="flex flex-wrap gap-2">
      {offered.map(format => (
        <li key={format ?? 'file'}>
          <Button asChild variant="secondary" size="sm" className="gap-1.5">
            <a href={downloadUrl(file.id, format)} target="_blank" rel="noopener noreferrer">
              <Download className="h-4 w-4" aria-hidden="true" />
              {format
                ? t('workbench.files.download_as', {
                    format: t(`workbench.files.formats.${format}`),
                  })
                : t('workbench.files.download')}
            </a>
          </Button>
        </li>
      ))}
    </ul>
  );
}
