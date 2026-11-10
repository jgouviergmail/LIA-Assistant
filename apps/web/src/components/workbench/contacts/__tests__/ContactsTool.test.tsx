/**
 * The « Tools » contacts screen (ADR-369, Task 7.2, D4).
 *
 * A search runs on Enter, never per key, and a page answered in one go says
 * when it may hold more; the group filter exists where the provider has
 * groups. « See the relationship » appears only on an EXACT fold — both keys
 * from the API. A change sends only the list it changed, and a list stops at
 * the provider's own bound.
 */

import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  WorkbenchAvailability,
  WorkbenchContact,
  WorkbenchContactHistory,
  WorkbenchFeature,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast } = vi.hoisted(() => ({
  api: {
    get: vi.fn(),
    getResponse: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
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
vi.mock('sonner', () => ({ toast }));
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

import { handOff, takeHandoff, setHandoffOwner } from '@/lib/workbench/handoff';

import { WorkbenchShell } from '../../WorkbenchShell';
import { ContactsTool } from '../ContactsTool';

/** A contact with nothing exchanged: sources connected, lists empty. */
const NO_HISTORY: WorkbenchContactHistory = {
  mail: 'used',
  received: [],
  sent: [],
  calendar: 'used',
  organized_by_them: [],
  organized_by_you: [],
  shared: [],
  meetings_window_days: 720,
  meetings_cut: false,
  telephony: 'not_requested',
  calls: [],
  calls_window: 500,
  calls_cut: false,
  sms: 'not_requested',
  texts: [],
  texts_window: 2000,
  texts_cut: false,
};

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
  job_title: null,
  website: null,
  birthday: null,
  emails: [{ value: 'ana@example.org', type: 'work' }],
  phones: [{ value: '+33 6 12', type: 'mobile' }],
  addresses: [],
  notes: null,
};

let mailReady: boolean;

function rail(): WorkbenchAvailability {
  const mail = {
    tool: 'mail',
    state: 'ready',
    provider: 'google_gmail',
    features,
    bounds,
  } as const;
  return {
    tools: [
      { tool: 'contacts', state: 'ready', provider: 'google_contacts', features, bounds },
      ...(mailReady ? [mail] : []),
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

let relations: { display_name: string; name_key: string }[];

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  mailReady = false;
  features = GOOGLE;
  bounds = { name_max_chars: 512, notes_max_chars: 8192, value_max_chars: 320, values_max: 20 };
  page = { items: [ANA], next_page_token: null, truncated: false };
  relations = [{ display_name: 'Ana LIMA', name_key: 'ana lima' }];
  api.get.mockImplementation((path: string) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
    if (path === '/workbench/contacts') return Promise.resolve(page);
    if (path === '/workbench/contacts/groups') {
      return Promise.resolve({ groups: [{ id: 'contactGroups/f', name: 'Friends', count: 7 }] });
    }
    if (path === '/workbench/contacts/contact') return Promise.resolve(ANA);
    if (path === '/workbench/contacts/member-of') return Promise.resolve({ groups: [] });
    if (path === '/relations')
      return Promise.resolve({ relations, relations_total: relations.length });
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue(ANA);
  api.getResponse.mockRejectedValue(new Error('no photo'));
});

function tool() {
  return (
    <WorkbenchShell lng="en">
      <ContactsTool lng="en" />
    </WorkbenchShell>
  );
}

function screenOf() {
  return renderWithProviders(tool());
}

/** What the open contact offers in its bar, in the order it is drawn. */
function barActs(): (string | null)[] {
  return Array.from(screen.getByTestId('detail-acts').children).map(act =>
    act.getAttribute('aria-label')
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
      .map(link => link.querySelector('.font-medium')?.textContent ?? '')
      .filter(name => name.includes('Lima') || name.includes('Morel'));
    expect(names).toEqual(['Ana Lima', 'Bruno Morel']);
    expect(screen.queryByText('Lima, Ana')).toBeNull();
  });

  it('heads the open contact « Given Family » too', async () => {
    nav.search = 'contact=people%2Fc1';
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/contact')
        return Promise.resolve({ ...ANA, name: 'Lima, Ana' });
      if (path === '/relations') return Promise.resolve({ relations, relations_total: 1 });
      return Promise.resolve({ groups: [] });
    });
    screenOf();

    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Lima' })).toBeVisible();
  });
});

describe('ContactsTool — groups', () => {
  const FAMILY = { id: 'contactGroups/f', name: 'Family', count: 7, own: true };
  const STARRED = { id: 'contactGroups/s', name: 'Starred', count: 1, own: false };

  /** The filter once a group is offered: it is drawn before the groups arrive. */
  async function filterOffering(group: { name: string; count: number }) {
    const filter = await screen.findByRole('combobox', {
      name: 'workbench.contacts.filter_label',
    });
    await within(filter).findByRole('option', { name: `${group.name} (${group.count})` });
    return filter;
  }

  function answering(memberOf: unknown[] = [FAMILY]) {
    const answers = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options: unknown) => {
      if (path === '/workbench/contacts/groups')
        return Promise.resolve({ groups: [FAMILY, STARRED] });
      if (path === '/workbench/contacts/member-of') return Promise.resolve({ groups: memberOf });
      return answers?.(path, options);
    });
  }

  it('shows the groups of the open contact', async () => {
    nav.search = 'contact=people/c1';
    answering();
    screenOf();

    expect(
      await screen.findByRole('button', { name: 'workbench.contacts.groups.leave' })
    ).toBeInTheDocument();
    expect(screen.getByText('Family', { ignore: 'option' })).toBeInTheDocument();
  });

  it('puts a contact in a group by its name, one nobody holds included', async () => {
    nav.search = 'contact=people/c1';
    answering([]);
    api.post.mockResolvedValue({ id: 'contactGroups/n', name: 'Work', count: null, own: true });
    const { user } = screenOf();

    const name = await screen.findByLabelText('workbench.contacts.groups.add_label');
    await user.type(name, ' Work {Enter}');

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][0]).toBe('/workbench/contacts/groups/join');
    expect(api.post.mock.calls[0][1]).toEqual({ contact_id: 'people/c1', name: 'Work' });
    await waitFor(() => expect(name).toHaveValue(''));
  });

  it('takes a contact out, and says a failure', async () => {
    nav.search = 'contact=people/c1';
    answering();
    api.post.mockRejectedValueOnce(new Error('offline'));
    api.post.mockResolvedValue(undefined);
    const { user } = screenOf();
    const leave = await screen.findByRole('button', { name: 'workbench.contacts.groups.leave' });

    await user.click(leave);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await user.click(leave);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1]).toEqual(
      expect.arrayContaining([
        '/workbench/contacts/groups/leave',
        { contact_id: 'people/c1', group_id: 'contactGroups/f' },
      ])
    );
  });

  it('renames the group chosen', async () => {
    answering();
    api.patch.mockResolvedValue(undefined);
    const { user } = screenOf();
    await user.selectOptions(await filterOffering(FAMILY), FAMILY.id);

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.groups.rename' }));
    const name = await screen.findByLabelText('workbench.contacts.groups.name');
    await user.clear(name);
    await user.type(name, 'Kin');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][0]).toBe('/workbench/contacts/groups');
    expect(api.patch.mock.calls[0][1]).toEqual({ id: FAMILY.id, name: 'Kin' });
  });

  it('deletes the group chosen after asking, and goes back to everyone', async () => {
    answering();
    api.delete.mockResolvedValue(undefined);
    const { user } = screenOf();
    const filter = await filterOffering(FAMILY);
    await user.selectOptions(filter, FAMILY.id);

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.groups.delete' }));
    await answerConfirmDialog(user);

    await waitFor(() => expect(api.delete).toHaveBeenCalled());
    expect(api.delete.mock.calls[0][0]).toBe('/workbench/contacts/groups');
    await waitFor(() => expect(filter).toHaveValue(''));
  });

  it('changes nothing of a group Google keeps for itself', async () => {
    answering();
    const { user } = screenOf();
    await user.selectOptions(await filterOffering(STARRED), STARRED.id);

    expect(screen.queryByRole('button', { name: 'workbench.contacts.groups.rename' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'workbench.contacts.groups.delete' })).toBeNull();
  });
});

