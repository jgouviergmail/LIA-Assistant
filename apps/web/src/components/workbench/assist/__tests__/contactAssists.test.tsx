/**
 * What LIA finds for a card (lot 10): each value beside the message that says it, the person
 * ticking what they keep, nothing reaching the card by itself; and a photographed card filling a
 * new contact's form under their eyes.
 */
import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProposedContact, ProposedValue } from '@/lib/workbench/assist';
import { EMPTY_CONTACT, withCard, withFoundValues } from '@/lib/workbench/contacts';
import { formatDay } from '@/lib/workbench/tasks';
import type { WorkbenchContact } from '@/lib/workbench/types';

const { post, bridges, bounds, toast, phone } = vi.hoisted(() => ({
  post: vi.fn(),
  bridges: { assists: true, mailbox: true, ask: vi.fn(), go: vi.fn() },
  phone: { callable: true },
  bounds: { value: { textMax: 100, instructionMax: 10, dictates: false } as object | null },
  toast: Object.assign(vi.fn(), { info: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { timezone: 'Pacific/Kiritimati' } }),
}));
vi.mock('../../useToolBridges', () => ({
  useToolBridges: () => ({
    ask: bridges.ask,
    remind: vi.fn(),
    go: bridges.go,
    offers: (kind: string) => kind === 'compose' && bridges.mailbox,
    assists: bridges.assists,
  }),
}));
vi.mock('@/hooks/useTelephonyCallable', () => ({ useTelephonyCallable: () => phone.callable }));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));

import { NewContactAssist } from '../NewContactAssist';
import { useContactAssist } from '../useContactAssist';

const COMPLETE = 'workbench.assist.contacts.complete';
const USE = 'workbench.assist.contacts.use';
const CONTACT: WorkbenchContact = {
  id: 'c1',
  name: 'Ana Silva',
  given_name: null,
  family_name: null,
  email: 'ana@example.org',
  phone: null,
  organization: null,
  name_key: 'ana silva',
  emails: [{ value: 'ana@example.org', type: null }],
  phones: [],
  addresses: [],
  notes: null,
  job_title: null,
  website: null,
  birthday: null,
};
const PHONE: ProposedValue = {
  field: 'phone',
  value: '+33 6 12',
  message_id: 'm1',
  subject: 'Budget',
  received_at: '2026-11-02T10:00:00Z',
};
const JOB: ProposedValue = { ...PHONE, field: 'job_title', value: 'Sales lead' };
const CARD: ProposedContact = {
  given_name: 'Ana',
  family_name: 'Silva',
  organization: 'Acme',
  job_title: 'Sales lead',
  website: 'acme.example',
  emails: ['ana@acme.example'],
  phones: ['+33 6 12'],
  address: '1 rue X',
};

const labels = (lines: readonly { label: string }[]) => lines.map(line => line.label);

beforeEach(() => {
  vi.clearAllMocks();
  bridges.assists = true;
  bridges.mailbox = true;
  phone.callable = true;
  bounds.value = { textMax: 100, instructionMax: 10, dictates: false };
});

