/**
 * What LIA finds for a card (lot 10): each value beside the message that says it, the person
 * ticking what they keep, nothing reaching the card by itself; and a photographed card filling a
 * new contact's form under their eyes.
 */
import { render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProposedContact, ProposedValue } from '@/lib/workbench/assist';
import { EMPTY_CONTACT, withCard, withFoundValues } from '@/lib/workbench/contacts';
import { formatDay } from '@/lib/workbench/tasks';
import type { WorkbenchContact } from '@/lib/workbench/types';

const { post, mutate, bridges, bounds, toast } = vi.hoisted(() => ({
  post: vi.fn(),
  mutate: vi.fn(),
  bridges: { assists: true },
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
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));
vi.mock('../../useToolBridges', () => ({
  useToolBridges: () => ({ ask: vi.fn(), remind: vi.fn(), assists: bridges.assists }),
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));

import { CardAssist } from '../CardAssist';
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
  bounds.value = { textMax: 100, instructionMax: 10, dictates: false };
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
    const { result, rerender } = renderHook(() => useContactAssist('en', CONTACT, onFound));

    result.current.lines.find(line => line.label === COMPLETE)?.onSelect?.();
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0]?.[1]).toEqual({ contact_id: 'c1' });
    await waitFor(() => {
      rerender();
      expect(result.current.busy).toBe(false);
    });
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

describe('CardAssist', () => {
  const LABEL = 'workbench.assist.contacts.from_card';
  const picture = new File(['bytes'], 'card.jpg', { type: 'image/jpeg' });

  function draw(maxBytes = 1000) {
    const onRead = vi.fn();
    const { container } = render(<CardAssist lng="en" maxBytes={maxBytes} onRead={onRead} />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    return { onRead, input };
  }

  it('stands aside where a click may not ask a model', () => {
    bounds.value = null;
    draw();

    expect(screen.queryByRole('button', { name: LABEL })).toBeNull();
  });

  it('offers the camera, and fills the form with what it read', async () => {
    mutate.mockResolvedValue({ contact: CARD, usage: null });
    const { onRead, input } = draw();
    expect(input).toHaveAttribute('capture', 'environment');

    await userEvent.setup({ applyAccept: false }).upload(input as HTMLInputElement, picture);

    await waitFor(() => expect(onRead).toHaveBeenCalledWith(CARD));
    expect(mutate.mock.calls[0]?.[0]).toBe('/tool-assists/contacts/from-card');
    expect((mutate.mock.calls[0]?.[1] as FormData).get('file')).toBeInstanceOf(File);
  });

  it('refuses a picture past its ceiling before anything leaves', async () => {
    const { onRead, input } = draw(2);

    await userEvent.setup({ applyAccept: false }).upload(input as HTMLInputElement, picture);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(mutate).not.toHaveBeenCalled();
    expect(onRead).not.toHaveBeenCalled();
  });

  it('says a failure and leaves the form as it stands', async () => {
    mutate.mockRejectedValue(new Error('down'));
    const { onRead, input } = draw();

    await userEvent.setup({ applyAccept: false }).upload(input as HTMLInputElement, picture);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.assist.failed'));
    expect(onRead).not.toHaveBeenCalled();
  });
});