describe('ContactsTool — a contact’s photo', () => {
  const picture = () => new File(['pixels'], 'me.png', { type: 'image/png' });
  const answered = () => ({ blob: () => Promise.resolve(new Blob(['x'])) });

  beforeEach(() => {
    nav.search = 'contact=people/c1';
    URL.createObjectURL = vi.fn(() => 'blob:photo');
    URL.revokeObjectURL = vi.fn();
  });

  it('draws the photo the provider holds, read through the API', async () => {
    api.getResponse.mockResolvedValue(answered());
    screenOf();

    const image = await screen.findByRole('img', { name: 'Ana Lima' });
    expect(image).toHaveAttribute('src', 'blob:photo');
    expect(api.getResponse.mock.calls[0][0]).toBe('/workbench/contacts/photo');
    expect(api.getResponse.mock.calls[0][1].params).toEqual({ id: 'people/c1' });
    expect(
      screen.getByRole('button', { name: 'workbench.contacts.photo_remove' })
    ).toBeInTheDocument();
  });

  it('keeps the initials where there is none, and offers none to remove', async () => {
    screenOf();

    await screen.findByRole('heading', { name: 'Ana Lima' });
    await waitFor(() => expect(api.getResponse).toHaveBeenCalled());
    expect(screen.queryByRole('img', { name: 'Ana Lima' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'workbench.contacts.photo_remove' })).toBeNull();
    expect(screen.getByRole('button', { name: 'workbench.contacts.photo_change' })).toBeVisible();
  });

  it('sends a new one and reads it back', async () => {
    api.put.mockResolvedValue(undefined);
    const { user } = screenOf();
    await screen.findByRole('heading', { name: 'Ana Lima' });
    await waitFor(() => expect(api.getResponse).toHaveBeenCalledTimes(1));
    api.getResponse.mockResolvedValue(answered());

    await user.upload(screen.getByLabelText('workbench.contacts.photo_file'), picture());

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [path, form] = api.put.mock.calls[0];
    expect(path).toBe('/workbench/contacts/photo');
    expect((form as FormData).get('id')).toBe('people/c1');
    expect((form as FormData).get('file')).toBeInstanceOf(File);
    expect(await screen.findByRole('img', { name: 'Ana Lima' })).toBeInTheDocument();
  });

  it('refuses unsent a picture past its published ceiling', async () => {
    bounds = { ...bounds, photo_max_bytes: 2 };
    const { user } = screenOf();
    await screen.findByRole('heading', { name: 'Ana Lima' });

    await user.upload(screen.getByLabelText('workbench.contacts.photo_file'), picture());

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(api.put).not.toHaveBeenCalled();
  });

  it('takes it off', async () => {
    api.getResponse.mockResolvedValue(answered());
    api.delete.mockResolvedValue(undefined);
    const { user } = screenOf();
    await screen.findByRole('img', { name: 'Ana Lima' });
    api.getResponse.mockRejectedValue(new Error('no photo'));

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.photo_remove' }));

    await waitFor(() => expect(api.delete).toHaveBeenCalled());
    expect(api.delete.mock.calls[0][0]).toBe('/workbench/contacts/photo');
    await waitFor(() => expect(screen.queryByRole('img', { name: 'Ana Lima' })).toBeNull());
  });

  it('says a failure in its own words and keeps what is shown', async () => {
    api.getResponse.mockResolvedValue(answered());
    api.delete.mockRejectedValue(new Error('offline'));
    const { user } = screenOf();
    await screen.findByRole('img', { name: 'Ana Lima' });

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.photo_remove' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole('img', { name: 'Ana Lima' })).toBeInTheDocument();
  });
});

