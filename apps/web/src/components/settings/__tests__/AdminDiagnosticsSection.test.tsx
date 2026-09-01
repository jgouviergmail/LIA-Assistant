/**
 * Admin platform-health panel (spec 2026-08-27, pillar 6).
 *
 * What must never lie here: the totals (exact counts from the API, never a
 * page length), the verdict badges, and the refresh behaviour — a refetch of
 * populated content must NOT unmount it (aria-busy, not a skeleton swap).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && typeof options.alternative === 'string' ? `${key}:${options.alternative}` : key,
  }),
}));

vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const overviewHook = vi.fn();
const incidentsHook = vi.fn();
const detailHook = vi.fn();

vi.mock('@/hooks/useDiagnostics', async () => {
  const actual =
    await vi.importActual<typeof import('@/hooks/useDiagnostics')>('@/hooks/useDiagnostics');
  return {
    ...actual,
    useDiagnosticsOverview: (...args: unknown[]) => overviewHook(...args),
    useDiagnosticsIncidents: (...args: unknown[]) => incidentsHook(...args),
    useDiagnosticsIncidentDetail: (...args: unknown[]) => detailHook(...args),
  };
});

import AdminDiagnosticsSection from '@/components/settings/AdminDiagnosticsSection';
import type {
  DiagnosticsIncident,
  DiagnosticsOverview,
} from '@/hooks/useDiagnostics';

function overview(overrides: Partial<DiagnosticsOverview> = {}): DiagnosticsOverview {
  return {
    snapshot_available: true,
    open_incidents: 2,
    alertmanager: 'ok',
    active_alerts: [
      { name: 'RedisDown', severity: 'critical', component: 'redis', summary: 'Redis is down' },
    ],
    total_active_alerts: 1,
    degradations: [
      {
        capability: 'web_search',
        status: 'degraded',
        reason: 'circuit_open:brave_search',
        alternative: 'perplexity',
      },
    ],
    overall: 'degraded',
    taken_at: '2026-08-28T10:00:00Z',
    checks: [
      {
        check_id: 'api_error_rate',
        status: 'ok',
        value: 0.4,
        unit: 'percent',
        detail: '',
        alertname: 'HighErrorRate',
      },
      {
        check_id: 'redis',
        status: 'critical',
        value: null,
        unit: '',
        detail: 'ConnectionError',
        alertname: 'RedisDown',
      },
    ],
    ...overrides,
  };
}

function incident(overrides: Partial<DiagnosticsIncident> = {}): DiagnosticsIncident {
  return {
    id: '3d1a0a58-0000-4000-8000-000000000001',
    correlation_key: 'RedisDown',
    source: 'self_check',
    severity: 'critical',
    status: 'open',
    title: 'Self-check critical: RedisDown',
    opened_at: '2026-08-28T10:00:00Z',
    last_seen_at: '2026-08-28T10:05:00Z',
    resolved_at: null,
    has_diagnosis: true,
    ...overrides,
  };
}

function wire(
  options: {
    overviewData?: DiagnosticsOverview | undefined;
    overviewLoading?: boolean;
    incidentRows?: DiagnosticsIncident[];
    total?: number;
    detailData?: { diagnosis: Record<string, unknown> | null } | undefined;
  } = {}
): { refetchOverview: ReturnType<typeof vi.fn> } {
  // `'overviewData' in options`, not a destructuring default: an EXPLICIT
  // undefined must mean "first load", while an absent key means "populated".
  const overviewData = 'overviewData' in options ? options.overviewData : overview();
  const { overviewLoading = false, incidentRows = [incident()], total = 7 } = options;
  const refetchOverview = vi.fn().mockResolvedValue(undefined);
  overviewHook.mockReturnValue({
    data: overviewData,
    loading: overviewLoading,
    error: null,
    refetch: refetchOverview,
    setData: vi.fn(),
  });
  incidentsHook.mockReturnValue({
    data: { items: incidentRows, total, page: 1, page_size: 25 },
    loading: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    setData: vi.fn(),
  });
  detailHook.mockReturnValue({
    data: options.detailData,
    loading: false,
    error: null,
    refetch: vi.fn(),
    setData: vi.fn(),
  });
  return { refetchOverview };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminDiagnosticsSection', () => {
  it('shows the overall verdict, exact totals and check labels', () => {
    wire();
    render(<AdminDiagnosticsSection lng="en" />);
    expect(screen.getByText('settings.admin.diagnostics.status.degraded')).toBeInTheDocument();
    // Exact totals from the API, rendered verbatim.
    expect(screen.getByText('(7)')).toBeInTheDocument();
    expect(screen.getByText('(1)')).toBeInTheDocument();
    expect(
      screen.getByText('settings.admin.diagnostics.checks.api_error_rate')
    ).toBeInTheDocument();
    // The critical check keeps its typed detail (exception class name only).
    expect(screen.getByText('ConnectionError')).toBeInTheDocument();
  });

  it('renders the degradation with its suggested fallback', () => {
    wire();
    render(<AdminDiagnosticsSection lng="en" />);
    expect(screen.getByText('web_search')).toBeInTheDocument();
    expect(
      screen.getByText(/settings\.admin\.diagnostics\.alternativeHint:perplexity/)
    ).toBeInTheDocument();
  });

  it('first load shows a skeleton; a refresh of populated content does not unmount', () => {
    wire({ overviewData: undefined, overviewLoading: true });
    const { rerender } = render(<AdminDiagnosticsSection lng="en" />);
    expect(
      screen.queryByText('settings.admin.diagnostics.checksTitle')
    ).not.toBeInTheDocument();

    // Populated + refetching: content stays mounted, aria-busy announces it.
    wire({ overviewLoading: true });
    rerender(<AdminDiagnosticsSection lng="en" />);
    expect(screen.getByText('settings.admin.diagnostics.checksTitle')).toBeInTheDocument();
  });

  it('refresh triggers both refetches from a real button', async () => {
    const { refetchOverview } = wire();
    render(<AdminDiagnosticsSection lng="en" />);
    await userEvent.click(
      screen.getByRole('button', { name: /settings\.admin\.diagnostics\.refresh/ })
    );
    expect(refetchOverview).toHaveBeenCalledTimes(1);
  });

  it('states alertmanager unavailability instead of pretending "no alerts"', () => {
    wire({
      overviewData: overview({
        alertmanager: 'unavailable',
        active_alerts: [],
        total_active_alerts: 0,
      }),
    });
    render(<AdminDiagnosticsSection lng="en" />);
    expect(
      screen.getByText('settings.admin.diagnostics.alertmanagerUnavailable')
    ).toBeInTheDocument();
  });

  it('empty incident memory says so explicitly', () => {
    wire({ incidentRows: [], total: 0 });
    render(<AdminDiagnosticsSection lng="en" />);
    expect(screen.getByText('settings.admin.diagnostics.noIncidents')).toBeInTheDocument();
  });
});

describe('the unit comes from the API, never from the check id', () => {
  // The renderer used to derive the suffix from `check_id`, defaulting to '%'.
  // A check measuring milliseconds — the egress probe added after the
  // 2026-08-28 outage — would have been shown as a percentage. The backend
  // knows the unit and now publishes it (ADR-184).
  beforeEach(() => {
    incidentsHook.mockReturnValue({ data: { items: [], total: 0 }, loading: false, error: null, refetch: vi.fn() });
    detailHook.mockReturnValue({ data: null, loading: false, error: null, refetch: vi.fn() });
  });

  it.each([
    ['milliseconds', 12.3, '12.3 ms'],
    ['percent', 0.4, '0.4%'],
    ['seconds', 0.22, '0.22s'],
    ['count', 2, '2'],
    ['', 5, '5'],
  ])('renders a %s value as %s', async (unit, value, expected) => {
    overviewHook.mockReturnValue({
      data: overview({
        checks: [{ check_id: 'whatever', status: 'ok', value, unit, detail: '', alertname: null }],
      }),
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<AdminDiagnosticsSection lng="en" />);

    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it('shows a dash when nothing was measured', async () => {
    overviewHook.mockReturnValue({
      data: overview({
        checks: [
          { check_id: 'database', status: 'ok', value: null, unit: '', detail: '', alertname: null },
        ],
      }),
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<AdminDiagnosticsSection lng="en" />);

    expect(await screen.findByText('—')).toBeInTheDocument();
  });
});

describe('the language a diagnosis was written in', () => {
  // The diagnosis is generated at WRITE time, in the languages the admins read
  // — there is no reader to ask when a scheduler tick produces it. When this
  // reader's language was not among them (a profile changed since, or an
  // incident older than the feature), the text is shown rather than hidden,
  // and the panel says so instead of passing it off as the answer.
  const diagnosisIn = (language: string) => ({
    diagnosis: {
      diagnosis: 'Redis container stopped',
      probable_cause: 'OOM kill',
      recommended_actions: ['docker restart redis'],
      language,
    },
  });

  it('says nothing when the diagnosis is in the reader language', async () => {
    wire({ detailData: diagnosisIn('en') });
    render(<AdminDiagnosticsSection lng="en" />);
    await userEvent.click(screen.getByText('settings.admin.diagnostics.diagnosisTitle'));

    expect(screen.getByText('Redis container stopped')).toBeInTheDocument();
    expect(
      screen.queryByText('settings.admin.diagnostics.otherLanguage')
    ).not.toBeInTheDocument();
  });

  it('flags a diagnosis written in another language, and still shows it', async () => {
    wire({ detailData: diagnosisIn('de') });
    render(<AdminDiagnosticsSection lng="fr" />);
    await userEvent.click(screen.getByText('settings.admin.diagnostics.diagnosisTitle'));

    expect(screen.getByText('settings.admin.diagnostics.otherLanguage')).toBeInTheDocument();
    // Hiding it would trade a translation gap for a hidden incident.
    expect(screen.getByText('Redis container stopped')).toBeInTheDocument();
  });

  it('does not flag Chinese, whose two canonical spellings differ by layer', async () => {
    wire({ detailData: diagnosisIn('zh-CN') });
    render(<AdminDiagnosticsSection lng="zh" />);
    await userEvent.click(screen.getByText('settings.admin.diagnostics.diagnosisTitle'));

    expect(
      screen.queryByText('settings.admin.diagnostics.otherLanguage')
    ).not.toBeInTheDocument();
  });

  it('says nothing for a row written before the language stamp existed', async () => {
    wire({
      detailData: {
        diagnosis: { diagnosis: 'Legacy text', probable_cause: 'c', recommended_actions: [] },
      },
    });
    render(<AdminDiagnosticsSection lng="fr" />);
    await userEvent.click(screen.getByText('settings.admin.diagnostics.diagnosisTitle'));

    expect(screen.getByText('Legacy text')).toBeInTheDocument();
    expect(
      screen.queryByText('settings.admin.diagnostics.otherLanguage')
    ).not.toBeInTheDocument();
  });
});