describe('useContactAssist — a call and a message through LIA (2026-11-07)', () => {
  const CALLABLE: WorkbenchContact = {
    ...CONTACT,
    phones: [
      { value: '+33 6 12 34 56 78', type: 'mobile' },
      { value: '01 23 45 67 89', type: null },
    ],
  };
  const CALL = 'workbench.assist.contacts.call';

  it('offers one call per number, its kind named, the words left unsent in the chat', () => {
    const { lines } = renderHook(() => useContactAssist('en', CALLABLE)).result.current;
    const calls = lines.filter(line => line.label.startsWith(CALL));

    expect(calls.map(line => line.label)).toEqual([
      `${CALL} {"name":"Ana Silva","which":"workbench.contacts.kinds.mobile"}`,
      `${CALL} {"name":"Ana Silva","which":"01 23 45 67 89"}`,
    ]);
    calls[1].onSelect?.();
    expect(bridges.ask).toHaveBeenCalledWith(
      'workbench.assist.contacts.call_words {"name":"Ana Silva","number":"01 23 45 67 89"}'
    );
  });

  it('tells two numbers of one kind apart by the numbers, and offers a number once', () => {
    const twice: WorkbenchContact = {
      ...CONTACT,
      phones: [
        { value: '+33 6 12 34 56 78', type: 'mobile' },
        { value: '+33 7 11 22 33 44', type: 'mobile' },
        { value: '+33 6 12 34 56 78', type: 'mobile' },
        { value: '01 23 45 67 89', type: 'work' },
      ],
    };
    const { lines } = renderHook(() => useContactAssist('en', twice)).result.current;

    expect(labels(lines).filter(label => label.startsWith(CALL))).toEqual([
      `${CALL} {"name":"Ana Silva","which":"+33 6 12 34 56 78"}`,
      `${CALL} {"name":"Ana Silva","which":"+33 7 11 22 33 44"}`,
      `${CALL} {"name":"Ana Silva","which":"workbench.contacts.kinds.work"}`,
    ]);
  });

  it('offers no call where the instance or the account cannot place one', () => {
    phone.callable = false;
    const { lines } = renderHook(() => useContactAssist('en', CALLABLE)).result.current;

    expect(lines.some(line => line.label.startsWith(CALL))).toBe(false);
  });

  it('writes to them with LIA in a new message, where a mailbox is ready', () => {
    const { lines } = renderHook(() => useContactAssist('en', CONTACT)).result.current;
    const write = lines.find(line => line.label.startsWith('workbench.assist.contacts.write_to'));

    write?.onSelect?.();
    expect(bridges.go).toHaveBeenCalledWith({
      kind: 'compose',
      to: 'ana@example.org',
      assisted: true,
    });
  });

  it.each([
    ['no mailbox', () => (bridges.mailbox = false)],
    ['no click may ask a model', () => (bridges.assists = false)],
  ])('offers no message through LIA with %s', (_, unset) => {
    unset();
    const { lines } = renderHook(() => useContactAssist('en', CONTACT)).result.current;

    expect(lines.some(line => line.label.startsWith('workbench.assist.contacts.write_to'))).toBe(
      false
    );
  });
});

describe('useContactAssist', () => {
  it('offers to complete a card the person can change, with an address to look under', () => {
    const onFound = vi.fn();
    const open = renderHook(() => useContactAssist('en', CONTACT, onFound)).result.current;
    expect(labels(open.lines)).toContain(COMPLETE);

    const readOnly = renderHook(() => useContactAssist('en', CONTACT)).result.current;
    expect(labels(readOnly.lines)).not.toContain(COMPLETE);

    const unreachable = { ...CONTACT, emails: [] };
    const none = renderHook(() => useContactAssist('en', unreachable, onFound)).result.current;
    expect(labels(none.lines)).not.toContain(COMPLETE);

    bridges.assists = false;
    const off = renderHook(() => useContactAssist('en', CONTACT, onFound)).result.current;
    expect(labels(off.lines)).not.toContain(COMPLETE);
  });

  it('asks by the id alone, shows each value with its source, and keeps what is ticked', async () => {
    post.mockResolvedValue({ values: [PHONE, JOB], usage: null });
    const onFound = vi.fn();
    const { result } = renderHook(() => useContactAssist('en', CONTACT, onFound));

    act(() => result.current.lines.find(line => line.label === COMPLETE)?.onSelect?.());
    expect(result.current.busy).toBe(true);
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0]?.[1]).toEqual({ contact_id: 'c1' });
    await waitFor(() => expect(result.current.busy).toBe(false));
    // Once, and outside the wait: what is rendered in `waitFor` wakes it again, without end.
    render(<div>{result.current.panel}</div>);

    const user = userEvent.setup();
    const source = screen.getAllByRole('link', { name: /Budget/ })[0];
    expect(source).toHaveAttribute('href', expect.stringContaining('m1'));
    // Midnight has passed where this person lives: their day, never Greenwich's.
    expect(source).toHaveTextContent(formatDay('2026-11-03', 'en'));
    await user.click(screen.getAllByRole('checkbox')[0]);
    await user.click(screen.getAllByRole('button', { name: USE })[0]);

    expect(onFound).toHaveBeenCalledWith([JOB]);
  });
});