describe('ContactsTool — a vCard file', () => {
  const card = () => new File(['BEGIN:VCARD'], 'book.vcf', { type: 'text/vcard' });

  it('leaves as a download: the book, and one contact', async () => {
    nav.search = 'contact=people/c1';
    screenOf();

    const whole = await screen.findByRole('link', { name: 'workbench.contacts.export_all' });
    expect(whole.getAttribute('href')).toMatch(/\/workbench\/contacts\/export$/);
    const one = await screen.findByRole('link', { name: 'workbench.contacts.export_one' });
    expect(one.getAttribute('href')).toMatch(/\/workbench\/contacts\/export\?id=people%2Fc1$/);
  });

  it('arrives under one key, says how many, and the list reads them', async () => {
    api.post.mockResolvedValue({ done: 2, failed: [] });
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });
    const before = listCalls().length;

    await user.upload(screen.getByLabelText('workbench.contacts.import_file'), card());

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, form] = api.post.mock.calls[0];
    expect(path).toBe('/workbench/contacts/import');
    expect((form as FormData).get('file')).toBeInstanceOf(File);
    expect((form as FormData).get('idempotency_key')).toEqual(expect.any(String));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.contacts.imported'));
    expect(listCalls().length).toBeGreaterThan(before);
  });

  it('names the cards that did not make it', async () => {
    api.post.mockResolvedValue({
      done: 1,
      failed: [
        { position: 2, name: 'Bea Rossi' },
        { position: 3, name: '' },
      ],
    });
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });

    await user.upload(screen.getByLabelText('workbench.contacts.import_file'), card());

    const report = await screen.findByRole('dialog');
    expect(within(report).getByText('workbench.contacts.import_card')).toBeInTheDocument();
    expect(within(report).getByText('workbench.contacts.import_card_unnamed')).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('refuses unsent a file past its published ceiling', async () => {
    bounds = { ...bounds, import_max_bytes: 4 };
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });

    await user.upload(screen.getByLabelText('workbench.contacts.import_file'), card());

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(api.post).not.toHaveBeenCalled();
  });

  it('says a refusal in its own words, and the same file can be picked again', async () => {
    api.post.mockRejectedValueOnce(new Error('offline'));
    api.post.mockResolvedValue({ done: 1, failed: [] });
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });
    const input = screen.getByLabelText<HTMLInputElement>('workbench.contacts.import_file');

    await user.upload(input, card());
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(input.value).toBe('');
    await user.upload(input, card());

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  });
});

