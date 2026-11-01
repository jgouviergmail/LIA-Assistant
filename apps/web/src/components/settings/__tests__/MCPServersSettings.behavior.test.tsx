/**
 * MCPServersSettings — who decides when LIA asks, and what a server will do
 * (spec 2026-10-30 § 1-4 and 6).
 *
 * The page holds no rule: the account's strategy and each server's choices are
 * offered as the API's defaults allow, the synthesis is the API's, and every change
 * that makes LIA ask less is listed first — from the API's own `questions_lost` — and
 * applies only once the person confirms. Nothing is locked (owner decision).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import {
  mcpBehaviorFixture,
  mcpDefaultsFixture,
  mcpToolBehaviorFixture,
} from '@/__tests__/fixtures/mcp-behavior';
import { userMCPServerFixture as server } from '@/__tests__/fixtures/mcp-servers';
import type { MCPQuestionLoss, MCPServerBehavior, UserMCPDefaults } from '@/lib/mcp-behavior';

// The page's sentences quote what the defaults currently give: this `t` shows the
// interpolated value so a test can read it. Built once — a stable `t`, like the real one.
vi.mock('@/i18n/client', () => {
  const t = (key: string, options?: { value?: unknown }) =>
    options?.value === undefined ? key : `${key}[${String(options.value)}]`;
  const stub = { t, i18n: { language: 'en', changeLanguage: () => undefined } };
  return { useTranslation: () => stub };
});
vi.mock('@/hooks/useAppConfig', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useAppConfig')>();
  const { appConfigFixture } = await import('@/__tests__/fixtures/app-config');
  const config = appConfigFixture();
  const useAppConfig: typeof original.useAppConfig = (enabled = true) => ({
    config: enabled ? config : null,
    loading: false,
    error: null,
  });
  return { ...original, useAppConfig };
});

// A received copy's provenance note dates the share in the viewer's timezone.
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner', timezone: 'UTC' } }) }));
const { useUserMCPServers } = vi.hoisted(() => ({ useUserMCPServers: vi.fn() }));
vi.mock('@/hooks/useUserMCPServers', () => ({ useUserMCPServers }));
const { useMCPServerBehavior, useMCPBehaviorPreview, useMCPToolChoice, previews, choices } =
  vi.hoisted(() => ({
    useMCPServerBehavior: vi.fn(),
    useMCPBehaviorPreview: vi.fn(),
    useMCPToolChoice: vi.fn(),
    previews: { previewServer: vi.fn(), previewStrategy: vi.fn() },
    choices: { setToolChoice: vi.fn() },
  }));
vi.mock('@/hooks/useMCPServerBehavior', () => ({
  useMCPServerBehavior,
  useMCPBehaviorPreview,
  useMCPToolChoice,
}));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { patch },
}));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { MCPServersSettings } from '../MCPServersSettings';

const C = 'settings.mcp.confirmation';
const D = 'settings.mcp.driver';
const B = 'settings.mcp.behavior';
const L = 'settings.mcp.loosening';

const refetch = vi.fn();
const createServer = vi.fn();
const updateServer = vi.fn();
const testConnection = vi.fn();
const refetchBehavior = vi.fn();

// What only the test result carries: shown, it would mean the bare list came back.
const BARE_LIST_ONLY = 'Deletes a note forever';

const LOSSES: MCPQuestionLoss[] = [
  { server_id: 's1', server_name: 'Notes', tool_name: 'delete_note' },
];

function page({
  servers = [server()],
  defaults = mcpDefaultsFixture(),
  behavior = mcpBehaviorFixture(),
}: {
  servers?: ReturnType<typeof server>[];
  /** null: the list has not been read yet. */
  defaults?: UserMCPDefaults | null;
  behavior?: MCPServerBehavior;
} = {}) {
  useUserMCPServers.mockReturnValue({
    ownerId: 'owner',
    servers,
    total: servers.length,
    defaults: defaults ?? undefined,
    loading: false,
    refetch,
    createServer,
    updateServer,
    deleteServer: vi.fn(),
    toggleServer: vi.fn(),
    testConnection,
    initiateOAuth: vi.fn(),
    disconnectOAuth: vi.fn(),
    generateDescription: vi.fn(),
    creating: false,
    updating: false,
    deleting: false,
    testing: false,
    disconnecting: false,
    generatingDescription: false,
  });
  useMCPServerBehavior.mockReturnValue({
    behavior,
    loading: false,
    error: null,
    refetch: refetchBehavior,
  });
  return renderWithProviders(<MCPServersSettings lng="en" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  useMCPBehaviorPreview.mockReturnValue(previews);
  useMCPToolChoice.mockReturnValue(choices);
  choices.setToolChoice.mockResolvedValue(undefined);
  previews.previewServer.mockResolvedValue({ behavior: mcpBehaviorFixture(), questions_lost: [] });
  previews.previewStrategy.mockResolvedValue({ questions_lost: [] });
  patch.mockResolvedValue({});
  updateServer.mockResolvedValue(server());
  createServer.mockResolvedValue(server());
});

