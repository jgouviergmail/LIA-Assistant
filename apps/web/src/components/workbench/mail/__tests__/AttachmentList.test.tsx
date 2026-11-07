/**
 * A message's files (ADR-369): each a download through the API's own door,
 * opened in a new tab that cannot reach back (a refusal never replaces the
 * screen); a file past the published ceiling is listed and said too large,
 * never offered for a download that would be refused; a file without a name
 * or a size is still listed.
 */

import { Sparkles } from 'lucide-react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { fileSize } from '@/lib/workbench/mail';
import type { MailAttachment } from '@/lib/workbench/types';

const { api, i18n, pdf, toast } = vi.hoisted(() => ({
  api: { getBlob: vi.fn(), getResponse: vi.fn(), get: vi.fn(), post: vi.fn() },
  pdf: { openPdf: vi.fn(), isLockedPdf: () => false },
  toast: { error: vi.fn(), success: vi.fn() },
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/workbench/pdf-document', () => pdf);
vi.mock('sonner', () => ({ toast }));

import { AttachmentList } from '../AttachmentList';

const MB = 1024 * 1024;

beforeEach(() => {
  pdf.openPdf.mockResolvedValue({ pages: 2, draw: vi.fn(), close: vi.fn() });
});

function list(attachments: MailAttachment[], maxBytes = 25 * MB) {
  return renderWithProviders(
    <AttachmentList lng="en" messageId="m1" attachments={attachments} maxBytes={maxBytes} />
  );
}

describe('AttachmentList — a look before the download', () => {
  const PICTURE: MailAttachment = {
    id: 'a1',
    filename: 'chart.png',
    mime_type: 'image/png',
    size: 2048,
    previewable: true,
  };
  const REPORT: MailAttachment = {
    ...PICTURE,
    id: 'a2',
    filename: 'r.pdf',
    mime_type: 'application/pdf',
  };
  const WORD: MailAttachment = {
    ...PICTURE,
    id: 'a3',
    filename: 'note.docx',
    mime_type: 'application/octet-stream',
  };
  const answered = (body: string, type: string, cut = false) =>
    new Response(body, {
      headers: { 'Content-Type': type, 'X-Preview-Truncated': String(cut) },
    });
  const look = /workbench\.mail\.preview/;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:https://lia.example/1');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('shows an image in a window of the page, through the reading door', async () => {
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    const { user } = list([PICTURE]);

    await user.click(screen.getByRole('button', { name: look }));

    const image = await screen.findByRole('img', { name: 'chart.png' });
    expect(image).toHaveAttribute('src', 'blob:https://lia.example/1');
    expect(api.getBlob).not.toHaveBeenCalled();
  });

  it('lets the bytes go when the window closes', async () => {
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    const { user } = list([PICTURE]);
    await user.click(screen.getByRole('button', { name: look }));
    await screen.findByRole('img', { name: 'chart.png' });

    await user.keyboard('{Escape}');

    await waitFor(() =>
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:https://lia.example/1')
    );
  });

  it('reads a PDF in the same window, on every device', async () => {
    api.getResponse.mockResolvedValue(answered('%PDF', 'application/pdf'));
    const { user } = list([REPORT]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(await within(window).findByText('workbench.files.pdf_pages(2)')).toBeInTheDocument();
    expect(pdf.openPdf).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['image/svg+xml', 'logo.svg'],
    ['application/zip', 'files.zip'],
  ])('offers no look at %s, which the API cannot read', (mime_type, filename) => {
    list([{ ...PICTURE, mime_type, filename, previewable: false }]);

    expect(screen.queryByRole('button', { name: look })).toBeNull();
  });

  it('reads it in a window of the page, naming the part', async () => {
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain'));
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(await within(window).findByText('Hello there')).toBeInTheDocument();
    const [path, options] = api.getResponse.mock.calls[0] as [
      string,
      { params: Record<string, string> },
    ];
    expect(path).toBe('/workbench/mail/attachment/preview');
    expect(options.params).toEqual({
      message_id: 'm1',
      attachment_id: 'a3',
      filename: 'note.docx',
    });
  });

  it('says the reading is only the beginning of the file', async () => {
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain', true));
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(await within(window).findByText('workbench.files.preview_cut')).toBeInTheDocument();
  });

  it('lays a table out', async () => {
    const sheets = { sheets: [{ name: 'Budget', rows: [['Rent', '700']], cut: false }] };
    api.getResponse.mockResolvedValue(answered(JSON.stringify(sheets), 'application/json'));
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    expect(await screen.findByRole('cell', { name: 'Rent' })).toBeInTheDocument();
  });

  it('says what it could not read, and reads again on the reader’s word', async () => {
    api.getResponse.mockRejectedValueOnce(new Error('gone'));
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain'));
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(await within(window).findByText('workbench.files.reading_failed')).toBeInTheDocument();
    await user.click(within(window).getByRole('button', { name: 'workbench.files.retry' }));
    expect(await within(window).findByText('Hello there')).toBeInTheDocument();
  });

  it('says what the API refused, in its words', async () => {
    api.getResponse.mockRejectedValue(
      new ApiError('no', 413, { detail: { code: 'too_large', max_bytes: 25 * MB } })
    );
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(
      await within(window).findByText('workbench.errors.too_large_bounded(25)')
    ).toBeInTheDocument();
  });

  it('says a file there is nothing to show of, and offers no second read', async () => {
    api.getResponse.mockRejectedValue(
      new ApiError('no', 422, { detail: { code: 'not_supported_by_provider' } })
    );
    const { user } = list([WORD]);

    await user.click(screen.getByRole('button', { name: look }));

    const window = await screen.findByRole('dialog');
    expect(await within(window).findByText('workbench.files.reading_none')).toBeInTheDocument();
    expect(within(window).queryByRole('button', { name: 'workbench.files.retry' })).toBeNull();
  });

  it('opens a file from its own card, its download beside it', async () => {
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    const { user } = list([PICTURE]);

    expect(screen.getByRole('link', { name: /workbench\.mail\.download/ })).toHaveAttribute(
      'href',
      expect.stringContaining('/workbench/mail/attachment?')
    );
    const card = screen.getByRole('button', { name: look });
    expect(card).toHaveTextContent('chart.png');
    await user.click(card);

    expect(await screen.findByRole('img', { name: 'chart.png' })).toBeInTheDocument();
  });

  it('leaves a file nothing can show as a download, its whole card a link', () => {
    list([{ ...PICTURE, previewable: false }]);

    expect(screen.getAllByRole('link', { name: /workbench\.mail\.download/ })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: look })).toBeNull();
  });

  it('offers neither a look at a file past the ceiling, nor its download', () => {
    list([{ ...PICTURE, size: 26 * MB }]);

    expect(screen.queryByRole('button', { name: look })).toBeNull();
    expect(screen.queryByRole('link', { name: /workbench\.mail\.download/ })).toBeNull();
  });
});