describe('ContactsTool — a contact met in mail', () => {
  const MET = {
    id: 'otherContacts/c9',
    name: 'Bea Costa',
    given_name: null,
    family_name: null,
    email: 'bea@example.org',
    phone: '+33 6 34',
    organization: null,
    name_key: 'bea costa',
  };

  beforeEach(() => {
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/contacts/other'
        ? Promise.resolve({ items: [MET], next_page_token: null, truncated: false })
        : read?.(path, options)
    );
  });

  async function searchMet(user: ReturnType<typeof screenOf>['user']) {
    await user.selectOptions(
      await screen.findByRole('combobox', { name: 'workbench.contacts.filter_label' }),
      'other'
    );
    await user.type(
      screen.getByRole('searchbox', { name: 'workbench.contacts.search_label' }),
      'bea{Enter}'
    );
    await screen.findByRole('link', { name: /Bea Costa/ });
  }

  it('opens from what the search said, asking the provider for nothing', async () => {
    const { user, rerender } = screenOf();
    await searchMet(user);

    nav.search = 'contact=otherContacts%2Fc9';
    rerender(tool());

    const detail = await screen.findByRole('article', { name: 'Bea Costa' });
    expect(within(detail).getByRole('link', { name: 'bea@example.org' })).toHaveAttribute(
      'href',
      'mailto:bea@example.org'
    );
    expect(within(detail).getByText('workbench.contacts.other_read_only')).toBeVisible();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/contacts/contact', expect.anything());
  });

  it('offers neither a change nor a deletion Google would refuse', async () => {
    const { user, rerender } = screenOf();
    await searchMet(user);

    nav.search = 'contact=otherContacts%2Fc9';
    rerender(tool());

    const detail = await screen.findByRole('article', { name: 'Bea Costa' });
    expect(within(detail).queryByRole('button', { name: 'workbench.contacts.edit' })).toBeNull();
    expect(within(detail).queryByRole('button', { name: 'workbench.contacts.delete' })).toBeNull();
    expect(barActs()).toEqual(['workbench.contacts.save_other', 'workbench.ask.label']);
  });

  it('says what to do when the address names one no search listed', async () => {
    nav.search = 'contact=otherContacts%2Fc9';
    screenOf();

    expect(await screen.findByText('workbench.contacts.other_not_listed')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'workbench.states.retry' })).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/contacts/contact', expect.anything());
  });
});

