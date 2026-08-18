'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';
import { logger } from '@/lib/logger';
import { formatLocalDateInput } from '@/lib/date-format';
import {
  AdminUserAutocomplete,
  type UserSuggestion,
} from '@/components/settings/AdminUserAutocomplete';

type ExportType =
  | 'token-usage'
  | 'google-api-usage'
  | 'stt-usage'
  | 'tts-usage'
  | 'consumption-summary';

interface ConsumptionExportSectionProps extends BaseSettingsProps {
  /** 'admin' shows user filter and uses admin endpoint; 'user' exports own data only. */
  mode: 'admin' | 'user';
}

const ENDPOINT_BASE: Record<ConsumptionExportSectionProps['mode'], string> = {
  admin: '/api/v1/admin/google-api/export',
  user: '/api/v1/usage/export',
};

const I18N_PREFIX: Record<ConsumptionExportSectionProps['mode'], string> = {
  admin: 'settings.admin.export',
  user: 'settings.user.export',
};

/** The five exports, with the i18n suffix each card reads its copy from. */
const EXPORT_TYPES: { type: ExportType; titleKey: string; descriptionKey: string }[] = [
  { type: 'token-usage', titleKey: 'token_usage_title', descriptionKey: 'token_usage_description' },
  {
    type: 'google-api-usage',
    titleKey: 'google_api_usage_title',
    descriptionKey: 'google_api_usage_description',
  },
  { type: 'stt-usage', titleKey: 'stt_usage_title', descriptionKey: 'stt_usage_description' },
  { type: 'tts-usage', titleKey: 'tts_usage_title', descriptionKey: 'tts_usage_description' },
  { type: 'consumption-summary', titleKey: 'summary_title', descriptionKey: 'summary_description' },
];

/** One export card: title, description, and the download action pinned to the
 * bottom edge so the five buttons align whatever the description length. */
function ExportCard({
  exportType,
  i18n,
  exporting,
  onExport,
  t,
}: {
  exportType: (typeof EXPORT_TYPES)[number];
  i18n: string;
  exporting: ExportType | null;
  onExport: (type: ExportType) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="flex flex-col p-4 border border-border rounded-lg bg-card">
      <div className="flex items-center gap-2 mb-2">
        <FileSpreadsheet className="h-5 w-5 text-primary" />
        <h4 className="font-medium">{t(`${i18n}.${exportType.titleKey}`)}</h4>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        {t(`${i18n}.${exportType.descriptionKey}`)}
      </p>
      <Button
        onClick={() => onExport(exportType.type)}
        disabled={exporting !== null}
        className="mt-auto w-full"
      >
        {exporting === exportType.type ? (
          <span className="animate-pulse">{t(`${i18n}.exporting`)}</span>
        ) : (
          <>
            <Download className="h-4 w-4 mr-2" />
            {t(`${i18n}.download_csv`)}
          </>
        )}
      </Button>
    </div>
  );
}

