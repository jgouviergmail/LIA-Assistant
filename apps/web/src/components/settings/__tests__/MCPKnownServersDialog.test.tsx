/**
 * The known servers' gallery: one tile each — the vendor's icon, the server's
 * name, how one signs in, what it is for — and a server the person already has
 * greyed and badged « Installed », never picked again.
 */
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { KnownMCPServer } from '@/lib/mcp-known-servers';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { MCPKnownServersDialog } from '../MCPKnownServersDialog';

const english = createInstance();
await english.init({ lng: 'en', resources: { en: { translation: en } } });
const french = createInstance();
await french.init({ lng: 'fr', resources: { fr: { translation: fr } } });

const NOTION: KnownMCPServer = {
  key: 'notion',
  name: 'Notion',
  url: 'https://mcp.notion.com/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's Notion workspace.",
  icon: 'notion.png',
};
const CALA: KnownMCPServer = {
  key: 'cala',
  name: 'Cala',
  url: 'https://api.cala.ai/mcp/',
  auth_type: 'api_key',
  domain_description: 'Verified knowledge.',
  icon: 'cala.png',
  header_name: 'X-API-Key',
};
const GITHUB: KnownMCPServer = {
  key: 'github',
  name: 'GitHub',
  url: 'https://api.githubcopilot.com/mcp/',
  auth_type: 'oauth2',
  domain_description: "The person's GitHub.",
  icon: 'github.svg',
  oauth_scopes: 'repo',
  own_oauth_client: true,
};
const EXA: KnownMCPServer = {
  key: 'exa',
  name: 'Exa',
  url: 'https://mcp.exa.ai/mcp',
  auth_type: 'none',
  domain_description: 'Web search.',
};

const onPick = vi.fn();
const onClose = vi.fn();

function render({
  servers = [CALA, EXA, GITHUB, NOTION],
  loading = false,
  installed = new Set<string>(),
  t = english.t,
}: {
  servers?: KnownMCPServer[];
  loading?: boolean;
  installed?: ReadonlySet<string>;
  t?: typeof english.t;
} = {}) {
  return renderWithProviders(
    <MCPKnownServersDialog
      servers={servers}
      loading={loading}
      installed={installed}
      onPick={onPick}
      onClose={onClose}
      t={t}
    />
  );
}

const known = en.settings.mcp.known;
const tile = (name: string) => screen.getByRole('button', { name });

beforeEach(() => vi.clearAllMocks());

describe('the known servers gallery', () => {
  it('is a dialog named « Known servers », one tile per server, in the catalogue order', () => {
    render();

    const dialog = screen.getByRole('dialog', { name: known.title });
    const names = within(dialog)
      .getAllByRole('listitem')
      .map(item => within(item).getByRole('button').getAttribute('aria-labelledby'))
      .map(id => document.getElementById(id ?? '')?.textContent);
    expect(names).toEqual(['Cala', 'Exa', 'GitHub', 'Notion']);
  });

  it('describes a tile by how one signs in and what the server is for', () => {
    render();

    expect(tile('Notion')).toHaveAccessibleDescription(
      `${known.scheme.oauth2} ${known.servers.notion}`
    );
    expect(tile('Cala')).toHaveAccessibleDescription(
      `${known.scheme.api_key} ${known.servers.cala}`
    );
    expect(tile('GitHub')).toHaveAccessibleDescription(
      `${known.scheme.oauth2_own} ${known.servers.github}`
    );
    expect(tile('Exa')).toHaveAccessibleDescription(`${known.scheme.none} ${known.servers.exa}`);
  });

  it('shows the vendor’s own icon from this application, and a generic glyph without one', () => {
    render();

    const icon = tile('Notion').querySelector('img');
    expect(icon).toHaveAttribute('src', '/mcp-icons/notion.png');
    // Decorative: the name beside it names the server.
    expect(icon).toHaveAttribute('alt', '');
    expect(tile('Exa').querySelector('img')).toBeNull();
    expect(tile('Exa').querySelector('svg')).not.toBeNull();
  });

  it('opens the create form of the server picked, by pointer or by keyboard', async () => {
    const { user } = render();

    await user.click(tile('Notion'));
    expect(onPick).toHaveBeenCalledWith(NOTION);

    tile('Cala').focus();
    await user.keyboard('{Enter}');
    expect(onPick).toHaveBeenLastCalledWith(CALA);

    tile('Exa').focus();
    await user.keyboard(' ');
    expect(onPick).toHaveBeenLastCalledWith(EXA);
  });

  it('greys a server already installed, badges it, and never picks it again', async () => {
    const { user } = render({ installed: new Set(['notion']) });

    const notion = tile('Notion');
    expect(notion).toHaveAttribute('aria-disabled', 'true');
    // Still in the tab order, so the reason is read where the focus lands.
    expect(notion).not.toBeDisabled();
    expect(notion).toHaveAccessibleDescription(
      `${known.installed_hint} ${known.scheme.oauth2} ${known.servers.notion}`
    );
    expect(within(notion).getByText(known.installed)).toBeVisible();

    await user.click(notion);
    notion.focus();
    await user.keyboard('{Enter}');
    expect(onPick).not.toHaveBeenCalled();

    expect(tile('Cala')).not.toHaveAttribute('aria-disabled');
    expect(within(tile('Cala')).queryByText(known.installed)).toBeNull();
  });

  it('names the same things in French', () => {
    render({ installed: new Set(['cala']), t: french.t });

    const frKnown = fr.settings.mcp.known;
    expect(screen.getByRole('dialog', { name: frKnown.title })).toBeInTheDocument();
    expect(tile('Cala')).toHaveAccessibleDescription(
      `${frKnown.installed_hint} ${frKnown.scheme.api_key} ${frKnown.servers.cala}`
    );
    expect(within(tile('Cala')).getByText(frKnown.installed)).toBeVisible();
  });

  it('waits on a catalogue still on its way, and says when it could not be read', () => {
    const { unmount } = render({ servers: [], loading: true });
    // The spinner names itself through the global i18n stub, which echoes the key.
    expect(screen.getByLabelText('common.loading')).toBeInTheDocument();
    expect(screen.queryByRole('listitem')).toBeNull();
    unmount();

    render({ servers: [], loading: false });
    expect(screen.getByRole('status')).toHaveTextContent(known.unavailable);
  });

  it('closes on Escape without picking anything', async () => {
    const { user } = render();

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onPick).not.toHaveBeenCalled();
  });
});
