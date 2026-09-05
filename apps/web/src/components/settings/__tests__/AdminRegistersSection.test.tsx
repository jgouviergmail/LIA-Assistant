/**
 * The administrator's register extraction (ADR-263, lot 4).
 *
 * The API served this from the day the registers existed and nothing in the
 * interface reached it — a capability that is real and unreachable is absent
 * for everyone but a curl user. These oracles are the four choices the screen
 * exists to express, plus the one it must never make easy to lose.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AdminRegistersSection, { buildHref } from '@/components/settings/AdminRegistersSection';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const dictionary: Record<string, string> = {
        'settings.admin.registers.title': 'Transparency registers',
        'settings.admin.registers.description': 'Extract the registers',
        'settings.admin.registers.intro': 'Wordings are masked by default',
        'settings.admin.registers.register_label': 'Register',
        'settings.admin.registers.register_actions': 'Actions',
        'settings.admin.registers.register_decisions': 'Decisions',
        'settings.admin.registers.register_inference': 'Inference',
        'settings.admin.registers.register_integrity': 'Integrity',
        'settings.admin.registers.article12_title': 'Unified extraction',
        'settings.admin.registers.article12_hint': 'All five records',
        'settings.admin.registers.article12_export': 'Export everything',
        'settings.admin.registers.register_consultations': 'Consultations',
        'settings.admin.registers.format_label': 'Format',
        'settings.admin.registers.format_markdown': 'Readable',
        'settings.admin.registers.format_csv': 'Spreadsheet',
        'settings.admin.registers.format_technical': 'Technical',
        'settings.admin.registers.unmask_label': 'Reveal the wordings',
        'settings.admin.registers.unmask_hint': 'No effect on consultations',
        'settings.admin.registers.all_users': 'All accounts',
        'settings.admin.registers.scope_label': 'Accounts covered',
        'settings.admin.registers.export': 'Export',
        'settings.admin.registers.technical_note': 'Always pseudonymised',
        'settings.admin.export.start_date': 'From',
        'settings.admin.export.end_date': 'To',
      };
      return dictionary[key] ?? (options?.defaultValue as string) ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/settings/AdminUserAutocomplete', () => ({
  AdminUserAutocomplete: ({
    onSelect,
  }: {
    onSelect: (user: { id: string; email: string }) => void;
  }) => (
    <button type="button" onClick={() => onSelect({ id: 'user-1', email: 'a@b.c' })}>
      pick a user
    </button>
  ),
}));

// Partial, not total: the section's subtree reaches `useApiQuery`, which needs
// the real `ApiError`. A full replacement compiled and then threw eighteen
// unhandled rejections under coverage, where the whole module graph loads.
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiEndpointUrl: (endpoint: string) => `https://api.test/api/v1${endpoint}`,
}));

// The figures have their own suite; leaving them real here would make this
// file's oracles depend on a request it never talks about.
vi.mock('@/components/effects/RegisterCharts', () => ({
  RegisterCharts: () => <div data-testid="admin-charts" />,
}));

const USERS = [
  { id: 'u1', email: 'a@b.c', full_name: null, is_active: true },
  { id: 'u2', email: 'd@e.f', full_name: null, is_active: true },
];

describe('buildHref', () => {
  it('asks the readable route for a readable format', () => {
    const href = buildHref({
      register: 'actions',
      format: 'markdown',
      users: [],
      since: '',
      until: '',
      unmask: false,
    });

    expect(href).toContain('/admin/effects/export/readable');
    expect(href).toContain('register=actions');
    expect(href).toContain('format=markdown');
  });

  it('asks the technical route for the technical format, with the register', () => {
    const href = buildHref({
      register: 'consultations',
      format: 'technical',
      users: [],
      since: '',
      until: '',
      unmask: false,
    });

    expect(href).toContain('/admin/effects/export?');
    expect(href).not.toContain('/readable');
    expect(href).toContain('register=consultations');
    expect(href).not.toContain('format=');
  });

  it('names SEVERAL accounts, one parameter each', () => {
    const href = buildHref({
      register: 'actions',
      format: 'csv',
      users: USERS,
      since: '',
      until: '',
      unmask: false,
    });

    expect(href).toContain('user_ids=u1');
    expect(href).toContain('user_ids=u2');
  });

  it('says ALL accounts by naming none', () => {
    const href = buildHref({
      register: 'actions',
      format: 'csv',
      users: [],
      since: '',
      until: '',
      unmask: false,
    });

    expect(href).not.toContain('user_ids');
  });

  /** The two bounds, parsed back as Dates. */
  function bounds(since: string, until: string): { since: Date; until: Date } {
    const params = new URL(
      buildHref({ register: 'actions', format: 'csv', users: [], since, until, unmask: false })
    ).searchParams;
    return {
      since: new Date(params.get('since') ?? ''),
      until: new Date(params.get('until') ?? ''),
    };
  }

  it('reads a picked day as a LOCAL day, not a UTC one', () => {
    // `<input type="date">` gives a local calendar day and the export cuts its
    // sections in the reader's timezone. Parsing it as UTC would shift the
    // window by the operator's offset. Asserted on the LOCAL clock, so the
    // oracle holds in whatever timezone the runner sits in.
    const { since } = bounds('2026-09-01', '2026-09-04');

    expect(since.getHours()).toBe(0);
    expect(since.getMinutes()).toBe(0);
    expect(since.getDate()).toBe(1);
    expect(since.getMonth()).toBe(8);
  });

  it('turns a picked end DAY into the exclusive bound the API documents', () => {
    // The reader asks for "up to the 4th" and means the 4th included; the
    // API's `until` is exclusive, so the bound is the 5th at local midnight.
    const { until } = bounds('2026-09-01', '2026-09-04');

    expect(until.getDate()).toBe(5);
    expect(until.getMonth()).toBe(8);
    expect(until.getHours()).toBe(0);
  });

  it('crosses a month boundary correctly', () => {
    const { until } = bounds('', '2026-09-30');

    expect(until.getDate()).toBe(1);
    expect(until.getMonth()).toBe(9);
  });

  it('crosses a YEAR boundary correctly', () => {
    const { until } = bounds('', '2026-12-31');

    expect(until.getDate()).toBe(1);
    expect(until.getMonth()).toBe(0);
    expect(until.getFullYear()).toBe(2027);
  });

  it('asks to unmask only when asked to', () => {
    const masked = buildHref({
      register: 'actions',
      format: 'markdown',
      users: [],
      since: '',
      until: '',
      unmask: false,
    });
    const revealed = buildHref({
      register: 'actions',
      format: 'markdown',
      users: [],
      since: '',
      until: '',
      unmask: true,
    });

    expect(masked).not.toContain('unmask');
    expect(revealed).toContain('unmask=true');
  });
});