describe('ContactsTool — what an open contact offers', () => {
  it('changes, exports, deletes and asks from its bar', async () => {
    nav.search = 'contact=people/c1';
    screenOf();

    await screen.findByRole('button', { name: 'workbench.contacts.edit' });

    expect(barActs()).toEqual([
      'workbench.contacts.edit',
      'workbench.contacts.export_one',
      'workbench.contacts.delete',
      'workbench.ask.label',
    ]);
    expect(screen.getByRole('button', { name: 'workbench.contacts.delete' })).toHaveClass(
      'text-destructive'
    );
  });
});

describe('ContactsTool — the notes', () => {
  it('lets an address they hold be followed', async () => {
    nav.search = 'contact=people%2Fc1';
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/contact')
        return Promise.resolve({ ...ANA, notes: 'Portfolio: https://ana.example.org/work' });
      if (path === '/relations') return Promise.resolve({ relations, relations_total: 1 });
      return Promise.resolve({ groups: [] });
    });
    screenOf();

    expect(
      await screen.findByRole('link', { name: 'https://ana.example.org/work' })
    ).toHaveAttribute('href', 'https://ana.example.org/work');
  });
});

describe('ContactsTool — the list', () => {
  it('re-reads what it shows when the person asks', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Ana Lima/ });
    api.get.mockClear();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/contacts', expect.anything())
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/contacts/groups', expect.anything())
    );
  });

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

