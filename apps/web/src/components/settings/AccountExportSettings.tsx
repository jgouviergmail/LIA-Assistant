'use client';

import { useCallback, useState } from 'react';
import { DownloadCloud } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import apiClient, { ApiError, ApiStepUpError, apiEndpointUrl } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { formatFileSize } from '@/lib/format';
import { formatInstant } from '@/lib/format-instant';
import { lifecycleTone } from '@/lib/status-tone';
import { logger } from '@/lib/logger';

interface ExportJob {
  id: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'expired';
  error_code: string | null;
  file_size_bytes: number | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
  download_available: boolean;
}

/**
 * Status badge + the detail each state owes the reader (owner arbitration
 * 2026-08-05: a bare "Expired" chip said nothing — when, and what now?).
 * The badge takes its tone from the shared lifecycle table: done is green,
 * running is blue, expired is grey — grey being reserved for the inactive.
 */
function ExportJobStatus({ job, locale }: { job: ExportJob | null | undefined; locale: string }) {
  const { t } = useTranslation();
  if (!job) return null;
  return (
    <div className="space-y-1.5">
      <Badge variant={lifecycleTone(job.status)} className="text-px-10">
        {t(`settings.security.export.status_${job.status}`)}
      </Badge>
      {job.status === 'done' && (
        <p className="text-xs text-muted-foreground">
          {job.download_available
            ? t('settings.security.export.ready_hint', {
                size: job.file_size_bytes != null ? formatFileSize(job.file_size_bytes) : '—',
                date: job.expires_at ? formatInstant(job.expires_at, locale) : '—',
              })
            : t('settings.security.export.archive_unavailable')}
        </p>
      )}
      {job.status === 'expired' && (
        <p className="text-xs text-muted-foreground">
          {t('settings.security.export.expired_hint', {
            created: formatInstant(job.created_at, locale, 'short'),
            expired: job.expires_at ? formatInstant(job.expires_at, locale, 'short') : '—',
          })}
        </p>
      )}
      {job.status === 'failed' && (
        <p className="text-xs text-destructive">
          {job.error_code === 'export_too_large'
            ? t('settings.security.export.too_large')
            : t('settings.security.export.failed_hint')}
        </p>
      )}
    </div>
  );
}

/**
 * Full-account export (security program D3, GDPR portability).
 *
 * Requesting is step-up guarded (the archive contains decrypted personal
 * data); the section hides itself when the instance has exports disabled
 * (the flag-gated router answers 404).
 * Renders as a SettingsSection card like every other section.
 */
export function AccountExportSettings() {
  const { user } = useAuth();
  return <AccountExportSettingsBody key={user?.id ?? 'anonymous'} />;
}

function AccountExportSettingsBody() {
  const { t, i18n } = useTranslation();
  const { data: job, ownerId, error, refetch } = useApplicationAccountQuery<ExportJob | null>(
    '/account/export/latest', 'AccountExportSettings'
  );
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();
  const [busy, setBusy] = useState(false);
  const releaseOverride = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'account_export', refetch, releaseOverride);

  const inFlight = job?.status === 'pending' || job?.status === 'running';

  const handleRequest = useCallback(async () => {
    if (!isCurrent() || busy || inFlight) return;
    setBusy(true);
    try {
      await guard(async () => {
        if (!isCurrent()) throw new ApiStepUpError();
        return apiClient.post('/account/export');
      });
      if (!isCurrent()) return;
      toast.success(t('settings.security.export.requested'));
      await refetch();
    } catch (err) {
      if (!isCurrent()) return;
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Export request failed', err instanceof Error ? err : new Error('Export request failed'), {
          component: 'AccountExportSettings',
        });
        toast.error(t('settings.security.export.error_generic'));
      }
    } finally {
      if (isCurrent()) setBusy(false);
    }
  }, [busy, inFlight, isCurrent, guard, refetch, t]);

  if (!ownerId || (error instanceof ApiError && error.status === 404)) return null;

  // Absolute API URL — the browser follows this link directly (streams the
  // archive to disk; the filename comes from Content-Disposition).
  const downloadHref =
    job?.status === 'done' && job.download_available
      ? apiEndpointUrl(`/account/export/${job.id}/download`) : null;

  const content = (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <ExportJobStatus job={job} locale={i18n.language} />
        <div className="flex flex-wrap gap-2 sm:ml-auto sm:flex-col sm:items-end shrink-0">
          <Button size="sm" onClick={handleRequest} aria-disabled={busy || inFlight}>
            {inFlight
              ? t('settings.security.export.in_progress')
              : t('settings.security.export.request')}
          </Button>
          {downloadHref && (
            <Button size="sm" variant="outline" asChild>
              <a href={downloadHref}>{t('settings.security.export.download')}</a>
            </Button>
          )}
        </div>
      </div>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />
    </div>
  );

  return (
    <SettingsSection
      value="security-export"
      title={t('settings.security.export.title')}
      description={t('settings.security.export.description')}
      icon={DownloadCloud}
    >
      {content}
    </SettingsSection>
  );
}
