/**
 * Typed access to the admin self-diagnostics API (spec 2026-08-27).
 *
 * Superuser-only endpoints; the section that consumes these hooks lives in
 * the administration tab, which the settings shell already gates. Split
 * endpoints on purpose (briefing pattern): the overview is cheap and cached
 * server-side, the incident list pages independently.
 */

import { useApiQuery, type UseApiQueryResult } from '@/hooks/useApiQuery';

/** One check result inside a snapshot (exact measured values). */
export interface DiagnosticsCheck {
  check_id: string;
  status: 'ok' | 'degraded' | 'critical' | 'unknown';
  value: number | null;
  /**
   * Unit of `value`, published by the backend's check registry. Never infer it
   * from `check_id`: that is how a millisecond probe came to be rendered as a
   * percentage (ADR-184 — what the system knows, it publishes).
   */
  unit: string;
  detail: string;
  alertname: string | null;
}

/** One firing alert as the overview reports it. */
export interface DiagnosticsAlert {
  name: string;
  severity: string;
  component: string;
  summary: string;
}

/** One degraded capability with its suggested fallback. */
export interface DiagnosticsDegradation {
  capability: string;
  status: string;
  reason: string;
  alternative: string | null;
}

/** The composed platform-health overview. */
export interface DiagnosticsOverview {
  snapshot_available: boolean;
  open_incidents: number;
  alertmanager: 'ok' | 'unavailable';
  active_alerts: DiagnosticsAlert[];
  total_active_alerts: number;
  degradations: DiagnosticsDegradation[];
  /** Per-alert runbooks the API can hand to the diagnostician; 0 = the mount is empty. */
  runbooks_available: number;
  overall?: 'ok' | 'degraded' | 'critical' | 'unknown';
  taken_at?: string;
  checks?: DiagnosticsCheck[];
}

/** Incident list row (exact totals travel with the page). */
export interface DiagnosticsIncident {
  id: string;
  correlation_key: string;
  source: 'alert' | 'self_check';
  severity: string;
  status: 'open' | 'resolved';
  title: string;
  opened_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  has_diagnosis: boolean;
}

/** One catalogue query of the evidence pack: its series, or why it is blind. */
export interface DiagnosisContextMetric {
  query_id: string;
  title: string;
  /** The catalogue's unit (`percent`, `seconds`, `count`…); absent on older rows. */
  unit?: string;
  status: 'ok' | 'unavailable';
  error?: string | null;
  series: Array<{ labels: Record<string, string>; value: number }>;
  truncated: boolean;
}

/** One distinct failing line of the log excerpt, with how often it occurred. */
export interface DiagnosisContextLogCount {
  event: string;
  level: string;
  head: string;
  count: number;
}

/** The log excerpt of the evidence pack, or the reason there is none. */
export interface DiagnosisContextLogs {
  status: 'ok' | 'unavailable' | 'skipped';
  service?: string;
  error?: string | null;
  lines_read?: number;
  lines_kept?: number;
  counts?: DiagnosisContextLogCount[];
  counts_truncated?: boolean;
  samples?: Array<Record<string, unknown>>;
}

/**
 * What the diagnostician read besides the check's own numbers (ADR-266):
 * collected at diagnosis time, stored with the diagnosis so an administrator can
 * check the text against its evidence. A pack that could not be collected at
 * all carries `status: 'unavailable'` and nothing else.
 */
export interface DiagnosisContext {
  recipe?: string | null;
  window_minutes?: number;
  runtime?: {
    version?: string;
    commit?: string;
    build_date?: string;
    uptime_seconds?: number;
  };
  metrics?: DiagnosisContextMetric[];
  logs?: DiagnosisContextLogs;
  status?: 'unavailable';
  error?: string;
}

/** Incident detail with evidence and the stored diagnosis. */
export interface DiagnosticsIncidentDetail extends DiagnosticsIncident {
  evidence: Record<string, unknown>;
  diagnosis: {
    diagnosis?: string;
    probable_cause?: string;
    recommended_actions?: string[];
    /** Language the text above was written in (backend canonical, e.g. `zh-CN`). */
    language?: string;
    model?: string;
    cost_usd?: number;
    diagnosed_at?: string;
    /** The evidence pack the text was written from (absent on rows older than ADR-266). */
    context?: DiagnosisContext;
  } | null;
  action_log: Array<Record<string, unknown>>;
}

/** Paged incident listing with an EXACT total. */
export interface DiagnosticsIncidentList {
  items: DiagnosticsIncident[];
  total: number;
  page: number;
  page_size: number;
}

/** Platform-health overview (admin only). */
export function useDiagnosticsOverview(): UseApiQueryResult<DiagnosticsOverview> {
  return useApiQuery<DiagnosticsOverview>('/admin/diagnostics/overview', {
    componentName: 'AdminDiagnosticsSection',
  });
}

/** Incident memory, newest first (admin only). */
export function useDiagnosticsIncidents(pageSize = 25): UseApiQueryResult<DiagnosticsIncidentList> {
  return useApiQuery<DiagnosticsIncidentList>(
    `/admin/diagnostics/incidents?status=all&page=1&page_size=${pageSize}`,
    { componentName: 'AdminDiagnosticsSection' }
  );
}

/** One incident with evidence and diagnosis (admin only, on demand). */
export function useDiagnosticsIncidentDetail(
  incidentId: string | null
): UseApiQueryResult<DiagnosticsIncidentDetail> {
  return useApiQuery<DiagnosticsIncidentDetail>(
    `/admin/diagnostics/incidents/${incidentId ?? 'none'}`,
    {
      componentName: 'AdminDiagnosticsSection',
      // `enabled` is the real gate: with no selection nothing is fetched and
      // the placeholder path never leaves the client.
      enabled: incidentId !== null,
      deps: [incidentId],
    }
  );
}
