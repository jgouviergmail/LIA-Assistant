'use client';

/**
 * FileDetail — one Drive file, and what can be done with it (ADR-369).
 *
 * What can be seen of it, its facts (changed, created, size, owners, where it lives),
 * its downloads —
 * a Google document once per format it exports to, any other file as itself,
 * none the provider says is past the published ceiling (said instead) —
 * « Open in Drive » (the drive's own page, in a new tab that cannot reach back: where an
 * Office file or a Google document is changed), its words changed here when it is a text
 * held whole, its link to copy, what organises it (renamed, moved, copied), and the trash.
 * In the trash it comes back or leaves for good, and nothing else is offered.
 */
import {
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  FilePenLine,
  FolderInput,
  Link2,
  Mail,
  Pencil,
  RotateCcw,
  Share2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useState, type ReactNode, type Ref } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/ui/empty-state';
import { LinkedText } from '@/components/ui/linked-text';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { downloadUrl, instantLabel, isTooLarge } from '@/lib/workbench/files';
import { fileWord } from '@/lib/workbench/files-words';
import { fileSize } from '@/lib/workbench/mail';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';

import { DetailClose } from '../DetailClose';
import { FilePreview } from './FilePreview';
import { FileTextEditor } from './FileTextEditor';

export interface FileDetailProps {
  /** The connector serving the tool: the drive is named after it. */
  provider?: string | null;
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
  /** The file sits in the drive's trash. */
  inTrash: boolean;
  onRestore: (file: WorkbenchFileDetail) => void;
  onDeleteForever: (file: WorkbenchFileDetail) => void;
  onRename: (file: WorkbenchFileDetail) => void;
  onMove: (file: WorkbenchFileDetail) => void;
  onCopy: (file: WorkbenchFileDetail) => void;
  onShare: (file: WorkbenchFileDetail) => void;
  /** Takes the file to a new message, where a mailbox is ready. */
  onMail?: (file: WorkbenchFileDetail) => void;
  /** Copies the file's link. */
  onCopyLink: (url: string) => void;
  /** Takes the file to LIA. */
  onAsk: (file: WorkbenchFileDetail) => void;
  /** Its words were changed here. */
  onEdited: () => void;
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
      <div className="flex items-center border-b px-2 py-1.5">
        <DetailClose
          closeLabel={t('workbench.files.close_file')}
          backLabel={t('workbench.tools.files.label')}
          onClose={onClose}
          buttonRef={closeRef}
        />
      </div>
      {content}
    </article>
  );
}

function TrashActions({
  lng,
  file,
  onRestore,
  onDeleteForever,
}: Pick<FileDetailProps, 'lng' | 'onRestore' | 'onDeleteForever'> & {
  file: WorkbenchFileDetail;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex flex-wrap justify-end gap-2 border-t p-3">
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => onRestore(file)}>
        <RotateCcw className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.restore')}
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 text-destructive hover:text-destructive"
        onClick={() => onDeleteForever(file)}
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
        {t('workbench.files.delete_forever')}
      </Button>
    </div>
  );
}

function DetailBody(props: FileDetailProps & { file: WorkbenchFileDetail }) {
  const { lng, provider, file, zone, maxBytes, inTrash, onRestore, onDeleteForever } = props;
  const { t } = useTranslation(lng);
  const [editing, setEditing] = useState(false);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <h2 className="break-words text-lg font-bold">
          {file.name || t('workbench.files.no_name')}
        </h2>
        <FilePreview key={`${file.id}:${file.modified_at}`} lng={lng} file={file} />
        <FileFacts lng={lng} provider={provider} file={file} zone={zone} />
        {file.description && (
          <p className="whitespace-pre-wrap break-words text-sm">
            <LinkedText text={file.description} />
          </p>
        )}
        <Downloads lng={lng} provider={provider} file={file} maxBytes={maxBytes} />
      </div>
      {inTrash ? (
        <TrashActions
          lng={lng}
          file={file}
          onRestore={onRestore}
          onDeleteForever={onDeleteForever}
        />
      ) : (
        <LiveActions {...props} onEdit={() => setEditing(true)} />
      )}
      {editing && (
        <FileTextEditor
          lng={lng}
          file={file}
          onClose={() => setEditing(false)}
          onSaved={props.onEdited}
        />
      )}
    </>
  );
}