describe('the account strategy', () => {
  it('a never-chosen account follows the instance default, and says what it is', () => {
    page({ defaults: mcpDefaultsFixture({ confirmation_instance: true }) });

    const group = screen.getByRole('group', { name: `${C}.strategy_legend` });
    const inherit = within(group).getByRole('radio', { name: `${C}.options.inherit.label` });
    expect(inherit).toBeChecked();
    expect(inherit).toHaveAccessibleDescription(
      `${C}.options.inherit.description[${C}.current_always]`
    );
  });

  it('a change that makes LIA ask more applies at once and re-reads the list', async () => {
    const { user } = page();

    await user.click(screen.getByRole('radio', { name: `${C}.options.always.label` }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/owner', { mcp_hitl_required: true }, undefined)
    );
    expect(previews.previewStrategy).toHaveBeenCalledWith(true);
    expect(refetch).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(`${C}.saved`);
  });

  it('a change that makes LIA ask less is listed first and applies only once confirmed', async () => {
    previews.previewStrategy.mockResolvedValue({ questions_lost: LOSSES });
    const { user } = page({ defaults: mcpDefaultsFixture({ confirmation_account: true }) });

    await user.click(screen.getByRole('radio', { name: `${C}.options.as_declared.label` }));

    const alert = await screen.findByRole('alertdialog', { name: `${L}.title` });
    expect(within(alert).getByText('delete_note')).toBeInTheDocument();
    // One row per tool: a tool asked about is asked in both modes (owner decision 2026-10-31).
    expect(within(alert).getAllByRole('listitem')).toHaveLength(1);
    expect(within(alert).getByText(/Notes/)).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
    await user.click(within(alert).getByRole('button', { name: `${L}.confirm` }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/owner', { mcp_hitl_required: false }, undefined)
    );
  });

  it('while a choice is checked, the group stays focusable and ignores another choice', async () => {
    // `disabled` would blur the focused radio to <body>; the alert could not hand it back.
    let release!: (value: { questions_lost: MCPQuestionLoss[] }) => void;
    previews.previewStrategy.mockReturnValue(new Promise(resolve => (release = resolve)));
    const { user } = page();

    await user.click(screen.getByRole('radio', { name: `${C}.options.always.label` }));
    const group = screen.getByRole('group', { name: `${C}.strategy_legend` });
    expect(group).toHaveAttribute('aria-busy', 'true');
    expect(group).not.toBeDisabled();
    await user.click(screen.getByRole('radio', { name: `${C}.options.as_declared.label` }));
    expect(previews.previewStrategy).toHaveBeenCalledTimes(1);

    release({ questions_lost: [] });
    await waitFor(() => expect(group).toHaveAttribute('aria-busy', 'false'));
  });

  it('says nothing about the strategy before the defaults are read', () => {
    page({ defaults: null });

    expect(screen.queryByRole('group', { name: `${C}.strategy_legend` })).not.toBeInTheDocument();
  });

  it('cancelling the alert changes nothing', async () => {
    previews.previewStrategy.mockResolvedValue({ questions_lost: LOSSES });
    const { user } = page({ defaults: mcpDefaultsFixture({ confirmation_account: true }) });

    await user.click(screen.getByRole('radio', { name: `${C}.options.inherit.label` }));
    const alert = await screen.findByRole('alertdialog');
    await user.click(within(alert).getByRole('button', { name: 'common.cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(patch).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: `${C}.options.always.label` })).toBeChecked();
  });
});

describe('a server form', () => {
  async function openEdit(user: ReturnType<typeof page>['user']) {
    await user.click(screen.getByRole('button', { name: 'common.edit' }));
    return screen.findByRole('dialog', { name: 'settings.mcp.edit_title' });
  }

  it('offers its confirmation and who drives it, where the switch was', async () => {
    const { user } = page({ defaults: mcpDefaultsFixture({ confirmation_effective: true }) });
    const dialog = await openEdit(user);

    const confirmation = within(dialog).getByRole('group', { name: `${C}.server_legend` });
    const inherit = within(confirmation).getByRole('radio', {
      name: `${C}.server_options.inherit.label`,
    });
    expect(inherit).toBeChecked();
    expect(inherit).toHaveAccessibleDescription(
      `${C}.server_options.inherit.description[${C}.current_always]`
    );
    const driver = within(dialog).getByRole('group', { name: `${D}.legend` });
    expect(within(driver).getAllByRole('radio')).toHaveLength(3);
    expect(within(driver).getByRole('radio', { name: `${D}.options.direct.label` })).toBeChecked();
    expect(within(dialog).queryByRole('switch')).not.toBeInTheDocument();
  });

  it('with dedicated agents off, the two agent choices are disabled and say why', async () => {
    const { user } = page({
      defaults: mcpDefaultsFixture({ dedicated_agents_available: false }),
    });
    const dialog = await openEdit(user);

    for (const choice of ['pipeline_agent', 'agent_everywhere']) {
      const radio = within(dialog).getByRole('radio', { name: `${D}.options.${choice}.label` });
      expect(radio).toBeDisabled();
      expect(radio).toHaveAccessibleDescription(`${D}.unavailable.dedicated_agents_off`);
    }
  });

  it('an MCP App keeps its dedicated agent in ReAct: the mixed choice says why', async () => {
    const { user } = page({ behavior: mcpBehaviorFixture({ notes: ['mcp_app'] }) });
    const dialog = await openEdit(user);

    const mixed = within(dialog).getByRole('radio', { name: `${D}.options.pipeline_agent.label` });
    expect(mixed).toBeDisabled();
    expect(mixed).toHaveAccessibleDescription(`${D}.unavailable.mcp_app`);
  });

  it('shows what the server will do, following the form before saving', async () => {
    previews.previewServer.mockResolvedValue({
      behavior: mcpBehaviorFixture({
        confirmation: { always: true, source: 'server' },
        tools: [mcpToolBehaviorFixture({ reason: 'server_always' })],
      }),
      questions_lost: [],
    });
    const { user } = page();
    const dialog = await openEdit(user);
    expect(within(dialog).getByText(`${B}.reasons.declared_destructive`)).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole('radio', { name: `${C}.server_options.always.label` })
    );

    expect(await within(dialog).findByText(`${B}.reasons.server_always`)).toBeInTheDocument();
    expect(previews.previewServer).toHaveBeenCalledWith('s1', { hitl_required: true });
    expect(updateServer).not.toHaveBeenCalled();
  });

  it('a change that makes LIA ask less is listed first and saved only once confirmed', async () => {
    previews.previewServer.mockResolvedValue({
      behavior: mcpBehaviorFixture(),
      questions_lost: LOSSES,
    });
    const { user } = page({ servers: [server({ hitl_required: true })] });
    const dialog = await openEdit(user);

    await user.click(
      within(dialog).getByRole('radio', { name: `${C}.server_options.as_declared.label` })
    );
    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));

    const alert = await screen.findByRole('alertdialog', { name: `${L}.title` });
    expect(updateServer).not.toHaveBeenCalled();
    await user.click(within(alert).getByRole('button', { name: `${L}.confirm` }));
    await waitFor(() => expect(updateServer).toHaveBeenCalledWith('s1', { hitl_required: false }));
  });

  it('cancelling the alert keeps the form open and saves nothing', async () => {
    previews.previewServer.mockResolvedValue({
      behavior: mcpBehaviorFixture(),
      questions_lost: LOSSES,
    });
    const { user } = page({ servers: [server({ hitl_required: true })] });
    const dialog = await openEdit(user);
    await user.click(
      within(dialog).getByRole('radio', { name: `${C}.server_options.as_declared.label` })
    );
    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));

    const alert = await screen.findByRole('alertdialog');
    await user.click(within(alert).getByRole('button', { name: 'common.cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(updateServer).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'settings.mcp.edit_title' })).toBeInTheDocument();
  });

  it('a driver change writes the mode and the shape it implies, nothing else', async () => {
    const { user } = page();
    const dialog = await openEdit(user);

    await user.click(
      within(dialog).getByRole('radio', { name: `${D}.options.agent_everywhere.label` })
    );
    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));

    await waitFor(() =>
      expect(updateServer).toHaveBeenCalledWith('s1', {
        iterative_mode: true,
        react_expand_iterative: false,
      })
    );
  });

  it('a new server is created with the chosen driver, nothing previewed', async () => {
    const { user } = page({ servers: [] });
    await user.click(screen.getByRole('button', { name: 'settings.mcp.add_server' }));
    const dialog = await screen.findByRole('dialog', { name: 'settings.mcp.add_title' });

    await user.type(within(dialog).getByLabelText('settings.mcp.field_name'), 'Notes');
    await user.type(
      within(dialog).getByLabelText('settings.mcp.field_url'),
      'https://n.example/mcp'
    );
    await user.click(
      within(dialog).getByRole('radio', { name: `${D}.options.pipeline_agent.label` })
    );
    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));

    await waitFor(() =>
      expect(createServer).toHaveBeenCalledWith(
        expect.objectContaining({ iterative_mode: true, react_expand_iterative: true })
      )
    );
    expect(previews.previewServer).not.toHaveBeenCalled();
  });

  it('a connection test re-reads the synthesis instead of listing bare tools', async () => {
    testConnection.mockResolvedValue({
      success: true,
      tool_count: 1,
      tools: [{ tool_name: 'delete_note', description: BARE_LIST_ONLY, input_schema: {} }],
    });
    const { user } = page();
    const dialog = await openEdit(user);

    await user.click(within(dialog).getByRole('button', { name: 'settings.mcp.test_connection' }));

    await waitFor(() => expect(refetchBehavior).toHaveBeenCalled());
    expect(within(dialog).queryByText(BARE_LIST_ONLY)).not.toBeInTheDocument();
  });
});