describe('what a card gains', () => {
  it('adds a phone beside the others, and never replaces what it holds', () => {
    const held = {
      ...EMPTY_CONTACT,
      organization: 'Old Ltd',
      phones: [{ value: '01', type: null }],
    };
    const found = withFoundValues(held, [
      PHONE,
      JOB,
      { ...PHONE, field: 'organization', value: 'Acme' },
    ]);

    expect(found.phones).toEqual([
      { value: '01', type: null },
      { value: '+33 6 12', type: 'work' },
    ]);
    expect(found.organization).toBe('Old Ltd');
    expect(found.job_title).toBe('Sales lead');
  });

  it('fills a blank address, never a second one', () => {
    const address = { ...PHONE, field: 'address', value: '1 rue X' };

    expect(withFoundValues(EMPTY_CONTACT, [address]).addresses).toEqual([
      { formatted: '1 rue X', type: 'work' },
    ]);
    const held = { ...EMPTY_CONTACT, addresses: [{ formatted: 'Here', type: null }] };
    expect(withFoundValues(held, [address]).addresses).toEqual(held.addresses);
  });

  it('reads a card into the form, naming it after the person or else the organization', () => {
    const fields = withCard(EMPTY_CONTACT, CARD);

    expect(fields.name).toBe('Ana Silva');
    expect(fields.emails).toEqual([{ value: 'ana@acme.example', type: 'work' }]);
    expect(fields.addresses).toEqual([{ formatted: '1 rue X', type: 'work' }]);
    expect(withCard(EMPTY_CONTACT, { ...CARD, given_name: '', family_name: '' }).name).toBe('Acme');
    expect(withCard(EMPTY_CONTACT, { ...CARD, address: '' }).addresses).toEqual([]);
  });

  it('keeps what the person already typed, and adds to the lists', () => {
    const typed = {
      ...EMPTY_CONTACT,
      name: 'Ana from the fair',
      organization: 'Typed Ltd',
      phones: [{ value: '01', type: null }],
    };

    const fields = withCard(typed, CARD);

    expect(fields.name).toBe('Ana from the fair');
    expect(fields.organization).toBe('Typed Ltd');
    expect(fields.job_title).toBe('Sales lead');
    expect(fields.phones).toEqual([
      { value: '01', type: null },
      { value: '+33 6 12', type: 'work' },
    ]);
  });

  it('adds nothing twice when the same card is read again', () => {
    const once = withCard(EMPTY_CONTACT, CARD);

    const twice = withCard(once, CARD);

    expect(twice.emails).toEqual(once.emails);
    expect(twice.phones).toEqual(once.phones);
  });
});

