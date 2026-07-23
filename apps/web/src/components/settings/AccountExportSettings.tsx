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
import { useApiQuery } from '@/hooks/useApiQuery';
import { logger } from '@/lib/logger';

interface ExportJob {
  id: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'expired';
  error_code: string | null;
  file_size_bytes: number | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
}

/** Status badge + failure explanation for the latest export job. */
function ExportJobStatus({ job }: { job: ExportJob | null | undefined }) {
  const { t } = useTranslation();
  if (!job) return null;
  return (
    <div className="space-y-1.5">
      <Badge variant="secondary" className="text-[10px]">
        {t(`settings.security.export.status_${job.status}`)}
      </Badge>
      {job.status === 'failed' && (
        <p className="text-xs text-red-600 dark:text-red-400">
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
 * (the flag-gated router answers 404). Polls while a job is in flight.
 * Renders as a collapsible SettingsSection card like every other section.
 */
export function AccountExportSettings({ collapsible = true }: { collapsible?: boolean } = {}) {
  const { t } = useTranslation();
  const [unavailable, setUnavailable] = useState(false);
  const { data: job, refetch } = useApiQuery<ExportJob | null>('/account/export/latest', {
    componentName: 'AccountExportSettings',
    onError: error => {
      if (error instanceof ApiError && error.status === 404) setUnavailable(true);
    },
  });
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();
  const [busy, setBusy] = useState(false);

  const inFlight = job?.status === 'pending' || job?.status === 'running';

  const handleRequest = useCallback(async () => {
    setBusy(true);
    try {
      await guard(() => apiClient.post('/account/export'));
      toast.success(t('settings.security.export.requested'));
      await refetch();
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Export request failed', err as Error, {
          component: 'AccountExportSettings',
        });
        toast.error(t('settings.security.export.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  }, [guard, refetch, t]);

  if (unavailable) return null;

  // Absolute API URL — the browser follows this link directly (streams the
  // archive to disk; the filename comes from Content-Disposition).
  const downloadHref =
    job?.status === 'done' ? apiEndpointUrl(`/account/export/${job.id}/download`) : null;

  const content = (
    <div className="space-y-3">
      <div className="flex items-start gap-3">
        <ExportJobStatus job={job} />
        <div className="ml-auto flex flex-col items-end gap-2 shrink-0">
          <Button size="sm" onClick={handleRequest} disabled={busy || inFlight}>
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

  if (!collapsible) {
    return content;
  }

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