describe('the choice of each tool, in the server form (owner decision 2026-10-31)', () => {
  async function openEdit(user: ReturnType<typeof page>['user']) {
    await user.click(screen.getByRole('button', { name: 'common.edit' }));
    return screen.findByRole('dialog', { name: 'settings.mcp.edit_title' });
  }

  it('is previewed with the form, alerts once, and is written only on save', async () => {
    previews.previewServer.mockResolvedValue({
      behavior: mcpBehaviorFixture(),
      questions_lost: LOSSES,
    });
    const { user } = page();
    const dialog = await openEdit(user);

    await user.selectOptions(
      within(dialog).getByRole('combobox', { name: `${B}.tool_choice.label` }),
      'never'
    );
    await waitFor(() =>
      expect(previews.previewServer).toHaveBeenCalledWith('s1', {
        tool_choices: { delete_note: 'never' },
      })
    );
    expect(choices.setToolChoice).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));
    const alert = await screen.findByRole('alertdialog', { name: `${L}.title` });
    expect(choices.setToolChoice).not.toHaveBeenCalled();
    await user.click(within(alert).getByRole('button', { name: `${L}.confirm` }));

    await waitFor(() =>
      expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'delete_note', 'never')
    );
    // Nothing else changed: the server row is not written.
    expect(updateServer).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'settings.mcp.edit_title' })).toBeNull()
    );
  });

  it('the select shows the choice made at once, before the preview answers', async () => {
    previews.previewServer.mockReturnValue(new Promise(() => {}));
    const { user } = page();
    const dialog = await openEdit(user);
    const select = within(dialog).getByRole('combobox', { name: `${B}.tool_choice.label` });

    await user.selectOptions(select, 'always');

    expect(select).toHaveValue('always');
  });

  it('cancelling the form writes no choice', async () => {
    const { user } = page();
    const dialog = await openEdit(user);

    await user.selectOptions(
      within(dialog).getByRole('combobox', { name: `${B}.tool_choice.label` }),
      'always'
    );
    await user.click(within(dialog).getByRole('button', { name: 'common.cancel' }));

    expect(choices.setToolChoice).not.toHaveBeenCalled();
    expect(updateServer).not.toHaveBeenCalled();
  });

  it('the server is written first, then its tools’ choices', async () => {
    const { user } = page();
    const dialog = await openEdit(user);
    await user.click(
      within(dialog).getByRole('radio', { name: `${C}.server_options.always.label` })
    );
    await user.selectOptions(
      within(dialog).getByRole('combobox', { name: `${B}.tool_choice.label` }),
      'always'
    );

    await user.click(within(dialog).getByRole('button', { name: 'common.save' }));

    await waitFor(() =>
      expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'delete_note', 'always')
    );
    expect(updateServer).toHaveBeenCalledWith('s1', { hitl_required: true });
    expect(updateServer.mock.invocationCallOrder[0]).toBeLessThan(
      choices.setToolChoice.mock.invocationCallOrder[0]
    );
  });
});

