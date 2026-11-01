/**
 * A message's files (ADR-369): each a download through the API's own door,
 * opened in a new tab that cannot reach back (a refusal never replaces the
 * screen); a file past the published ceiling is listed and said too large,
 * never offered for a download that would be refused; a file without a name
 * or a size is still listed.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { fileSize } from '@/lib/workbench/mail';
import type { MailAttachment } from '@/lib/workbench/types';

const { i18n } = vi.hoisted(() => ({
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { AttachmentList } from '../AttachmentList';

const MB = 1024 * 1024;

function list(attachments: MailAttachment[], maxBytes = 25 * MB) {
  return renderWithProviders(
    <AttachmentList lng="en" messageId="m1" attachments={attachments} maxBytes={maxBytes} />
  );
}

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
