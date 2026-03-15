'use client';

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Library, RefreshCw, AlertTriangle } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useTranslation } from '@/i18n/client';

import type { BaseSettingsProps } from '@/types/settings';

// API endpoint constants
const REINDEX_ENDPOINT = '/rag-spaces/admin/reindex';
const REINDEX_STATUS_ENDPOINT = '/rag-spaces/admin/reindex/status';

interface ReindexResponse {
  message: string;
  total_documents: number;
  model_from: string | null;
  model_to: string;
}

interface ReindexStatus {
  in_progress: boolean;
  started_at: string | null;
  model_from: string | null;
  model_to: string | null;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
}

/** Polling interval for reindex status (5 seconds). */
const REINDEX_POLL_INTERVAL_MS = 5000;

export default function AdminRAGSpacesSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const { config: appConfig } = useAppConfig(true);
  const [showReindexConfirm, setShowReindexConfirm] = useState(false);
  const [reindexStatus, setReindexStatus] = useState<ReindexStatus | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const embeddingModel = appConfig?.features?.rag_spaces_embedding_model ?? 'text-embedding-3-small';

  // Mutation for triggering reindex
  const { mutate: triggerReindex, loading: reindexing } = useApiMutation<void, ReindexResponse>({
    method: 'POST',
    componentName: 'AdminRAGSpacesSection.reindex',
  });

  const fetchReindexStatus = async () => {
    try {
      const { default: apiClient } = await import('@/lib/api-client');
      const status = await apiClient.get<ReindexStatus>(REINDEX_STATUS_ENDPOINT);
      setReindexStatus(status);
      return status;
    } catch {
      // Silently fail — polling will retry
      return null;
    }
  };

  // Start polling for reindex status
  const startPolling = () => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      const status = await fetchReindexStatus();
      if (status && !status.in_progress) {
        stopPolling();
      }
    }, REINDEX_POLL_INTERVAL_MS);
  };

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  // Check initial reindex status on mount
  useEffect(() => {
    fetchReindexStatus().then((status) => {
      if (status?.in_progress) {
        startPolling();
      }
    });
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleReindex = async () => {
    setShowReindexConfirm(false);
    try {
      const result = await triggerReindex(REINDEX_ENDPOINT);
      if (result) {
        toast.success(
          t('settings.admin.ragSpaces.reindexStarted', {
            count: result.total_documents,
          })
        );
        // Start polling for status
        await fetchReindexStatus();
        startPolling();
      }
    } catch {
      toast.error(t('settings.admin.ragSpaces.reindexError'));
    }
  };

  const progressPercent =
    reindexStatus?.in_progress && reindexStatus.total_documents > 0
      ? Math.round(
          (reindexStatus.processed_documents / reindexStatus.total_documents) * 100
        )
      : 0;

  const content = (
    <div className="space-y-6">
      {/* Embedding Model */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-4 border border-border rounded-lg">
        <div className="flex-1 space-y-1">
          <div className="text-base font-medium">
            {t('settings.admin.ragSpaces.embeddingModel')}
          </div>
          <div className="text-sm text-muted-foreground">
            {t('settings.admin.ragSpaces.embeddingModelDescription')}
          </div>
          <div className="mt-1">
            <Badge variant="secondary" className="font-mono text-xs">
              {embeddingModel}
            </Badge>
          </div>
        </div>
      </div>

      {/* Reindex Section */}
      <div className="p-4 border border-border rounded-lg space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex-1 space-y-1">
            <div className="text-base font-medium">
              {t('settings.admin.ragSpaces.reindexTitle')}
            </div>
            <div className="text-sm text-muted-foreground">
              {t('settings.admin.ragSpaces.reindexDescription')}
            </div>
          </div>
          <Button
            variant="outline"
            onClick={() => setShowReindexConfirm(true)}
            disabled={reindexing || reindexStatus?.in_progress}
            className="shrink-0"
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${reindexStatus?.in_progress ? 'animate-spin' : ''}`}
            />
            {t('settings.admin.ragSpaces.reindexButton')}
          </Button>
        </div>

        {/* Reindex Progress */}
        {reindexStatus?.in_progress && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {t('settings.admin.ragSpaces.reindexProgress', {
                  processed: reindexStatus.processed_documents,
                  total: reindexStatus.total_documents,
                })}
              </span>
              <span className="font-medium">{progressPercent}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            {reindexStatus.failed_documents > 0 && (
              <div className="flex items-center gap-1.5 text-sm text-destructive">
                <AlertTriangle className="h-3.5 w-3.5" />
                {t('settings.admin.ragSpaces.reindexFailed', {
                  count: reindexStatus.failed_documents,
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Info Box */}
      <InfoBox className="p-4">
        <div className="text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">
              {t('settings.admin.ragSpaces.whatItDoes')}:
            </strong>{' '}
            {t('settings.admin.ragSpaces.description')}
          </p>
        </div>
      </InfoBox>

      {/* Reindex Confirmation Dialog */}
      <AlertDialog open={showReindexConfirm} onOpenChange={setShowReindexConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('settings.admin.ragSpaces.reindexConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <p>{t('settings.admin.ragSpaces.reindexConfirmWarning')}</p>
              <ul className="list-disc pl-4 text-sm space-y-1">
                <li>{t('settings.admin.ragSpaces.reindexConfirmCost')}</li>
                <li>{t('settings.admin.ragSpaces.reindexConfirmDowntime')}</li>
              </ul>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleReindex}>
              {t('settings.admin.ragSpaces.reindexConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );

  return (
    <SettingsSection
      value="rag-spaces-admin"
      icon={Library}
      title={t('settings.admin.ragSpaces.title')}
      description={t('settings.admin.ragSpaces.subtitle')}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
