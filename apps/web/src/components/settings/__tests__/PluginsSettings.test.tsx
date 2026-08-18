/**
 * PluginsSettings — Agent Plugins section (ADR-225).
 *
 * Pins the section's four behaviors: empty state, installed-plugin listing
 * with component-count badges, the group-uninstall confirm flow, and the
 * import report dialog where a skipped component always shows its translated
 * taxonomy reason (anti-false-success doctrine).
 *
 * The section renders as an open card (ADR-227), so its body is visible on
 * mount — there is no disclosure step to perform first.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, userEvent } from '@/__tests__/test-utils';

const { usePlugins } = vi.hoisted(() => ({ usePlugins: vi.fn() }));
vi.mock('@/hooks/usePlugins', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/usePlugins')>();
  return { ...original, usePlugins };
});
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { PluginsSettings } from '../PluginsSettings';
import type {
  usePlugins as usePluginsFn,
  InstalledPlugin,
  PluginImportReport,
} from '@/hooks/usePlugins';

type PluginsHook = ReturnType<typeof usePluginsFn>;

function plugin(over: Partial<InstalledPlugin> = {}): InstalledPlugin {
  return {
    id: 'p-1',
    name: 'acme.tools',
    version: '1.2.0',
    description: 'Acme developer tools',
    spec_version: '1.0.0',
    skill_names: ['summarize'],
    server_names: ['acme.tools:api'],
    created_at: null,
    updated_at: null,
    ...over,
  };
}

function report(over: Partial<PluginImportReport> = {}): PluginImportReport {
  return {
    plugin_id: 'p-1',
    name: 'acme.tools',
    version: '1.2.0',
    description: null,
    updated: false,
    components: [],
    warnings: [],
    ...over,
  };
}

function hook(over: Partial<PluginsHook> = {}): PluginsHook {
  return {
    plugins: [plugin()],
    total: 1,
    loading: false,
    error: null,
    refetch: vi.fn(),
    importPlugin: vi.fn().mockResolvedValue(report()),
    importFromUrl: vi.fn().mockResolvedValue(report()),
    importingFromUrl: false,
    uninstallPlugin: vi.fn().mockResolvedValue(undefined),
    uninstalling: false,
    ...over,
  } as PluginsHook;
}

function renderSection() {
  return renderWithProviders(
    <PluginsSettings lng="en" />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('PluginsSettings', () => {
  it('shows the empty state when no plugin is installed', () => {
    usePlugins.mockReturnValue(hook({ plugins: [], total: 0 }));
    renderSection();

    expect(screen.getByText('settings.plugins.empty')).toBeInTheDocument();
  });

  it('lists installed plugins with version and component-count badges', () => {
    usePlugins.mockReturnValue(hook());
    renderSection();

    expect(screen.getByText('acme.tools')).toBeInTheDocument();
    expect(screen.getByText('v1.2.0')).toBeInTheDocument();
    expect(screen.getByText('settings.plugins.skills_count')).toBeInTheDocument();
    expect(screen.getByText('settings.plugins.servers_count')).toBeInTheDocument();
  });

  it('uninstalls through an explicit confirmation dialog', async () => {
    const uninstallPlugin = vi.fn().mockResolvedValue(undefined);
    usePlugins.mockReturnValue(hook({ uninstallPlugin }));
    const user = userEvent.setup();
    renderSection();

    await user.click(screen.getByRole('button', { name: /settings.plugins.uninstall_aria/ }));
    expect(screen.getByText('settings.plugins.uninstall_confirm_title')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: /^settings.plugins.uninstall$/ })
    );

    await waitFor(() => expect(uninstallPlugin).toHaveBeenCalledWith('p-1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('shows the import report with the reason of every skipped component', async () => {
    const importPlugin = vi.fn().mockResolvedValue(
      report({
        components: [
          { kind: 'skill', key: 'summarize', status: 'installed', issues: [] },
          {
            kind: 'mcp_server',
            key: 'local',
            status: 'skipped',
            issues: [
              { code: 'server_transport_unsupported', field: 'local', detail: null },
            ],
          },
        ],
      })
    );
    usePlugins.mockReturnValue(hook({ importPlugin }));
    const user = userEvent.setup();
    const { container } = renderSection();

    const input = container.querySelector('[data-testid="plugin-file-input"]');
    expect(input).not.toBeNull();
    await user.upload(
      input as HTMLInputElement,
      new File(['zip-bytes'], 'plugin.zip', { type: 'application/zip' })
    );

    await waitFor(() =>
      expect(screen.getByText('settings.plugins.report_title')).toBeInTheDocument()
    );
    expect(screen.getByText('summarize')).toBeInTheDocument();
    expect(screen.getByText('local')).toBeInTheDocument();
    expect(screen.getByText('settings.plugins.status.installed')).toBeInTheDocument();
    expect(screen.getByText('settings.plugins.status.skipped')).toBeInTheDocument();
    expect(
      screen.getByText('settings.plugins.reasons.server_transport_unsupported')
    ).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalled();
  });

  it('surfaces an import failure as an error toast, never silently', async () => {
    const importPlugin = vi.fn().mockRejectedValue(new Error('Invalid plugin package'));
    usePlugins.mockReturnValue(hook({ importPlugin }));
    const user = userEvent.setup();
    const { container } = renderSection();

    const input = container.querySelector('[data-testid="plugin-file-input"]');
    await user.upload(
      input as HTMLInputElement,
      new File(['zip'], 'plugin.zip', { type: 'application/zip' })
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Invalid plugin package'));
    expect(screen.queryByText('settings.plugins.report_title')).not.toBeInTheDocument();
  });
});