describe('AttachmentList — kept on the drive', () => {
  const REPORT: MailAttachment = {
    id: 'a2',
    filename: 'r.pdf',
    mime_type: 'application/pdf',
    size: 2048,
  };

  function kept(attachments: MailAttachment[] = [REPORT], maxBytes = 25 * MB) {
    return renderWithProviders(
      <AttachmentList
        lng="en"
        messageId="m1"
        attachments={attachments}
        maxBytes={maxBytes}
        drive={{ provider: 'google_drive' }}
      />
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      items: [
        {
          id: 'd1',
          name: 'Invoices',
          kind: 'folder',
          mime_type: 'folder',
          target_id: null,
          target_kind: null,
        },
      ],
      next_page_token: null,
    });
    api.post.mockResolvedValue({ id: 'f1' });
  });

  it('goes to the folder chosen, once per submission', async () => {
    const { user } = kept();

    await user.click(screen.getByRole('button', { name: /workbench\.mail\.keep_on_drive/ }));
    const dialog = await screen.findByRole('dialog');
    await user.click(await within(dialog).findByRole('button', { name: 'Invoices' }));
    await user.click(within(dialog).getByRole('button', { name: 'workbench.mail.keep_here' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.mail.kept_on_drive'));
    const [path, body] = api.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/workbench/files/from-mail');
    expect(body).toMatchObject({
      message_id: 'm1',
      attachment_id: 'a2',
      filename: 'r.pdf',
      folder_id: 'd1',
    });
    expect(body.idempotency_key).toEqual(expect.any(String));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('says a refusal and leaves the walk open', async () => {
    api.post.mockRejectedValue(new ApiError('taken', 409, { detail: { code: 'name_taken' } }));
    const { user } = kept();
    await user.click(screen.getByRole('button', { name: /workbench\.mail\.keep_on_drive/ }));
    const dialog = await screen.findByRole('dialog');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.mail.keep_here' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('offers nothing for what cannot be read', () => {
    kept([{ ...REPORT, size: 2 * MB }], MB);

    expect(screen.queryByRole('button', { name: /workbench\.mail\.keep_on_drive/ })).toBeNull();
  });

  it('offers nothing without a drive', () => {
    list([REPORT]);

    expect(screen.queryByRole('button', { name: /workbench\.mail\.keep_on_drive/ })).toBeNull();
  });
});

describe('AttachmentList — what LIA can do on a file', () => {
  const REPORT: MailAttachment = {
    id: 'a2',
    filename: 'r.pdf',
    mime_type: 'application/pdf',
    size: 2048,
    previewable: true,
  };
  const read = vi.fn();
  const lines = () => [{ label: 'Read it', icon: Sparkles, onSelect: read }];

  function assisted(attachments = [REPORT], maxBytes = 25 * MB) {
    return renderWithProviders(
      <AttachmentList
        lng="en"
        messageId="m1"
        attachments={attachments}
        maxBytes={maxBytes}
        drive={{ provider: 'google_drive' }}
        lines={lines}
      />
    );
  }

  it('gains no control on a row: one icon stands where the drive’s did', () => {
    assisted();

    const row = screen.getByRole('listitem');
    expect(within(row).getAllByRole('button')).toHaveLength(2);
    expect(within(row).getAllByRole('link')).toHaveLength(1);
    expect(
      within(row).queryByRole('button', { name: /workbench\.mail\.keep_on_drive/ })
    ).toBeNull();
  });

  it('lists what LIA does beside the drive, and runs nothing until a line is pressed', async () => {
    const { user } = assisted();

    await user.click(
      screen.getByRole('button', { name: /workbench\.assist\.mail\.attachment_menu/ })
    );
    expect(read).not.toHaveBeenCalled();
    expect(
      await screen.findByRole('menuitem', { name: /workbench\.mail\.keep_on_drive/ })
    ).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Read it' }));

    expect(read).toHaveBeenCalledOnce();
  });

  it('offers nothing of LIA on a file past the ceiling', () => {
    assisted([{ ...REPORT, size: 2 * MB }], MB);

    expect(
      screen.queryByRole('button', { name: /workbench\.assist\.mail\.attachment_menu/ })
    ).toBeNull();
  });
});

describe('AttachmentList', () => {
  it('shows nothing for a message without files', () => {
    const { container } = list([]);

    expect(container).toBeEmptyDOMElement();
  });

  it('downloads each file through the API in a tab that cannot reach back', () => {
    list([
      { id: 'att-1', filename: 'report.pdf', mime_type: 'application/pdf', size: 2048 },
      { id: null, filename: 'notes.txt', mime_type: 'text/plain', size: null },
    ]);

    const section = screen.getByRole('region', { name: 'workbench.mail.attachments(2)' });
    const [sized, unsized] = within(section).getAllByRole('link');
    expect(sized).toHaveAccessibleName(
      `workbench.mail.download_sized(report.pdf|${fileSize(2048, 'en')})`
    );
    expect(sized).toHaveAttribute('target', '_blank');
    expect(sized).toHaveAttribute('rel', 'noopener noreferrer');
    const href = new URL(sized.getAttribute('href') ?? '', 'https://lia.example');
    expect(href.pathname.endsWith('/workbench/mail/attachment')).toBe(true);
    expect(Object.fromEntries(href.searchParams)).toEqual({
      message_id: 'm1',
      attachment_id: 'att-1',
      filename: 'report.pdf',
    });
    // A handle the provider did not give travels by its name alone.
    expect(unsized).toHaveAccessibleName('workbench.mail.download(notes.txt)');
    const unnamed = new URL(unsized.getAttribute('href') ?? '', 'https://lia.example');
    expect(unnamed.searchParams.has('attachment_id')).toBe(false);
  });

  it('lists a file past the ceiling as too large, with no download to refuse', () => {
    list(
      [
        { id: 'big', filename: 'video.mp4', mime_type: 'video/mp4', size: 30 * MB },
        { id: 'edge', filename: 'scan.pdf', mime_type: 'application/pdf', size: 25 * MB },
      ],
      25 * MB
    );

    const big = screen.getByText('video.mp4').closest('li') as HTMLElement;
    expect(within(big).queryByRole('link')).toBeNull();
    expect(big).toHaveTextContent(
      `workbench.mail.attachment_too_large(${fileSize(25 * MB, 'en')})`
    );
    // Exactly the ceiling is still served.
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('names a file the provider left unnamed', () => {
    list([{ id: 'x', filename: '', mime_type: 'application/octet-stream', size: 10 }]);

    expect(screen.getByText('workbench.mail.unnamed_attachment')).toBeInTheDocument();
  });
});
