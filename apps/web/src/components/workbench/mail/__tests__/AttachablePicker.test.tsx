/**
 * The person's own files a new message may carry (ADR-369, spec §13): one page
 * at a time with its EXACT total, a search by name, and the two bounds the send
 * refuses beyond — a file that would pass one is said so and cannot be picked,
 * never silently dropped; a picked file can always be put back.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { fileSize } from '@/lib/workbench/mail';
import type { AttachableFile, AttachablePage } from '@/lib/workbench/types';

const { api, i18n } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  // One stable `t` that shows its values, so a bound and a range are read.
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import { AttachablePicker } from '../AttachablePicker';

const PATH = '/workbench/mail/attachable';
const MB = 1024 * 1024;

function file(id: string, size = MB): AttachableFile {
  return {
    id,
    filename: `${id}.pdf`,
    mime_type: 'application/pdf',
    size,
    origin: 'upload',
    expires_at: null,
  };
}

let pages: Record<string, AttachablePage>;

beforeEach(() => {
  vi.clearAllMocks();
  pages = {
    '0': { items: [file('a'), file('b')], total: 3, next_offset: 2 },
    '2': { items: [file('c')], total: 3, next_offset: null },
  };
  api.get.mockImplementation((_path: string, { params }: { params: { offset: number } }) =>
    Promise.resolve(pages[String(params.offset)])
  );
});

function picker({
  open = true,
  chosen = [],
  maxFiles = 5,
  maxBytes = 10 * MB,
}: { open?: boolean; chosen?: AttachableFile[]; maxFiles?: number; maxBytes?: number } = {}) {
  const onToggle = vi.fn();
  const rendered = renderWithProviders(
    <AttachablePicker
      lng="en"
      open={open}
      onOpenChange={vi.fn()}
      chosen={chosen}
      maxFiles={maxFiles}
      maxBytes={maxBytes}
      onToggle={onToggle}
    />
  );
  return { ...rendered, onToggle };
}

/** The params of the last read. */
function lastRead(): Record<string, unknown> {
  const [path, options] = api.get.mock.calls.at(-1) ?? [];
  expect(path).toBe(PATH);
  return (options as { params: Record<string, unknown> }).params;
}

const attach = (name: string) =>
  screen.getByRole('button', { name: `workbench.mail.files.attach_named(${name})` });

describe('AttachablePicker', () => {
  it('reads nothing while closed, then the first page with its exact total', async () => {
    const closed = picker({ open: false });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(api.get).not.toHaveBeenCalled();
    closed.unmount();

    picker();
    const row = (await screen.findByText('a.pdf')).closest('li') as HTMLElement;
    expect(lastRead()).toEqual({ offset: 0 });
    expect(row).toHaveTextContent(fileSize(MB, 'en'));
    expect(screen.getByText('workbench.mail.files.range(1|2|3)')).toBeInTheDocument();
  });

  it('picks a file and puts a picked one back, even at the bound', async () => {
    const a = file('a');
    const { user, onToggle } = picker({ chosen: [a], maxFiles: 1 });
    await screen.findByText('a.pdf');

    expect(attach('a.pdf')).toHaveAttribute('aria-pressed', 'true');
    expect(attach('a.pdf')).toHaveTextContent('workbench.mail.files.attached');
    await user.click(attach('a.pdf'));

    expect(onToggle).toHaveBeenCalledWith(a);
  });

  it('says a file past the count bound and does not pick it', async () => {
    const { user, onToggle } = picker({ chosen: [file('x')], maxFiles: 1 });
    const row = (await screen.findByText('b.pdf')).closest('li') as HTMLElement;

    expect(row).toHaveTextContent('workbench.mail.files.max_files(1)');
    expect(attach('b.pdf')).toHaveAttribute('aria-disabled', 'true');
    await user.click(attach('b.pdf'));

    expect(onToggle).not.toHaveBeenCalled();
  });

  it('says a file past the byte bound and does not pick it, but picks one that fits', async () => {
    pages['0'] = { items: [file('big', 3 * MB), file('fits', 2 * MB)], total: 2, next_offset: null };
    const { user, onToggle } = picker({ chosen: [file('x', 8 * MB)], maxBytes: 10 * MB });
    const big = (await screen.findByText('big.pdf')).closest('li') as HTMLElement;

    expect(big).toHaveTextContent(`workbench.mail.files.max_bytes(${fileSize(10 * MB, 'en')})`);
    await user.click(attach('big.pdf'));
    expect(onToggle).not.toHaveBeenCalled();

    // 8 MB + 2 MB is exactly the bound: allowed.
    await user.click(attach('fits.pdf'));
    expect(onToggle).toHaveBeenCalledWith(expect.objectContaining({ id: 'fits' }));
  });

  it('searches by name, trimmed, from the first page', async () => {
    const { user } = picker();
    await screen.findByText('a.pdf');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.files.next' }));
    await screen.findByText('c.pdf');

    await user.type(screen.getByRole('searchbox'), '  invoice  ');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.search' }));

    await waitFor(() => expect(lastRead()).toEqual({ q: 'invoice', offset: 0 }));
  });

  it('walks forward and back through the pages, and no further than they go', async () => {
    pages = {
      '0': { items: [file('a'), file('b')], total: 5, next_offset: 2 },
      '2': { items: [file('c'), file('d')], total: 5, next_offset: 4 },
      '4': { items: [file('e')], total: 5, next_offset: null },
    };
    const { user } = picker();
    await screen.findByText('a.pdf');
    const previous = () => screen.getByRole('button', { name: 'workbench.mail.files.previous' });
    const next = () => screen.getByRole('button', { name: 'workbench.mail.files.next' });
    const reads = api.get.mock.calls.length;

    // Nothing before the first page — and pressing it anyway loses no step.
    await user.click(previous());
    expect(previous()).toHaveAttribute('aria-disabled', 'true');
    expect(api.get).toHaveBeenCalledTimes(reads);
    await user.click(next());
    await screen.findByText('c.pdf');
    expect(previous()).not.toHaveAttribute('aria-disabled');

    await user.click(next());
    await screen.findByText('e.pdf');
    expect(lastRead()).toEqual({ offset: 4 });
    expect(screen.getByText('workbench.mail.files.range(5|5|5)')).toBeInTheDocument();
    expect(next()).toHaveAttribute('aria-disabled', 'true');
    await user.click(next());
    expect(lastRead()).toEqual({ offset: 4 });

    // Back one page at a time, never straight to the start.
    await user.click(previous());
    await screen.findByText('c.pdf');
    expect(lastRead()).toEqual({ offset: 2 });
    await user.click(previous());
    await screen.findByText('a.pdf');
    expect(lastRead()).toEqual({ offset: 0 });
  });

  it('tells no file from a list that could not be read', async () => {
    pages['0'] = { items: [], total: 0, next_offset: null };
    const empty = picker();
    expect(await screen.findByText('workbench.mail.files.empty')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.mail.files.next' })).toBeNull();
    empty.unmount();

    api.get.mockRejectedValue(new ApiError('down', 502));
    picker();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('workbench.mail.files.failed')).toBeInTheDocument();
  });
});