function LiveActions({
  lng,
  provider,
  file,
  onTrash,
  onRename,
  onMove,
  onCopy,
  onShare,
  onMail,
  maxBytes,
  onCopyLink,
  onAsk,
  onEdit,
}: FileDetailProps & { file: WorkbenchFileDetail; onEdit: () => void }) {
  const { t } = useTranslation(lng);
  const leaves = file.downloadable && !isTooLarge(file, maxBytes);
  return (
    <div className="flex flex-wrap justify-end gap-2 border-t p-3">
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => onAsk(file)}>
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        {t('workbench.ask.label')}
      </Button>
      {file.editable && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}>
          <FilePenLine className="h-4 w-4" aria-hidden="true" />
          {t('workbench.files.edit_text')}
        </Button>
      )}
      {file.web_url && (
        <>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => file.web_url && onCopyLink(file.web_url)}
          >
            <Link2 className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.copy_link')}
          </Button>
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <a href={file.web_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              {t(fileWord(provider, 'open_in_drive'))}
            </a>
          </Button>
        </>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            {t('workbench.files.organise')}
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => onRename(file)}>
            <Pencil className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('workbench.files.rename')}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => onMove(file)}>
            <FolderInput className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('workbench.files.move')}
          </DropdownMenuItem>
          {file.kind === 'file' && (
            <DropdownMenuItem onSelect={() => onCopy(file)}>
              <Copy className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('workbench.files.copy')}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={() => onShare(file)}>
            <Share2 className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('workbench.files.share')}
          </DropdownMenuItem>
          {onMail && leaves && (
            <DropdownMenuItem onSelect={() => onMail(file)}>
              <Mail className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('workbench.files.send_by_mail')}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
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
  );
}

function FileFacts({
  lng,
  provider,
  file,
  zone,
}: {
  lng: Language;
  provider?: string | null;
  file: WorkbenchFileDetail;
  zone: string | undefined;
}) {
  const { t } = useTranslation(lng);
  const facts: [string, string | null][] = [
    [t('workbench.files.facts.modified'), instantLabel(file.modified_at, zone, lng)],
    [t('workbench.files.facts.created'), instantLabel(file.created_at, zone, lng)],
    [t('workbench.files.facts.size'), file.size === null ? null : fileSize(file.size, lng)],
    [t('workbench.files.facts.owners'), file.owners.join(', ') || null],
    [t('workbench.files.facts.location'), locationOf(file, t, provider)],
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
function locationOf(
  file: WorkbenchFileDetail,
  t: (key: string) => string,
  provider: string | null | undefined
): string {
  const folders = file.ancestors.map(folder => folder.name || t('workbench.files.no_name'));
  if (!file.in_my_drive) {
    return folders.length
      ? ['…', ...folders].join(' › ')
      : t(fileWord(provider, 'outside_my_drive'));
  }
  return [t(fileWord(provider, 'my_drive')), ...folders].join(' › ');
}

function Downloads({
  lng,
  provider,
  file,
  maxBytes,
}: {
  lng: Language;
  provider?: string | null;
  file: WorkbenchFileDetail;
  maxBytes: number;
}) {
  const { t } = useTranslation(lng);
  if (!file.downloadable) {
    return <p className="text-sm text-muted-foreground">{t(fileWord(provider, 'drive_only'))}</p>;
  }
  if (isTooLarge(file, maxBytes)) {
    return (
      <p className="text-sm text-muted-foreground">
        {t(fileWord(provider, 'too_large'), { max: fileSize(maxBytes, lng) })}
      </p>
    );
  }
  const offered = file.formats.length ? file.formats : [null];
  return (
    <ul className="flex flex-wrap gap-2">
      {offered.map(format => (
        <li key={format ?? 'file'}>
          <Button asChild variant="outline" size="sm" className="gap-1.5">
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