describe('AdminRegistersSection', () => {
  it('offers the two registers and the three formats', () => {
    render(<AdminRegistersSection lng="en" />);

    expect(screen.getByRole('button', { name: 'Actions' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Consultations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Readable' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Spreadsheet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Technical' })).toBeInTheDocument();
  });

  it('downloads through a link, never a fetch into a blob', () => {
    render(<AdminRegistersSection lng="en" />);

    const link = screen.getByRole('link', { name: 'Export' });
    expect(link).toHaveAttribute('download');
    expect(link.getAttribute('href')).toContain('/admin/effects/export/readable');
  });

  it('hides the unmask switch where there is nothing to mask', async () => {
    render(<AdminRegistersSection lng="en" />);
    expect(screen.getByRole('switch', { name: 'Reveal the wordings' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Consultations' }));

    expect(screen.queryByRole('switch', { name: 'Reveal the wordings' })).not.toBeInTheDocument();
  });

  it('hides the unmask switch on the technical export', async () => {
    render(<AdminRegistersSection lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'Technical' }));

    expect(screen.queryByRole('switch', { name: 'Reveal the wordings' })).not.toBeInTheDocument();
    expect(screen.getByText('Always pseudonymised')).toBeInTheDocument();
  });

  it('never disables the choice the click just landed on', async () => {
    render(<AdminRegistersSection lng="en" />);
    const control = screen.getByRole('button', { name: 'Consultations' });

    await userEvent.click(control);

    expect(control).not.toBeDisabled();
    expect(control).toHaveFocus();
    expect(control).toHaveAttribute('aria-current', 'true');
  });

  it('adds a picked account to the scope, and lets it be removed', async () => {
    render(<AdminRegistersSection lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'pick a user' }));
    expect(screen.getByText('a@b.c')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Export' }).getAttribute('href')).toContain(
      'user_ids=user-1'
    );

    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));

    expect(screen.queryByText('a@b.c')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Export' }).getAttribute('href')).not.toContain(
      'user_ids'
    );
  });

  it('does not add the same account twice', async () => {
    render(<AdminRegistersSection lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'pick a user' }));
    await userEvent.click(screen.getByRole('button', { name: 'pick a user' }));

    expect(screen.getAllByText('a@b.c')).toHaveLength(1);
  });
});