export default function ConsumptionExportSection({
  lng,
  mode,
}: ConsumptionExportSectionProps) {
  const { t } = useTranslation(lng, 'translation');
  const i18n = I18N_PREFIX[mode];

  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [exporting, setExporting] = useState<ExportType | null>(null);

  // Selected user for the admin export filter. The autocomplete UI (ARIA combobox
  // + stale-response guard) lives in AdminUserAutocomplete (F014).
  const [selectedUser, setSelectedUser] = useState<UserSuggestion | null>(null);

  // Today and first day of current month, as LOCAL civil dates (F036: never via
  // toISOString/UTC, which rolls back a day near midnight in positive offsets).
  // Both derived from a single instant so they cannot straddle a midnight tick.
  const now = new Date();
  const today = formatLocalDateInput(now);
  const firstDayOfMonth = formatLocalDateInput(new Date(now.getFullYear(), now.getMonth(), 1));

  const handleExport = async (exportType: ExportType) => {
    setExporting(exportType);

    try {
      // Build URL with query params
      const params = new URLSearchParams();
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      // Only admin mode can filter by user — user mode never sends user_id
      if (mode === 'admin' && selectedUser) params.append('user_id', selectedUser.id);

      const endpoint = `${ENDPOINT_BASE[mode]}/${exportType}`;
      const url = `${process.env.NEXT_PUBLIC_API_URL}${endpoint}?${params.toString()}`;

      // Fetch with credentials (for auth cookie)
      const response = await fetch(url, {
        method: 'GET',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Export failed with status ${response.status}`);
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('Content-Disposition');
      const filenameMatch = contentDisposition?.match(/filename="(.+)"/);
      const filename = filenameMatch ? filenameMatch[1] : `${exportType}_export.csv`;

      // Download the file
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

      toast.success(t(`${i18n}.success`));
    } catch (error) {
      logger.error('Export failed', error as Error, {
        component: 'ConsumptionExportSection',
        mode,
        exportType,
        startDate,
        endDate,
        userId: selectedUser?.id,
      });
      toast.error(t(`${i18n}.error`));
    } finally {
      setExporting(null);
    }
  };

  const isAdmin = mode === 'admin';
  const dateGridCols = isAdmin ? 'sm:grid-cols-3' : 'sm:grid-cols-2';
  const idPrefix = `${mode}-export`;

  const content = (
    <div className="space-y-6">
      {/* Quick date presets */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
            setStartDate(formatLocalDateInput(firstDay));
            setEndDate(formatLocalDateInput(now));
          }}
        >
          {t(`${i18n}.preset_current_month`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const firstDay = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            const lastDay = new Date(now.getFullYear(), now.getMonth(), 0);
            setStartDate(formatLocalDateInput(firstDay));
            setEndDate(formatLocalDateInput(lastDay));
          }}
        >
          {t(`${i18n}.preset_last_month`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const last30Days = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            setStartDate(formatLocalDateInput(last30Days));
            setEndDate(formatLocalDateInput(now));
          }}
        >
          {t(`${i18n}.preset_last_30_days`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setStartDate('');
            setEndDate('');
          }}
        >
          {t(`${i18n}.preset_all_time`)}
        </Button>
      </div>

      {/* Filters Row */}
      <div className={`grid gap-4 ${dateGridCols} min-w-0`}>
        {/* User Filter with Autocomplete (admin mode only) */}
        {isAdmin && (
          <div className="sm:col-span-1 min-w-0">
            <label
              htmlFor={`${idPrefix}-user-filter`}
              className="block text-sm font-medium text-foreground mb-3"
            >
              {t(`${i18n}.user_filter`)}
            </label>
            <AdminUserAutocomplete
              lng={lng}
              i18n={i18n}
              idPrefix={idPrefix}
              selectedUser={selectedUser}
              onSelect={setSelectedUser}
              onClear={() => setSelectedUser(null)}
            />
            <p className="text-xs text-muted-foreground mt-1">{t(`${i18n}.user_filter_hint`)}</p>
          </div>
        )}

        {/* Date Filters */}
        <div className="min-w-0 overflow-hidden">
          <label
            htmlFor={`${idPrefix}-start-date`}
            className="block text-sm font-medium text-foreground mb-3"
          >
            {t(`${i18n}.start_date`)}
          </label>
          <div className="relative min-w-0">
            <Input
              id={`${idPrefix}-start-date`}
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              placeholder={firstDayOfMonth}
              className="pl-10 w-full min-w-0"
            />
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          </div>
        </div>
        <div className="min-w-0 overflow-hidden">
          <label
            htmlFor={`${idPrefix}-end-date`}
            className="block text-sm font-medium text-foreground mb-3"
          >
            {t(`${i18n}.end_date`)}
          </label>
          <div className="relative min-w-0">
            <Input
              id={`${idPrefix}-end-date`}
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              placeholder={today}
              className="pl-10 w-full min-w-0"
            />
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Export cards — one component, five instances. The five hand-copied
          cards had drifted only in whitespace so far, but the real defect was
          layout: the button flowed after a description of variable length, so
          the five "Download CSV" buttons sat at five different heights. The
          card is a flex column and the button is pushed to the bottom edge —
          descriptions vary, the action line does not. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {EXPORT_TYPES.map(exportType => (
          <ExportCard
            key={exportType.type}
            exportType={exportType}
            i18n={i18n}
            exporting={exporting}
            onExport={handleExport}
            t={t}
          />
        ))}
      </div>
    </div>
  );

  const sectionValue = mode === 'admin' ? 'admin-consumption-export' : 'user-consumption-export';

  return (
    <SettingsSection
      value={sectionValue}
      title={t(`${i18n}.title`)}
      description={t(`${i18n}.description`)}
      icon={FileSpreadsheet}
    >
      {content}
    </SettingsSection>
  );
}
