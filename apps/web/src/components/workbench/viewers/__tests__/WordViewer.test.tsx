/**
 * A Word file in the page (ADR-369, lot 14), from a real file through the real library: what its
 * author wrote is shown in the sealed frame, disarmed, and a file that cannot be read says so.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

vi.mock('next-themes', async importOriginal => ({
  ...(await importOriginal<typeof import('next-themes')>()),
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

import { WordViewer } from '../WordViewer';

async function fixture(name: string): Promise<Blob> {
  const bytes = await readFile(join(process.cwd(), 'e2e/fixtures/viewers', name));
  return new Blob([new Uint8Array(bytes)]);
}

async function frameOf(data: Blob): Promise<HTMLIFrameElement> {
  renderWithProviders(<WordViewer lng="en" data={data} name="report.docx" />);
  const frame = await screen.findByTitle('report.docx', {}, { timeout: 5000 });
  if (!(frame instanceof HTMLIFrameElement)) throw new Error('not a frame');
  return frame;
}

describe('WordViewer', () => {
  it('shows the file in a frame with no script and no reach', async () => {
    const frame = await frameOf(await fixture('report.docx'));

    expect(frame.getAttribute('srcdoc')).toContain('Proof report');
    expect(frame.getAttribute('sandbox')).toBe('allow-popups allow-popups-to-escape-sandbox');
  });

  it('keeps a web link, in a tab that cannot reach back', async () => {
    const frame = await frameOf(await fixture('report.docx'));

    const page = new DOMParser().parseFromString(frame.getAttribute('srcdoc') ?? '', 'text/html');
    const link = page.querySelector('a[href^="https:"]');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('leaves a hostile link its words and no address', async () => {
    const frame = await frameOf(await fixture('hostile.docx'));

    const source = frame.getAttribute('srcdoc') ?? '';
    expect(source).toContain('a trap');
    expect(source).not.toContain('javascript:');
  });

  it('offers no remote image: a file loads nothing from elsewhere', async () => {
    await frameOf(await fixture('report.docx'));

    expect(screen.queryByRole('button', { name: 'workbench.mail.show_images' })).toBeNull();
  });

  it('says a file that cannot be read', async () => {
    renderWithProviders(<WordViewer lng="en" data={new Blob(['no archive'])} name="report.docx" />);

    await waitFor(() =>
      expect(screen.getByText('workbench.files.reading_failed')).toBeInTheDocument()
    );
  });
});