describe('AdminRegistersSection — the third register (ADR-263, lot 6)', () => {
  it('offers the decision register only where a tool reads it', async () => {
    render(<AdminRegistersSection lng="en" />);

    expect(screen.queryByRole('button', { name: /Decisions/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));

    expect(screen.getByRole('button', { name: /Decisions/ })).toBeInTheDocument();
  });

  it('carries the chosen register into the download', async () => {
    render(<AdminRegistersSection lng="en" />);
    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));
    await userEvent.click(screen.getByRole('button', { name: /Decisions/ }));

    expect(screen.getByRole('link', { name: 'Export' })).toHaveAttribute(
      'href',
      expect.stringContaining('register=decisions')
    );
  });

  it('falls back rather than building a request the API refuses', async () => {
    // Leaving `decisions` selected under a format that cannot render it would
    // be an invalid combination the interface let the operator assemble.
    render(<AdminRegistersSection lng="en" />);
    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));
    await userEvent.click(screen.getByRole('button', { name: /Decisions/ }));
    await userEvent.click(screen.getByRole('button', { name: /Readable/ }));

    expect(screen.getByRole('link', { name: 'Export' })).toHaveAttribute(
      'href',
      expect.stringContaining('register=actions')
    );
  });

  it('RESTORES the choice when the format comes back', async () => {
    // The effective register falls back; the state does not — switching the
    // format back must not have silently discarded what the operator picked.
    render(<AdminRegistersSection lng="en" />);
    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));
    await userEvent.click(screen.getByRole('button', { name: /Decisions/ }));
    await userEvent.click(screen.getByRole('button', { name: /Readable/ }));
    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));

    expect(screen.getByRole('link', { name: 'Export' })).toHaveAttribute(
      'href',
      expect.stringContaining('register=decisions')
    );
  });
});

describe('AdminRegistersSection — the unified extraction (ADR-263, lot 9)', () => {
  it('offers everything-at-once whatever the register and format', async () => {
    // It answers a different question — the whole account of a period — so it
    // must not disappear behind a choice made for the per-record export.
    render(<AdminRegistersSection lng="en" />);

    expect(screen.getByRole('link', { name: /Export everything/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));

    expect(screen.getByRole('link', { name: /Export everything/ })).toBeInTheDocument();
  });

  it('carries the scope and the period, and no register', async () => {
    render(<AdminRegistersSection lng="en" />);
    await userEvent.type(screen.getByLabelText('From'), '2026-09-01');

    const href = screen.getByRole('link', { name: /Export everything/ }).getAttribute('href');
    expect(href).toContain('/admin/effects/export/article12');
    expect(href).toContain('since=');
    expect(href).not.toContain('register=');
  });

  it('asks about the whole instance when no account is named', () => {
    // The absence of a parameter IS the meaning: an operator asking about the
    // instance is asking about the instance.
    render(<AdminRegistersSection lng="en" />);

    expect(
      screen.getByRole('link', { name: /Export everything/ }).getAttribute('href')
    ).not.toContain('user_ids=');
  });

  it('offers the two records only a tool can read', async () => {
    render(<AdminRegistersSection lng="en" />);

    expect(screen.queryByRole('button', { name: /Inference/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Technical/ }));

    expect(screen.getByRole('button', { name: /Inference/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Integrity/ })).toBeInTheDocument();
  });
});