describe('the choice of each tool, from what the server will do', () => {
  const T = `${B}.tool_choice`;

  async function openBehavior(user: ReturnType<typeof page>['user']) {
    await user.click(screen.getByRole('button', { name: `${B}.action` }));
    return screen.findByRole('dialog', { name: `${B}.dialog_title` });
  }

  it('asking less is listed first and written only once confirmed', async () => {
    previews.previewServer.mockResolvedValue({
      behavior: mcpBehaviorFixture(),
      questions_lost: LOSSES,
    });
    const { user } = page();
    const dialog = await openBehavior(user);

    await user.selectOptions(within(dialog).getByRole('combobox', { name: `${T}.label` }), 'never');

    const alert = await screen.findByRole('alertdialog', { name: `${L}.title` });
    expect(previews.previewServer).toHaveBeenCalledWith('s1', {
      tool_choices: { delete_note: 'never' },
    });
    expect(choices.setToolChoice).not.toHaveBeenCalled();
    await user.click(within(alert).getByRole('button', { name: `${L}.confirm` }));
    await waitFor(() =>
      expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'delete_note', 'never')
    );
    expect(refetchBehavior).toHaveBeenCalled();
  });

  it('asking more is written at once', async () => {
    const { user } = page({
      behavior: mcpBehaviorFixture({
        tools: [mcpToolBehaviorFixture({ tool_name: 'read_note', default_asks: false })],
      }),
    });
    const dialog = await openBehavior(user);

    await user.selectOptions(
      within(dialog).getByRole('combobox', { name: `${T}.label` }),
      'always'
    );

    await waitFor(() =>
      expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'read_note', 'always')
    );
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('a received copy shows its tools without offering a choice', () => {
    page({
      servers: [
        server({
          is_enabled: false,
          status: 'inactive',
          shared_origin: {
            sender_display_name: 'Alex',
            shared_at: '2026-10-30T10:00:00Z',
            transfer_id: '00000000-0000-4000-8000-000000000001',
          },
        }),
      ],
    });

    expect(screen.queryByRole('combobox', { name: `${T}.label` })).not.toBeInTheDocument();
  });
});

