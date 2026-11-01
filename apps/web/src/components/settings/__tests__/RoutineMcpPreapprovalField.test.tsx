/**
 * The MCP servers a routine confirms for itself (spec 2026-10-29 D9): one native
 * checkbox per server its runs can call, named by the server, operable from the
 * keyboard; a change never keeps a key the API would refuse.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { RoutineMcpPreapprovalField } from '@/components/settings/RoutineMcpPreapprovalField';
import type { PreapprovableServer } from '@/lib/routines/preapprovable-servers';

const SERVERS: PreapprovableServer[] = [
  { key: 'p-1', name: 'Notes', family: 'personal' },
  { key: 'excalidraw', name: 'Excalidraw', family: 'shared' },
];

describe('RoutineMcpPreapprovalField', () => {
  it('names each callable server and reflects the stored ticks', () => {
    renderWithProviders(
      <RoutineMcpPreapprovalField
        id="sa-mcp"
        value={['p-1']}
        servers={SERVERS}
        onChange={vi.fn()}
      />
    );

    expect(
      screen.getByRole('group', { name: 'scheduled_actions.mcp_preapproval.label' })
    ).toHaveAccessibleDescription('scheduled_actions.mcp_preapproval.hint');
    expect(screen.getByRole('checkbox', { name: /Notes/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Excalidraw/ })).not.toBeChecked();
  });

  it('ticks from the keyboard and drops a key no longer callable', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <RoutineMcpPreapprovalField
        id="sa-mcp"
        value={['gone-server', 'p-1']}
        servers={SERVERS}
        onChange={onChange}
      />
    );

    await user.tab();
    await user.tab();
    expect(screen.getByRole('checkbox', { name: /Excalidraw/ })).toHaveFocus();
    await user.keyboard(' ');

    expect(onChange).toHaveBeenCalledWith(['p-1', 'excalidraw']);
  });

  it('unticks a server', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <RoutineMcpPreapprovalField
        id="sa-mcp"
        value={['p-1']}
        servers={SERVERS}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole('checkbox', { name: /Notes/ }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('says so when no server can be pre-approved', () => {
    renderWithProviders(
      <RoutineMcpPreapprovalField id="sa-mcp" value={[]} servers={[]} onChange={vi.fn()} />
    );

    expect(screen.getByText('scheduled_actions.mcp_preapproval.empty')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});