describe('ContactsTool — what a contact holds beyond its lists', () => {
  const held = (contact: Partial<WorkbenchContact>) => {
    nav.search = 'contact=people/c1';
    const answers = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options: unknown) =>
      path === '/workbench/contacts/contact'
        ? Promise.resolve({ ...ANA, ...contact })
        : answers?.(path, options)
    );
    return screenOf();
  };

  it('shows the job beside the company, the website and the birthday', async () => {
    held({
      job_title: 'Engineer',
      website: 'https://ana.example.org',
      birthday: '1990-05-15',
    });

    expect(await screen.findByText('Engineer · Atlas')).toBeInTheDocument();
    const site = screen.getByRole('link', { name: 'https://ana.example.org' });
    expect(site).toHaveAttribute('href', 'https://ana.example.org/');
    expect(site).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(screen.getByText('May 15, 1990')).toBeInTheDocument();
  });

  it('never follows a website no one may follow', async () => {
    held({ website: 'javascript:alert(1)' });

    expect(await screen.findByText('javascript:alert(1)')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).toBeNull();
  });

  it('shows no line for what the contact does not hold', async () => {
    held({});

    await screen.findByRole('heading', { name: 'Ana Lima' });
    expect(screen.queryByText('workbench.contacts.editor.website')).toBeNull();
    expect(screen.queryByText('workbench.contacts.editor.birthday')).toBeNull();
  });

  it('changes what the person changed, and only that', async () => {
    const { user } = held({ job_title: 'Engineer', birthday: '1990-05-15' });
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.edit' }));

    const job = await screen.findByLabelText('workbench.contacts.editor.job_title');
    await user.clear(job);
    await user.type(job, 'CTO');
    await user.click(screen.getByRole('button', { name: 'workbench.contacts.editor.save' }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toEqual({ id: 'people/c1', job_title: 'CTO' });
  });

  it('takes a website with no scheme, as providers hold them', async () => {
    const { user } = held({ website: 'ana.example.org' });
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.edit' }));

    const site = await screen.findByLabelText('workbench.contacts.editor.website');

    expect(site).toHaveValue('ana.example.org');
    expect(site).toBeValid();
    expect(site).not.toHaveAttribute('type', 'url');
  });

  it('takes a birthday off, one with no year included', async () => {
    const { user } = held({ birthday: '--05-15' });
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.edit' }));

    expect(await screen.findByLabelText('workbench.contacts.editor.birthday')).toHaveValue('');
    expect(screen.getByText('workbench.contacts.editor.birthday_no_year')).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'workbench.contacts.editor.birthday_remove' })
    );
    await user.click(screen.getByRole('button', { name: 'workbench.contacts.editor.save' }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toEqual({ id: 'people/c1', clear_birthday: true });
  });

  it('takes a name from its parts on a new contact', async () => {
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.new_contact' }));

    await user.type(await screen.findByLabelText('workbench.contacts.editor.given_name'), 'Ana');
    await user.type(screen.getByLabelText('workbench.contacts.editor.family_name'), 'Lima');
    await user.click(screen.getByRole('button', { name: 'workbench.contacts.editor.create' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({
      name: 'Ana Lima',
      given_name: 'Ana',
      family_name: 'Lima',
    });
  });
});

describe('ContactsTool — a contact met in mail', () => {
  const MET = {
    id: 'otherContacts/c9',
    name: 'Bea Rossi',
    given_name: null,
    family_name: null,
    email: 'bea@example.org',
    phone: null,
    organization: null,
    name_key: 'bea rossi',
  };

  /** The filter on « other contacts », a search answered, the contact opened. */
  async function metInMail() {
    nav.search = `contact=${MET.id}`;
    const answers = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options: unknown) =>
      path === '/workbench/contacts/other'
        ? Promise.resolve({ items: [MET], next_page_token: null, truncated: false })
        : answers?.(path, options)
    );
    const view = screenOf();
    await view.user.selectOptions(
      await screen.findByRole('combobox', { name: 'workbench.contacts.filter_label' }),
      'other'
    );
    await view.user.type(screen.getByRole('searchbox'), 'bea{Enter}');
    await screen.findByRole('heading', { name: 'Bea Rossi' });
    return view;
  }

  it('offers no group field: nothing can be changed on it', async () => {
    await metInMail();

    expect(screen.getByText('workbench.contacts.other_read_only')).toBeVisible();
    expect(screen.queryByLabelText('workbench.contacts.groups.add_label')).toBeNull();
  });

  it('is saved into the contacts, and opens as one', async () => {
    api.post.mockResolvedValue({ ...ANA, id: 'people/c7', name: 'Bea Rossi' });
    const { user } = await metInMail();

    await user.click(screen.getByRole('button', { name: 'workbench.contacts.save_other' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, body] = api.post.mock.calls[0];
    expect(path).toBe('/workbench/contacts/other/save');
    expect(body).toMatchObject({ id: MET.id, idempotency_key: expect.any(String) });
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(
        expect.stringContaining('contact=people%2Fc7'),
        expect.anything()
      )
    );
    expect(toast.success).toHaveBeenCalledWith('workbench.contacts.saved_other');
  });

  it('says it is on its way, and sends it once', async () => {
    let answer: (contact: unknown) => void = () => undefined;
    api.post.mockImplementationOnce(() => new Promise(resolve => (answer = resolve)));
    const { user } = await metInMail();
    const save = screen.getByRole('button', { name: 'workbench.contacts.save_other' });

    await user.click(save);
    expect(save).toHaveAttribute('aria-busy', 'true');
    await user.click(save);
    expect(api.post).toHaveBeenCalledTimes(1);

    answer({ ...ANA, id: 'people/c7' });
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('workbench.contacts.saved_other')
    );
  });

  it('keeps its key when it is tried again after a failure', async () => {
    api.post.mockRejectedValueOnce(new Error('offline'));
    api.post.mockResolvedValue({ ...ANA, id: 'people/c7' });
    const { user } = await metInMail();
    const save = screen.getByRole('button', { name: 'workbench.contacts.save_other' });

    await user.click(save);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await user.click(save);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][1].idempotency_key).toBe(
      api.post.mock.calls[0][1].idempotency_key
    );
  });

  it('offers nothing of the kind on a saved contact', async () => {
    nav.search = 'contact=people/c1';
    screenOf();

    await screen.findByRole('heading', { name: 'Ana Lima' });
    expect(screen.queryByRole('button', { name: 'workbench.contacts.save_other' })).toBeNull();
  });
});