describe('what a saved server will do', () => {
  it('every card offers it, in a dialog of its own', async () => {
    const { user } = page();

    await user.click(screen.getByRole('button', { name: `${B}.action` }));

    const dialog = await screen.findByRole('dialog', { name: `${B}.dialog_title` });
    expect(within(dialog).getByRole('region', { name: `${B}.title` })).toBeInTheDocument();
    expect(useMCPServerBehavior).toHaveBeenCalledWith('s1');
  });

  it('a copy received from a connection, still off, shows it opened on its card', () => {
    page({
      servers: [
        server({
          is_enabled: false,
          status: 'inactive',
          shared_origin: {
            sender_display_name: 'Alex',
            shared_at: '2026-10-30T10:00:00Z',
            transfer_id: '00000000-0000-4000-8000-000000000001',
          },
        }),
      ],
    });

    const card = screen.getByRole('heading', { name: 'Weather MCP' }).closest('li');
    expect(card).not.toBeNull();
    expect(within(card!).getByRole('region', { name: `${B}.title` })).toBeInTheDocument();
  });

  it('a card says when a tool’s « never ask » is suspended', () => {
    page({ servers: [server({ suspended_tool_choices: 2 })] });

    const card = screen.getByRole('heading', { name: 'Weather MCP' }).closest('li');
    expect(within(card!).getByText(`${B}.suspended_on_card`)).toBeInTheDocument();
  });

  it('a card with no suspended choice says nothing about it', () => {
    page({ servers: [server()] });

    expect(screen.queryByText(`${B}.suspended_on_card`)).not.toBeInTheDocument();
  });

  it('an own server keeps its card closed', () => {
    page({ servers: [server({ is_enabled: false, status: 'inactive' })] });

    expect(screen.queryByRole('region', { name: `${B}.title` })).not.toBeInTheDocument();
  });

  it('a tested server shows its synthesis, not a bare tool list', async () => {
    testConnection.mockResolvedValue({
      success: true,
      tool_count: 1,
      tools: [{ tool_name: 'delete_note', description: BARE_LIST_ONLY, input_schema: {} }],
    });
    const { user } = page();

    await user.click(screen.getByRole('button', { name: 'settings.mcp.test_connection' }));

    const dialog = await screen.findByRole('dialog', { name: 'settings.mcp.test_results_title' });
    expect(within(dialog).getByRole('region', { name: `${B}.title` })).toBeInTheDocument();
    expect(within(dialog).queryByText(BARE_LIST_ONLY)).not.toBeInTheDocument();
  });
});