describe('NewContactAssist', () => {
  // Its own name: a field's « Write with LIA » (the notes) stands in the same form.
  const WRITE = 'workbench.assist.contacts.write';
  const FROM_CARD = 'workbench.assist.contacts.from_card';
  const FROM_WORDS = 'workbench.assist.contacts.from_words';
  const CAMERA = 'workbench.assist.contacts.take_photo';
  const LIBRARY = 'workbench.assist.contacts.choose_photo';
  const picture = new File(['bytes'], 'card.jpg', { type: 'image/jpeg' });

  function draw(maxBytes = 1000) {
    const onRead = vi.fn();
    const rendered = render(<NewContactAssist lng="en" maxBytes={maxBytes} onRead={onRead} />);
    return { onRead, ...rendered };
  }

  async function openReading(capture = false) {
    const user = userEvent.setup({ applyAccept: false });
    await user.click(screen.getByRole('button', { name: WRITE }));
    await user.click(screen.getByRole('menuitem', { name: FROM_CARD }));
    const dialog = screen.getByRole('dialog', { name: FROM_CARD });
    const input = dialog.querySelector<HTMLInputElement>(
      capture ? 'input[capture]' : 'input[type="file"]:not([capture])'
    );
    if (!input) throw new Error('Photo source input missing');
    return { input, dialog, user };
  }

  it('stands aside where a click may not ask a model', () => {
    bounds.value = null;
    draw();

    expect(screen.queryByRole('button', { name: WRITE })).toBeNull();
  });

  it('offers both ways behind « Write with LIA »', async () => {
    draw();

    await userEvent.setup().click(screen.getByRole('button', { name: WRITE }));

    expect(screen.getByRole('menuitem', { name: FROM_WORDS })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: FROM_CARD })).toBeInTheDocument();
  });

  it('fills the form from a sentence, typed or dictated, nothing created', async () => {
    post.mockResolvedValue({ contact: CARD, usage: null });
    const { onRead } = draw();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: WRITE }));
    await user.click(screen.getByRole('menuitem', { name: FROM_WORDS }));
    await user.type(
      screen.getByRole('textbox', { name: 'workbench.assist.writing.instruction' }),
      'Ana, sales'
    );
    await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.ask' }));

    await waitFor(() => expect(onRead).toHaveBeenCalledWith(CARD));
    expect(post.mock.calls[0]?.[0]).toBe('/tool-assists/contacts/from-words');
    // Within the published bound of a sentence (10 here).
    expect(post.mock.calls[0]?.[1]).toEqual({ sentence: 'Ana, sales' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it.each([true, false])(
    'opens the chosen photo source (camera: %s), then fills the form',
    async capture => {
      post.mockResolvedValue({ contact: CARD, usage: null });
      const { onRead } = draw();
      const { input, dialog, user } = await openReading(capture);
      const click = vi.spyOn(input, 'click');
      expect(within(dialog).getByRole('button', { name: CAMERA })).toBeVisible();
      expect(within(dialog).getByRole('button', { name: LIBRARY })).toBeVisible();
      expect(post).not.toHaveBeenCalled();
      expect(input.getAttribute('capture')).toBe(capture ? 'environment' : null);
      await user.click(within(dialog).getByRole('button', { name: capture ? CAMERA : LIBRARY }));
      expect(click).toHaveBeenCalledOnce();
      click.mockRestore();
      await user.upload(input, picture);

      await waitFor(() => expect(onRead).toHaveBeenCalledWith(CARD));
      expect(post.mock.calls[0]?.[0]).toBe('/tool-assists/contacts/from-card');
      expect((post.mock.calls[0]?.[1] as FormData).get('file')).toBe(picture);
      expect(screen.queryByRole('dialog', { name: FROM_CARD })).toBeNull();
    }
  );

  it('refuses a picture past its ceiling before anything leaves', async () => {
    const { onRead } = draw(2);
    const { input, user } = await openReading();

    await user.upload(input, picture);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(post).not.toHaveBeenCalled();
    expect(onRead).not.toHaveBeenCalled();
  });

  it('says a failure, keeps the form, and lets the person select the same picture again', async () => {
    post.mockRejectedValueOnce(new Error('down'));
    post.mockResolvedValueOnce({ contact: CARD, usage: null });
    const { onRead } = draw();
    const { input, user } = await openReading();

    await user.upload(input, picture);

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.assist.failed');
    expect(onRead).not.toHaveBeenCalled();
    expect(post).toHaveBeenCalledOnce();
    await user.upload(input, picture);
    await waitFor(() => expect(onRead).toHaveBeenCalledWith(CARD));
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('aborts on closing and ignores a late answer without filling the form', async () => {
    let complete: (value: { contact: ProposedContact; usage: null }) => void = () => undefined;
    post.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          complete = resolve;
        })
    );
    const { onRead } = draw();
    const { input, dialog, user } = await openReading();
    await user.upload(input, picture);
    expect(within(dialog).getByRole('button', { name: CAMERA })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: LIBRARY })).toBeDisabled();
    await user.keyboard('{Escape}');
    expect(post.mock.calls[0][2].signal.aborted).toBe(true);
    await act(async () => complete({ contact: CARD, usage: null }));
    expect(onRead).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: FROM_CARD })).toBeNull();
    await waitFor(() => expect(screen.getByRole('button', { name: WRITE })).toHaveFocus());
  });
});
