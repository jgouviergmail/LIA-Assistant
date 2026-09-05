'use client';

import { ScrollText } from 'lucide-react';

import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { unitSuffix } from '@/lib/diagnostics-units';
import { formatUptime } from '@/lib/format-uptime';

import type {
  DiagnosisContext,
  DiagnosisContextLogs,
  DiagnosisContextMetric,
} from '@/hooks/useDiagnostics';
import type { TFunction } from 'i18next';

/**
 * What the diagnostician read (ADR-266), rendered from the pack stored WITH the
 * diagnosis so an administrator can check the text against its evidence.
 *
 * Two rules the layout keeps: a blind source is STATED with its reason, never
 * rendered as a reassuring zero; and nothing here is computed client-side —
 * every number is the one the backend collected. Labels and log heads are
 * bounded upstream, so the chips can wrap freely on a phone.
 */

/** `k=v,k=v` — one chip per sample, the value and its unit suffix beside it. */
function SeriesChips({
  series,
  unit,
}: {
  series: DiagnosisContextMetric['series'];
  unit: string | undefined;
}) {
  const suffix = unitSuffix(unit);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {series.map(sample => {
        const label = Object.entries(sample.labels)
          .map(([key, value]) => `${key}=${value}`)
          .join(',');
        return (
          <span
            key={label || 'value'}
            className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5"
          >
            {label ? <span className="font-mono">{label}</span> : null}
            <span className="tabular-nums">{`${sample.value}${suffix}`}</span>
          </span>
        );
      })}
    </span>
  );
}

function MetricRow({ metric, t }: { metric: DiagnosisContextMetric; t: TFunction }) {
  return (
    <li className="space-y-1">
      <span className="font-medium text-foreground">{metric.title}</span>
      <div>
        {metric.status !== 'ok' ? (
          <span>
            {t('settings.admin.diagnostics.contextUnavailable', { error: metric.error ?? '' })}
          </span>
        ) : metric.series.length ? (
          <>
            <SeriesChips series={metric.series} unit={metric.unit} />
            {metric.truncated ? (
              <span className="ml-1">({t('settings.admin.diagnostics.contextTruncated')})</span>
            ) : null}
          </>
        ) : (
          <span>{t('settings.admin.diagnostics.contextNoSeries')}</span>
        )}
      </div>
    </li>
  );
}

function LogsBlock({ logs, t }: { logs: DiagnosisContextLogs; t: TFunction }) {
  if (logs.status === 'skipped') {
    return <p>{t('settings.admin.diagnostics.contextSkipped')}</p>;
  }
  if (logs.status !== 'ok') {
    return <p>{t('settings.admin.diagnostics.contextUnavailable', { error: logs.error ?? '' })}</p>;
  }
  return (
    <div className="space-y-1">
      <p>
        {t('settings.admin.diagnostics.contextLogsRead', {
          kept: logs.lines_kept ?? 0,
          read: logs.lines_read ?? 0,
        })}
      </p>
      {logs.counts?.length ? (
        <ul className="space-y-1">
          {logs.counts.map(entry => (
            <li
              key={`${entry.event}-${entry.level}-${entry.head}`}
              className="flex flex-wrap items-baseline gap-x-2"
            >
              <span className="tabular-nums font-medium text-foreground">×{entry.count}</span>
              <span className="font-mono">{entry.event || '—'}</span>
              {entry.level ? <span className="uppercase">{entry.level}</span> : null}
              {entry.head ? (
                <span className="min-w-0 basis-full break-words font-mono text-[11px]">
                  {entry.head}
                </span>
              ) : null}
            </li>
          ))}
          {logs.counts_truncated ? (
            <li>({t('settings.admin.diagnostics.contextTruncated')})</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

export function DiagnosisEvidence({
  context,
  t,
  lng,
}: {
  context: DiagnosisContext | undefined;
  t: TFunction;
  lng: string;
}) {
  if (!context) {
    return null;
  }
  if (context.status === 'unavailable') {
    return (
      <p className="text-xs text-muted-foreground">
        {t('settings.admin.diagnostics.contextPackUnavailable', { error: context.error ?? '' })}
      </p>
    );
  }
  const runtime = context.runtime;
  return (
    <SettingsDisclosure
      icon={ScrollText}
      title={t('settings.admin.diagnostics.contextTitle')}
      className="mt-2"
    >
      <div className="space-y-3 text-xs text-muted-foreground">
        {runtime ? (
          <p className="break-words">
            {t('settings.admin.diagnostics.contextRuntime', {
              version: runtime.version ?? '',
              commit: runtime.commit ?? '',
              uptime: formatUptime(runtime.uptime_seconds ?? 0, lng),
              window: context.window_minutes ?? '',
            })}
          </p>
        ) : null}
        {context.metrics?.length ? (
          <div className="space-y-1">
            <p className="font-medium text-foreground">
              {t('settings.admin.diagnostics.contextMetrics')}
            </p>
            <ul className="space-y-2">
              {context.metrics.map(metric => (
                <MetricRow key={metric.query_id} metric={metric} t={t} />
              ))}
            </ul>
          </div>
        ) : null}
        {context.logs ? (
          <div className="space-y-1">
            <p className="font-medium text-foreground">
              {t('settings.admin.diagnostics.contextLogs')}
            </p>
            <LogsBlock logs={context.logs} t={t} />
          </div>
        ) : null}
      </div>
    </SettingsDisclosure>
  );
}