describe('ContactsTool — what another tool hands it', () => {
  it('opens a new contact holding the name and the address it was given', async () => {
    handOff('owner', { kind: 'contact', name: 'Ana Lima', email: 'ana@example.org' });
    screenOf();

    expect(await screen.findByLabelText('workbench.contacts.editor.name')).toHaveValue('Ana Lima');
    expect(screen.getByDisplayValue('ana@example.org')).toBeInTheDocument();
  });

  it('opens a new contact holding the number an SMS came from, and no empty address', async () => {
    // The home's SMS card saves a sender (2026-11-07): a number, often with no name.
    handOff('owner', { kind: 'contact', name: '', email: '', phone: '+33612345678' });
    screenOf();

    expect(await screen.findByDisplayValue('+33612345678')).toBeInTheDocument();
    expect(screen.getByLabelText('workbench.contacts.editor.name')).toHaveValue('');
    expect(screen.queryByDisplayValue('ana@example.org')).toBeNull();
  });
});

describe('ContactsTool — to the other tools', () => {
  it('writes to an address from the mail tool, when one is ready', async () => {
    nav.search = 'contact=people/c1';
    mailReady = true;
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.contacts.write' }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/mail');
    expect(takeHandoff('compose', 'owner')).toEqual({ kind: 'compose', to: 'ana@example.org' });
  });

  it('offers no such way without a mailbox', async () => {
    nav.search = 'contact=people/c1';
    screenOf();

    await screen.findByRole('heading', { name: 'Ana Lima' });
    expect(screen.queryByRole('button', { name: 'workbench.contacts.write' })).toBeNull();
  });
});

describe('ContactsTool — a value at hand', () => {
  beforeEach(() => {
    nav.search = 'contact=people/c1';
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/contact') {
        return Promise.resolve({
          ...ANA,
          addresses: [{ formatted: '1 rue de la Paix, Paris', type: 'home' }],
        });
      }
      return Promise.resolve({ relations: [], groups: [] });
    });
  });

  it('copies an address or a number, and says so', async () => {
    const { user } = screenOf();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);

    const [copy] = await screen.findAllByRole('button', { name: 'workbench.contacts.copy' });
    await user.click(copy!);

    expect(writeText).toHaveBeenCalledWith('ana@example.org');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.contacts.copied'));
  });

  it('opens an address on a map, in a tab of its own', async () => {
    screenOf();

    const map = await screen.findByRole('link', { name: 'workbench.contacts.see_on_map' });

    expect(map).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=1%20rue%20de%20la%20Paix%2C%20Paris'
    );
    expect(map).toHaveAttribute('rel', 'noopener noreferrer');
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

  it('asks its latest exchanges by its numbers too, within the published bound', async () => {
    bounds = { ...bounds, history_addresses: 3, history_phones: 1 };
    const both = {
      ...ANA,
      phones: [
        { value: '+33 6 12', type: 'mobile' },
        { value: '01 40 00 00 00', type: 'work' },
      ],
    };
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail());
      if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
      if (path === '/workbench/contacts') return Promise.resolve({ ...page, items: [both] });
      if (path === '/workbench/contacts/contact') return Promise.resolve(both);
      return Promise.resolve({ groups: [], relations: [], relations_total: 0 });
    });
    screenOf();

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/contacts/history', expect.anything())
    );
    const asked = api.get.mock.calls.find(([path]) => path === '/workbench/contacts/history');
    expect(asked?.[1]).toMatchObject({
      params: { address: ['ana@example.org'], phone: ['+33 6 12'] },
    });
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
      if (path === '/workbench/contacts/history') return Promise.resolve(NO_HISTORY);
      if (path === '/workbench/contacts') return Promise.resolve(page);
      if (path === '/workbench/contacts/groups') return Promise.resolve({ groups: [] });
      if (path === '/workbench/contacts/contact') return Promise.resolve(withAddress);
      if (path === '/relations') return Promise.resolve({ relations, relations_total: 1 });
      return Promise.resolve({ groups: [] });
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

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});

afterEach(() => setHandoffOwner(null));
