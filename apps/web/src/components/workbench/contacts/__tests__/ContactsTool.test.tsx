/**
 * The « Tools » contacts screen (ADR-369, Task 7.2, D4).
 *
 * A search runs on Enter, never per key, and a page answered in one go says
 * when it may hold more; the group filter exists where the provider has
 * groups. « See the relationship » appears only on an EXACT fold — both keys
 * from the API. A change sends only the list it changed, and a list stops at
 * the provider's own bound.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  WorkbenchAvailability,
  WorkbenchContact,
  WorkbenchFeature,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/contacts',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { WorkbenchShell } from '../../WorkbenchShell';
import { ContactsTool } from '../ContactsTool';

const GOOGLE: WorkbenchFeature[] = ['multi_valued', 'contact_groups', 'other_contacts'];
const GRAPH: WorkbenchFeature[] = ['multi_valued'];

let features: WorkbenchFeature[];
let bounds: Record<string, number>;
let page: { items: WorkbenchContact[]; next_page_token: string | null; truncated: boolean };

const ANA: WorkbenchContact = {
  id: 'people/c1',
  name: 'Ana Lima',
  given_name: 'Ana',
  family_name: 'Lima',
  email: 'ana@example.org',
  phone: '+33 6 12',
  organization: 'Atlas',
  name_key: 'ana lima',
  emails: [{ value: 'ana@example.org', type: 'work' }],
  phones: [{ value: '+33 6 12', type: 'mobile' }],
  addresses: [],
  notes: null,
};

function rail(): WorkbenchAvailability {
  return {
    tools: [{ tool: 'contacts', state: 'ready', provider: 'google_contacts', features, bounds }],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      calendar_window_max_events: 500,
    },
  };
}

let relations: { display_name: string; name_key: string }[];

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  features = GOOGLE;
  bounds = { name_max_chars: 512, notes_max_chars: 8192, value_max_chars: 320, values_max: 20 };
  page = { items: [ANA], next_page_token: null, truncated: false };
  relations = [{ display_name: 'Ana LIMA', name_key: 'ana lima' }];
  api.get.mockImplementation((path: string) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/contacts') return Promise.resolve(page);
    if (path === '/workbench/contacts/groups') {
      return Promise.resolve({ groups: [{ id: 'contactGroups/f', name: 'Friends', count: 7 }] });
    }
    if (path === '/workbench/contacts/contact') return Promise.resolve(ANA);
    if (path === '/relations')
      return Promise.resolve({ relations, relations_total: relations.length });
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue(ANA);
});

function screenOf() {
  return renderWithProviders(
    <WorkbenchShell lng="en">
      <ContactsTool lng="en" />
    </WorkbenchShell>
  );
}

function listCalls(): Array<Record<string, unknown>> {
  return api.get.mock.calls
    .filter(([path]) => path === '/workbench/contacts')
    .map(([, options]) => (options as { params: Record<string, unknown> }).params);
}

describe('ContactsTool — names', () => {
  /** Owner request (2026-10-31): « Given Family », in the order the API sorted. */
  it('draws each contact as « Given Family », in the order the API answers', async () => {
    const morel = {
      ...ANA,
      id: 'people/c2',
      name: 'Morel, Bruno',
      given_name: 'Bruno',
      family_name: 'Morel',
      name_key: 'morel, bruno',
    };
    page = {
      items: [{ ...ANA, name: 'Lima, Ana' }, morel],
      next_page_token: null,
      truncated: false,
    };
    screenOf();

    await screen.findByRole('link', { name: /Ana Lima/ });
    // Each row leads with its name; the line under it is the contact's details.
    const names = screen
      .getAllByRole('link')
      .map(link => link.firstElementChild?.textContent ?? '')
      .filter(name => name.includes('Lima') || name.includes('Morel'));
    expect(names).toEqual(['Ana Lima', 'Bruno Morel']);
    expect(screen.queryByText('Lima, Ana')).toBeNull();
  });

  it('heads the open contact « Given Family » too', async () => {
    nav.search = 'contact=people%2Fc1';
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/contact')
        return Promise.resolve({ ...ANA, name: 'Lima, Ana' });
      if (path === '/relations') return Promise.resolve({ relations, relations_total: 1 });
      return Promise.resolve({});
    });
    screenOf();

    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Lima' })).toBeVisible();
  });
});

