'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  AudioLines,
  CalendarRange,
  ChartNoAxesCombined,
  Cpu,
  Download,
  FileSpreadsheet,
  MapPin,
  Mic,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { FormSection } from '@/components/ui/form-section';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { formatLocalDateInput } from '@/lib/date-format';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
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
  mode: 'admin' | 'user';
}
const ENDPOINT_BASE = { admin: '/admin/google-api/export', user: '/usage/export' } as const;
const I18N_PREFIX = { admin: 'settings.admin.export', user: 'settings.user.export' } as const;
const EXPORT_TYPES: {
  type: ExportType;
  titleKey: string;
  descriptionKey: string;
  icon: LucideIcon;
  tint: string;
}[] = [
  {
    type: 'token-usage',
    titleKey: 'token_usage_title',
    descriptionKey: 'token_usage_description',
    icon: Cpu,
    tint: 'bg-primary/10',
  },
  {
    type: 'google-api-usage',
    titleKey: 'google_api_usage_title',
    descriptionKey: 'google_api_usage_description',
    icon: MapPin,
    tint: 'bg-success/10',
  },
  {
    type: 'stt-usage',
    titleKey: 'stt_usage_title',
    descriptionKey: 'stt_usage_description',
    icon: Mic,
    tint: 'bg-warning/10',
  },
  {
    type: 'tts-usage',
    titleKey: 'tts_usage_title',
    descriptionKey: 'tts_usage_description',
    icon: AudioLines,
    tint: 'bg-primary/10',
  },
  {
    type: 'consumption-summary',
    titleKey: 'summary_title',
    descriptionKey: 'summary_description',
    icon: ChartNoAxesCombined,
    tint: 'bg-success/10',
  },
];

/** Keep the server's CSV filename, including RFC 5987 Unicode names. */
function exportFilename(response: Response, type: ExportType): string {
  const disposition = response.headers.get('Content-Disposition');
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      /* Fall back to the ordinary name. */
    }
  }
  return disposition?.match(/filename="([^"]+)"/i)?.[1] ?? `${type}_export.csv`;
}

