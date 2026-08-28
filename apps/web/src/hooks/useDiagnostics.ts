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

/** Incident detail with evidence and the stored diagnosis. */
export interface DiagnosticsIncidentDetail extends DiagnosticsIncident {
  evidence: Record<string, unknown>;
  diagnosis: {
    diagnosis?: string;
    probable_cause?: string;
    recommended_actions?: string[];
    model?: string;
    cost_usd?: number;
    diagnosed_at?: string;
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
