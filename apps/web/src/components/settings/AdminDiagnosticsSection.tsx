'use client';

import { useState } from 'react';
import { Activity, BookX, RefreshCw, Stethoscope } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Skeleton } from '@/components/ui/skeleton';
import { DiagnosisEvidence } from '@/components/settings/DiagnosisEvidence';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useDiagnosticsIncidentDetail,
  useDiagnosticsIncidents,
  useDiagnosticsOverview,
  type DiagnosticsCheck,
  type DiagnosticsDegradation,
  type DiagnosticsIncident,
  type DiagnosticsIncidentList,
  type DiagnosticsOverview,
} from '@/hooks/useDiagnostics';
import { useTranslation } from '@/i18n/client';
import { unitSuffix } from '@/lib/diagnostics-units';
import { sameLanguage } from '@/lib/language-match';
import { healthTone, incidentTone } from '@/lib/status-tone';

import type { BaseSettingsProps } from '@/types/settings';
import type { TFunction } from 'i18next';

/** Exact value with its unit — a shown number is the measured number. */
function formatCheckValue(check: DiagnosticsCheck): string {
  if (check.value === null || check.value === undefined) {
    return '—';
  }
  const rounded = Math.round(check.value * 100) / 100;
  return `${rounded}${unitSuffix(check.unit)}`;
}

function CheckRow({ check, t }: { check: DiagnosticsCheck; t: TFunction }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">
          {t(`settings.admin.diagnostics.checks.${check.check_id}`, {
            defaultValue: check.check_id,
          })}
        </p>
        {check.detail ? (
          <p className="truncate text-xs text-muted-foreground" title={check.detail}>
            {check.detail}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatCheckValue(check)}
        </span>
        <Badge variant={healthTone(check.status)}>
          {t(`settings.admin.diagnostics.status.${check.status}`)}
        </Badge>
      </div>
    </div>
  );
}