describe('ContactsTool — the list', () => {
  it('searches the words on Enter, never on every key', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });
    const box = screen.getByRole('searchbox', { name: 'workbench.contacts.search_label' });

    await user.type(box, 'ana');
    expect(listCalls().every(params => !('q' in params))).toBe(true);
    await user.keyboard('{Enter}');

    await waitFor(() => expect(listCalls().at(-1)).toEqual({ q: 'ana' }));
  });

  it('says a page answered in one go may hold more', async () => {
    page = { ...page, truncated: true };
    screenOf();

    expect(await screen.findByText('workbench.contacts.truncated')).toBeInTheDocument();
  });

  it('lists a group where the provider has groups, and offers none elsewhere', async () => {
    const { user } = screenOf();
    const filter = await screen.findByRole('combobox', { name: 'workbench.contacts.filter_label' });
    await within(filter).findByRole('option', { name: 'Friends (7)' });

    await user.selectOptions(filter, 'contactGroups/f');

    await waitFor(() => expect(listCalls().at(-1)).toEqual({ group: 'contactGroups/f' }));
  });

  it('offers no filter where the provider has neither groups nor other contacts', async () => {
    features = GRAPH;
    screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });

    expect(screen.queryByRole('combobox', { name: 'workbench.contacts.filter_label' })).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/contacts/groups', expect.anything());
  });
});

describe('ContactsTool — the open contact', () => {
  beforeEach(() => {
    nav.search = 'contact=people%2Fc1';
  });

  it('links its relationship when the API folds both names to one key', async () => {
    screenOf();

    const link = await screen.findByRole('link', { name: 'workbench.contacts.see_relation' });
    expect(link.getAttribute('href')).toBe('/en/dashboard/relations?name=Ana+LIMA');
  });

  it('links nothing on a name that only resembles a relation’s', async () => {
    relations = [{ display_name: 'Ana Lima-Costa', name_key: 'ana lima-costa' }];
    screenOf();
    await screen.findByRole('article', { name: 'Ana Lima' });

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/relations', expect.anything()));
    expect(screen.queryByRole('link', { name: 'workbench.contacts.see_relation' })).toBeNull();
  });

  it('sends only the list it changed', async () => {
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.edit' }));

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.lists.phones_add' }));
    const phones = screen.getAllByLabelText('workbench.contacts.lists.phones_value');
    await user.type(phones[1], '+33 1 00');
    await user.click(screen.getByRole('button', { name: 'workbench.contacts.editor.save' }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toEqual({
      id: 'people/c1',
      phones: [
        { value: '+33 6 12', type: 'mobile' },
        { value: '+33 1 00', type: 'mobile' },
      ],
    });
  });

  it('keeps an address’s lines: shown, edited and sent as written', async () => {
    const lines = '3 place de la Bourse\n69002 Lyon';
    const withAddress = { ...ANA, addresses: [{ formatted: lines, type: 'Bureau' }] };
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/groups') return Promise.resolve({ groups: [] });
      if (path === '/workbench/contacts/contact') return Promise.resolve(withAddress);
      if (path === '/relations') return Promise.resolve({ relations, relations_total: 1 });
      return Promise.resolve({});
    });
    const { user } = screenOf();
    const article = await screen.findByRole('article', { name: 'Ana Lima' });
    expect(within(article).getByText((_, node) => node?.textContent === lines)).toBeInTheDocument();

    await user.click(within(article).getByRole('button', { name: 'workbench.contacts.edit' }));
    const field = screen.getByRole('textbox', { name: 'workbench.contacts.lists.addresses_value' });
    expect(field.tagName).toBe('TEXTAREA');
    expect(field).toHaveValue(lines);
    await user.type(field, '{Enter}France');
    await user.click(screen.getByRole('button', { name: 'workbench.contacts.editor.save' }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toEqual({
      id: 'people/c1',
      addresses: [{ formatted: `${lines}\nFrance`, type: 'Bureau' }],
    });
  });

  it('stops a list at the provider’s own bound', async () => {
    features = GRAPH;
    bounds = { ...bounds, emails_max: 1 };
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.edit' }));

    expect(
      screen.queryByRole('button', { name: 'workbench.contacts.lists.emails_add' })
    ).toBeNull();
    expect(screen.getByText('workbench.contacts.values_full')).toBeInTheDocument();
  });
});

describe('ContactsTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    const separator = await screen.findByRole('separator', {
      name: 'workbench.panes.contacts_list',
    });
    const pane = document.getElementById(separator.getAttribute('aria-controls') ?? '');

    expect(within(pane as HTMLElement).getByRole('searchbox')).toBeInTheDocument();
    fireEvent.keyDown(separator, { key: 'End' });
    expect(pane?.style.getPropertyValue('--pane-w')).toMatch(/^\d+px$/);
    fireEvent.keyDown(separator, { key: 'Enter' });
    expect(pane?.style.getPropertyValue('--pane-w')).toBe('');
  });
});
