'use client';

import { useEffect, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import { apiEndpointUrl } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const copy = 'settings.application_tools';

const downloads: Readonly<Record<string, { title: string; endpoint: string }>> = {
  'meeting_report.download': { title: 'meeting_pdf_download_title', endpoint: 'meeting-pdf' },
  'account_export.download': { title: 'download_title', endpoint: 'download' },
  'interests.export': { title: 'interests_download_title', endpoint: 'management-export' },
  'memories.export': { title: 'memories_download_title', endpoint: 'management-export' },
  'journals.export': { title: 'journals_download_title', endpoint: 'management-export' },
  'generated_asset.download': {
    title: 'asset_download_title',
    endpoint: 'asset-download',
  },
  'saved_answer.download': {
    title: 'bookmark_download_title',
    endpoint: 'bookmark-download',
  },
  'skill_settings.download': { title: 'skill_download_title', endpoint: 'skill-download' },
  'knowledge_document.download': {
    title: 'document_download_title',
    endpoint: 'document-download',
  },
  'knowledge_documents.archive': {
    title: 'document_archive_title',
    endpoint: 'document-archive',
  },
};

export const applicationExportTitles: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(downloads).map(([operation, action]) => [operation, action.title])
);

interface Props {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
}

function downloadMessage(
  status: ApplicationCommandStatus,
  expired: boolean,
  waiting: boolean,
  attempted: boolean
): string {
  if (status.phase === 'committed') return 'download_requested';
  if (expired || status.phase === 'expired') return 'secure_expired';
  if (!waiting) return 'secure_failed';
  return attempted ? 'download_attempted' : 'download_waiting';
}

/** A single approved browser request does not attest that a file was saved. */
export function ApplicationExportDownloadCard({ status, checkResult, readError }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const accountExport = status.operation_id === 'account_export.download';
  const download = downloads[status.operation_id];
  const title = download?.title ?? 'download_title';
  const endpoint = download?.endpoint ?? 'download';
  const transferTarget = useId();
  const scopeKey = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { isCurrent } = useApplicationAccountLifetime(scopeKey);
  const [attempted, setAttempted] = useApplicationAccountState(scopeKey, false);
  const expired = useApplicationCommandDeadline(status.expires_at, scopeKey);
  const waiting =
    Boolean(download) &&
    status.phase === 'waiting' &&
    status.interaction?.kind === 'device' &&
    !expired;
  useEffect(() => {
    if (accountExport && isCurrent() && user?.id && status.outcome?.committed) {
      publishApplicationResources(user.id, new Set(['account_export']));
    }
  }, [isCurrent, accountExport, status.outcome?.committed, user?.id]);
  const message = downloadMessage(status, expired, waiting, attempted);
  return (
    <section
      data-application-action-priority={waiting}
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.${title}`)}
    >
      <h3 className="flex items-start gap-2 text-sm font-medium">
        <Download className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${copy}.${title}`)}
      </h3>
      <p className="mt-1 break-words text-sm text-muted-foreground" role="status">
        {t(`${copy}.${message}`)}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {waiting && (
          <Button size="sm" asChild>
            <a
              href={apiEndpointUrl(
                `/application-commands/${encodeURIComponent(status.command_id)}/${endpoint}`
              )}
              target={transferTarget}
              aria-disabled={attempted}
              onClick={event => {
                if (
                  !isCurrent() ||
                  attempted ||
                  new Date(status.expires_at).getTime() <= Date.now()
                ) {
                  event.preventDefault();
                  return;
                }
                setAttempted(true);
              }}
            >
              {t(`${copy}.download_start`)}
            </a>
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            if (isCurrent()) void checkResult();
          }}
        >
          {t(`${copy}.secure_check`)}
        </Button>
      </div>
      {/* A failed attachment stays here; no script or top-level navigation is allowed. */}
      <iframe
        name={transferTarget}
        title={t(`${copy}.${title}`)}
        hidden
        sandbox="allow-downloads allow-same-origin"
      />
      {readError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {t(`${copy}.secure_read_failed`)}
        </p>
      )}
    </section>
  );
}