function saveCsv(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  try {
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}

function ExportRow({
  item,
  i18n,
  exporting,
  blocked,
  onExport,
  t,
}: {
  item: (typeof EXPORT_TYPES)[number];
  i18n: string;
  exporting: ExportType | null;
  blocked: boolean;
  onExport: (type: ExportType) => void;
  t: (key: string) => string;
}) {
  const headingId = useId();
  const descriptionId = useId();
  const downloadLabelId = useId();
  const Icon = item.icon;
  return (
    <li className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:gap-x-4 sm:px-5 sm:py-5">
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-primary sm:row-span-2 ${item.tint}`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <h4
        id={headingId}
        className="min-w-0 text-sm font-semibold leading-relaxed sm:col-start-2 sm:row-start-1 sm:text-base"
      >
        {t(`${i18n}.${item.titleKey}`)}
      </h4>
      <p
        id={descriptionId}
        className="col-span-2 min-w-0 text-sm leading-relaxed text-muted-foreground sm:col-span-1 sm:col-start-2 sm:row-start-2"
      >
        {t(`${i18n}.${item.descriptionKey}`)}
      </p>
      <Button
        type="button"
        aria-labelledby={`${downloadLabelId} ${headingId}`}
        aria-describedby={descriptionId}
        onClick={() => onExport(item.type)}
        disabled={blocked}
        aria-disabled={blocked || exporting !== null}
        aria-busy={exporting === item.type}
        className="col-span-2 mt-1 min-h-11 w-full sm:col-span-1 sm:col-start-3 sm:row-start-1 sm:mt-0 sm:min-h-9 sm:w-auto"
      >
        {exporting === item.type ? (
          <LoadingSpinner spinnerColor="white" label={t(`${i18n}.exporting`)} />
        ) : (
          <Download aria-hidden="true" />
        )}
        <span id={downloadLabelId}>{t(`${i18n}.download`)}</span>
      </Button>
    </li>
  );
}

/** Account and mode changes discard filters and cannot publish an old account's file. */
export default function ConsumptionExportSection(props: ConsumptionExportSectionProps) {
  const { user } = useAuth();
  return (
    <ConsumptionExportContent
      key={`${user?.id ?? 'anonymous'}:${props.mode}`}
      {...props}
      ownerId={user?.id}
    />
  );
}

function ConsumptionExportContent({
  lng,
  mode,
  ownerId,
}: ConsumptionExportSectionProps & { ownerId: string | undefined }) {
  const { t } = useTranslation(lng, 'translation');
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const i18n = I18N_PREFIX[mode];
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [exporting, setExporting] = useState<ExportType | null>(null);
  const [error, setError] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserSuggestion | null>(null);
  const active = useRef<AbortController | null>(null);
  const errorId = useId();
  const idPrefix = `${mode}-export`;
  const invalidPeriod = !!startDate && !!endDate && startDate > endDate;
  const params = {
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    user_id: mode === 'admin' ? selectedUser?.id : undefined,
  };
  useEffect(() => () => active.current?.abort(), []);

  const handleExport = async (exportType: ExportType) => {
    if (!isCurrent() || active.current || invalidPeriod) return;
    const controller = new AbortController();
    active.current = controller;
    setExporting(exportType);
    setError(false);
    try {
      const response = await apiClient.getResponse(`${ENDPOINT_BASE[mode]}/${exportType}`, {
        params,
        signal: controller.signal,
      });
      if (!isCurrent() || controller.signal.aborted) return;
      const blob = await response.blob();
      if (!isCurrent() || controller.signal.aborted) return;
      saveCsv(blob, exportFilename(response, exportType));
      toast.success(t(`${i18n}.success`));
    } catch (cause) {
      if (!isCurrent() || controller.signal.aborted) return;
      logger.error('Export failed', cause instanceof Error ? cause : new Error(String(cause)), {
        component: 'ConsumptionExportSection',
        mode,
        exportType,
      });
      setError(true);
      toast.error(t(`${i18n}.error`));
    } finally {
      if (isCurrent()) {
        active.current = null;
        setExporting(null);
      }
    }
  };

  const preset = (kind: 'current' | 'previous' | 'thirty' | 'all') => {
    setError(false);
    if (kind === 'all') {
      setStartDate('');
      setEndDate('');
      return;
    }
    const now = new Date();
    const beginning = new Date(now.getFullYear(), now.getMonth(), 1);
    if (kind === 'previous') {
      beginning.setMonth(beginning.getMonth() - 1);
      now.setDate(0);
    }
    if (kind === 'thirty') {
      beginning.setTime(now.getTime());
      // The API includes the whole end date: today plus the previous 29 civil days.
      beginning.setDate(beginning.getDate() - 29);
    }
    setStartDate(formatLocalDateInput(beginning));
    setEndDate(formatLocalDateInput(now));
  };

  return (
    <SettingsSection
      value={mode === 'admin' ? 'admin-consumption-export' : 'user-consumption-export'}
      title={t(`${i18n}.title`)}
      icon={FileSpreadsheet}
      contentClassName="space-y-5"
    >
      <p className="-mt-2 text-sm leading-relaxed text-muted-foreground sm:pl-[60px]">
        {t(`${i18n}.description`)}
      </p>
      <div className="rounded-2xl border border-border bg-background [--lia-field-background:var(--color-card)] p-4 sm:p-5">
        <FormSection icon={CalendarRange} title={t(`${i18n}.period_title`)}>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {t(`${i18n}.period_description`)}
          </p>
          {mode === 'admin' && (
            <div className="max-w-xl space-y-3">
              <label htmlFor={`${idPrefix}-user-filter`} className="block text-sm font-medium">
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
              <p className="text-xs text-muted-foreground">{t(`${i18n}.user_filter_hint`)}</p>
            </div>
          )}
          <div className="max-w-md space-y-3">
            <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3">
              <label
                htmlFor={`${idPrefix}-start-date`}
                className="block min-w-7 text-sm font-medium"
              >
                {t(`${i18n}.start_date`)}
              </label>
              <Input
                id={`${idPrefix}-start-date`}
                type="date"
                value={startDate}
                onChange={event => {
                  setStartDate(event.target.value);
                  setError(false);
                }}
                aria-invalid={invalidPeriod}
                aria-describedby={invalidPeriod ? errorId : undefined}
                className="min-w-0"
              />
              <label htmlFor={`${idPrefix}-end-date`} className="block min-w-7 text-sm font-medium">
                {t(`${i18n}.end_date`)}
              </label>
              <Input
                id={`${idPrefix}-end-date`}
                type="date"
                value={endDate}
                onChange={event => {
                  setEndDate(event.target.value);
                  setError(false);
                }}
                aria-invalid={invalidPeriod}
                aria-describedby={invalidPeriod ? errorId : undefined}
                className="min-w-0"
              />
            </div>
            {invalidPeriod && (
              <p id={errorId} role="alert" className="text-sm text-destructive">
                {t(`${i18n}.invalid_period`)}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {(['current', 'previous', 'thirty', 'all'] as const).map((kind, index) => (
              <Button
                key={kind}
                type="button"
                variant="outline"
                onClick={() => preset(kind)}
                className="min-h-11 h-auto whitespace-normal px-3 py-2 text-xs sm:min-h-9 sm:whitespace-nowrap"
              >
                {t(
                  `${i18n}.${['preset_current_month', 'preset_last_month', 'preset_last_30_days', 'preset_all_time'][index]}`
                )}
              </Button>
            ))}
          </div>
        </FormSection>
      </div>
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {t(`${i18n}.error`)}
        </p>
      )}
      <ul
        aria-label={t(`${i18n}.title`)}
        aria-busy={exporting !== null}
        className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-background [--lia-field-background:var(--color-card)]"
      >
        {EXPORT_TYPES.map(item => (
          <ExportRow
            key={item.type}
            item={item}
            i18n={i18n}
            exporting={exporting}
            blocked={!ownerId || invalidPeriod}
            onExport={handleExport}
            t={t}
          />
        ))}
      </ul>
    </SettingsSection>
  );
}