function IncidentRow({
  incident,
  t,
  lng,
}: {
  incident: DiagnosticsIncident;
  t: TFunction;
  lng: string;
}) {
  const [open, setOpen] = useState(false);
  const detail = useDiagnosticsIncidentDetail(open ? incident.id : null);
  const openedAt = new Date(incident.opened_at);
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{incident.title}</p>
          <p className="text-xs text-muted-foreground">
            {incident.correlation_key} · {t(`settings.admin.diagnostics.source.${incident.source}`)}{' '}
            · <time dateTime={incident.opened_at}>{openedAt.toLocaleString()}</time>
          </p>
        </div>
        <Badge variant={incidentTone(incident.status, incident.severity)}>
          {t(`settings.admin.diagnostics.status.${incident.status}`)}
        </Badge>
      </div>
      <SettingsDisclosure
        icon={Stethoscope}
        title={t('settings.admin.diagnostics.diagnosisTitle')}
        onOpenChange={setOpen}
        className="mt-2"
      >
        {detail.loading ? (
          <Skeleton className="h-16 w-full rounded-md" />
        ) : detail.data?.diagnosis ? (
          <div className="space-y-2 text-sm">
            {/* The diagnosis is generated in the languages the admins read, at
                write time. When this reader's language was not among them — a
                profile changed since, or an incident older than the feature —
                the text is still shown rather than hidden, and says so. */}
            {sameLanguage(detail.data.diagnosis.language, lng) ? null : (
              <p className="text-xs text-muted-foreground italic">
                {t('settings.admin.diagnostics.otherLanguage')}
              </p>
            )}
            <p>{detail.data.diagnosis.diagnosis}</p>
            <p className="text-xs text-muted-foreground">
              {t('settings.admin.diagnostics.probableCause')}:{' '}
              {detail.data.diagnosis.probable_cause}
            </p>
            {detail.data.diagnosis.recommended_actions?.length ? (
              <div>
                <p className="text-xs font-medium">
                  {t('settings.admin.diagnostics.recommendedActions')}
                </p>
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {detail.data.diagnosis.recommended_actions.map(action => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <DiagnosisEvidence context={detail.data.diagnosis.context} t={t} lng={lng} />
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {t('settings.admin.diagnostics.noDiagnosisYet')}
          </p>
        )}
      </SettingsDisclosure>
    </div>
  );
}

function OverviewHeader({
  overview,
  t,
  onRefresh,
}: {
  overview: DiagnosticsOverview | undefined;
  t: TFunction;
  onRefresh: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={healthTone(overview?.overall ?? 'unknown')}>
          {overview?.snapshot_available
            ? t(`settings.admin.diagnostics.status.${overview.overall ?? 'unknown'}`)
            : t('settings.admin.diagnostics.noSnapshot')}
        </Badge>
        {overview?.taken_at ? (
          <span className="text-xs text-muted-foreground">
            {t('settings.admin.diagnostics.lastCheck')}{' '}
            <time dateTime={overview.taken_at}>{new Date(overview.taken_at).toLocaleString()}</time>
          </span>
        ) : null}
      </div>
      <Button variant="outline" size="sm" onClick={onRefresh}>
        <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
        {t('settings.admin.diagnostics.refresh')}
      </Button>
    </div>
  );
}

function ChecksGrid({ checks, t }: { checks: DiagnosticsCheck[] | undefined; t: TFunction }) {
  if (!checks?.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('settings.admin.diagnostics.checksTitle')}
      </h4>
      <div className="grid gap-2 sm:grid-cols-2">
        {checks.map(check => (
          <CheckRow key={check.check_id} check={check} t={t} />
        ))}
      </div>
    </div>
  );
}

function DegradationsList({
  degradations,
  t,
}: {
  degradations: DiagnosticsDegradation[] | undefined;
  t: TFunction;
}) {
  if (!degradations?.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">{t('settings.admin.diagnostics.degradationsTitle')}</h4>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {degradations.map(degradation => (
          <li key={`${degradation.capability}-${degradation.reason}`}>
            <span className="font-medium text-foreground">{degradation.capability}</span> —{' '}
            {degradation.reason}
            {degradation.alternative
              ? ` (${t('settings.admin.diagnostics.alternativeHint', {
                  alternative: degradation.alternative,
                })})`
              : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AlertsList({ overview, t }: { overview: DiagnosticsOverview | undefined; t: TFunction }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">
        {t('settings.admin.diagnostics.alertsTitle')}{' '}
        <span className="tabular-nums text-muted-foreground">
          ({overview?.total_active_alerts ?? 0})
        </span>
      </h4>
      {overview?.active_alerts?.length ? (
        <div className="space-y-1">
          {overview.active_alerts.map(alert => (
            <div
              key={`${alert.name}-${alert.component}`}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <span className="truncate">{alert.summary || alert.name}</span>
              <Badge variant={alert.severity === 'critical' ? 'alert' : 'warning'}>
                {alert.name}
              </Badge>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {overview?.alertmanager === 'unavailable'
            ? t('settings.admin.diagnostics.alertmanagerUnavailable')
            : t('settings.admin.diagnostics.noAlerts')}
        </p>
      )}
    </div>
  );
}

function IncidentsList({
  list,
  runbooksAvailable,
  t,
  lng,
}: {
  list: DiagnosticsIncidentList | undefined;
  runbooksAvailable: number | undefined;
  t: TFunction;
  lng: string;
}) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">
        {t('settings.admin.diagnostics.incidentsTitle')}{' '}
        <span className="tabular-nums text-muted-foreground">({list?.total ?? 0})</span>
      </h4>
      {/* Zero is a deployment defect, stated where its effect is felt: the
          diagnoses below were produced without their operations procedure.
          Undefined (older API, first load) says nothing — absence of a count
          is not an empty mount. */}
      {runbooksAvailable === 0 ? (
        <InfoBox variant="warning" role="status">
          <p className="flex items-start gap-2 text-xs text-yellow-700 dark:text-yellow-400">
            <BookX className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{t('settings.admin.diagnostics.runbooksMissing')}</span>
          </p>
        </InfoBox>
      ) : null}
      {list?.items?.length ? (
        <div className="space-y-2">
          {list.items.map(incident => (
            <IncidentRow key={incident.id} incident={incident} t={t} lng={lng} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t('settings.admin.diagnostics.noIncidents')}
        </p>
      )}
    </div>
  );
}

/**
 * Platform health for administrators (spec 2026-08-27, pillar 6).
 *
 * Read-only: latest self-check verdicts with exact values, firing alerts,
 * current degradations with their suggested fallbacks, and the incident
 * memory with the stored LLM diagnoses. Refreshes never unmount populated
 * content (aria-busy on refetch; the skeleton is first-load only).
 */
export default function AdminDiagnosticsSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const overview = useDiagnosticsOverview();
  const incidents = useDiagnosticsIncidents();

  // Monotone first-load flags (derived from data, never from error).
  const overviewFirstLoad = overview.data === undefined && overview.loading;
  const refreshing = overview.loading && overview.data !== undefined;

  const content = overviewFirstLoad ? (
    <div className="space-y-3" aria-busy="true">
      {[0, 1, 2].map(index => (
        <Skeleton key={index} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  ) : (
    <div className="space-y-4" aria-busy={refreshing || undefined}>
      <InfoBox>{t('settings.admin.diagnostics.intro')}</InfoBox>
      <OverviewHeader
        overview={overview.data}
        t={t}
        onRefresh={() => {
          void overview.refetch();
          void incidents.refetch();
        }}
      />
      <ChecksGrid checks={overview.data?.checks} t={t} />
      <DegradationsList degradations={overview.data?.degradations} t={t} />
      <AlertsList overview={overview.data} t={t} />
      <IncidentsList
        list={incidents.data}
        runbooksAvailable={overview.data?.runbooks_available}
        t={t}
        lng={lng}
      />
    </div>
  );

  return (
    <SettingsSection
      value="admin-diagnostics"
      title={t('settings.admin.diagnostics.title')}
      description={t('settings.admin.diagnostics.description')}
      icon={Activity}
    >
      {content}
    </SettingsSection>
  );
}
