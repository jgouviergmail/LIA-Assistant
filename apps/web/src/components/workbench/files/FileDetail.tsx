'use client';

/**
 * FileDetail — one Drive file, and what can be done with it (ADR-369).
 *
 * What can be seen of it, its facts (changed, created, size, owners, where it lives),
 * its downloads —
 * a Google document once per format it exports to, any other file as itself,
 * none the provider says is past the published ceiling (said instead) —
 * « Open » (the drive's own page, in a new tab that cannot reach back: where an Office file or
 * a Google document is changed), its link to copy, what sends it elsewhere (moved, shared, mailed),
 * the trash and the question to LIA stand in its bar; behind « … », its words changed here when it
 * is a text held whole, its new name and its copy.
 * In the trash it comes back or leaves for good, and nothing else is offered.
 */
import {
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
  Trash2,
} from 'lucide-react';
import { useState, type ReactNode, type Ref } from 'react';

import { Button } from '@/components/ui/button';
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

import { actIf, askAct, DetailBar, type AssistOffer, type DetailAct } from '../DetailBar';
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
  /** What LIA can do on it, under the question's icon. */
  assist?: AssistOffer;
  /** What LIA answered, above what the file shows. */
  assistPanel?: ReactNode;
  /** Its words were changed here. */
  onEdited: () => void;
  closeRef?: Ref<HTMLButtonElement>;
}

export function FileDetail(props: FileDetailProps) {
  const { lng, file, loading, error, onClose, onRetry, closeRef, inTrash } = props;
  const { t } = useTranslation(lng);
  const [editing, setEditing] = useState(false);
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
      <DetailBar
        lng={lng}
        closeLabel={t('workbench.files.close_file')}
        backLabel={t('workbench.tools.files.label')}
        onClose={onClose}
        closeRef={closeRef}
        acts={
          file &&
          (inTrash ? trashActs(props, file, t) : liveActs(props, file, () => setEditing(true), t))
        }
      />
      {content}
      {editing && file && (
        <FileTextEditor
          lng={lng}
          file={file}
          onClose={() => setEditing(false)}
          onSaved={props.onEdited}
        />
      )}
    </article>
  );
}

type Say = (key: string) => string;

/** What a file in the trash offers: it comes back or leaves for good. */
function trashActs(
  { onRestore, onDeleteForever }: FileDetailProps,
  file: WorkbenchFileDetail,
  t: Say
): readonly DetailAct[] {
  return [
    {
      label: t('workbench.files.restore'),
      icon: RotateCcw,
      onSelect: () => onRestore(file),
    },
    {
      label: t('workbench.files.delete_forever'),
      icon: Trash2,
      danger: true,
      onSelect: () => onDeleteForever(file),
    },
  ];
}

/** What a live file offers: what organises it in place waits behind « … », the rest in the bar. */
function liveActs(
  props: FileDetailProps,
  file: WorkbenchFileDetail,
  onEdit: () => void,
  t: Say
): readonly DetailAct[] {
  const { provider, maxBytes, onTrash, onRename, onMove, onCopy, onShare, onMail } = props;
  const { onCopyLink, onAsk, assist } = props;
  const link = file.web_url;
  const leaves = file.downloadable && !isTooLarge(file, maxBytes);
  return [
    ...actIf(Boolean(link), {
      label: t(fileWord(provider, 'open_in_drive')),
      icon: ExternalLink,
      href: link ?? undefined,
      external: true,
    }),
    ...actIf(Boolean(link), {
      label: t('workbench.files.copy_link'),
      icon: Link2,
      onSelect: () => link && onCopyLink(link),
    }),
    { label: t('workbench.files.move'), icon: FolderInput, onSelect: () => onMove(file) },
    { label: t('workbench.files.share'), icon: Share2, onSelect: () => onShare(file) },
    ...actIf(Boolean(onMail) && leaves, {
      label: t('workbench.files.send_by_mail'),
      icon: Mail,
      onSelect: () => onMail?.(file),
    }),
    ...actIf(file.editable, {
      label: t('workbench.files.edit_text'),
      icon: FilePenLine,
      more: true,
      onSelect: onEdit,
    }),
    {
      label: t('workbench.files.rename'),
      icon: Pencil,
      more: true,
      onSelect: () => onRename(file),
    },
    ...actIf(file.kind === 'file', {
      label: t('workbench.files.copy'),
      icon: Copy,
      more: true,
      onSelect: () => onCopy(file),
    }),
    { label: t('workbench.files.trash'), icon: Trash2, danger: true, onSelect: onTrash },
    askAct(t('workbench.ask.label'), () => onAsk(file), assist),
  ];
}

function DetailBody({
  lng,
  provider,
  file,
  zone,
  maxBytes,
  assistPanel,
}: FileDetailProps & { file: WorkbenchFileDetail }) {
  const { t } = useTranslation(lng);
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <h2 className="break-words text-lg font-bold">{file.name || t('workbench.files.no_name')}</h2>
      {assistPanel}
      <FilePreview key={`${file.id}:${file.modified_at}`} lng={lng} file={file} />
      <FileFacts lng={lng} provider={provider} file={file} zone={zone} />
      {file.description && (
        <p className="whitespace-pre-wrap break-words text-sm">
          <LinkedText text={file.description} />
        </p>
      )}
      <Downloads lng={lng} provider={provider} file={file} maxBytes={maxBytes} />
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
