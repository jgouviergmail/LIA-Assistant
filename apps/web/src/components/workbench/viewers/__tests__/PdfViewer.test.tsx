/**
 * A PDF read in the page (ADR-369, lot 14). What the library draws is proven in a browser
 * (`e2e/smoke/workbench-files.spec.ts`); here, what the viewer owes around it: a page is drawn
 * while it is near and given back when it leaves, the reader chooses its size, a document is
 * closed once, and what cannot be read says why.
 */
import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { PdfDocument } from '@/lib/workbench/pdf-document';

const { port, i18n } = vi.hoisted(() => ({
  port: { openPdf: vi.fn(), isLockedPdf: vi.fn() },
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/lib/workbench/pdf-document', () => port);

import { PdfViewer } from '../PdfViewer';

const DATA = new Blob(['%PDF']);
const WIDTH = 600;

/** The pages the screen brought near, by the element each observer watches. */
let watching: Map<Element, IntersectionObserverCallback>;

function near(label: string, isIntersecting = true): void {
  const page = screen.getByRole('group', { name: label });
  const callback = watching.get(page);
  if (!callback) throw new Error('nobody watches this page');
  act(() =>
    callback([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver)
  );
}

class Watcher {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(element: Element): void {
    watching.set(element, this.callback);
  }
  disconnect(): void {}
}

class Measure {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(): void {
    this.callback([{ contentRect: { width: WIDTH } } as ResizeObserverEntry], {} as ResizeObserver);
  }
  disconnect(): void {}
}

function drawing(ratio: number | null = 1.5) {
  return { done: Promise.resolve(ratio), stop: vi.fn<() => void>() };
}

function document(pages: number, draw = vi.fn<PdfDocument['draw']>(() => drawing())) {
  return { pages, draw, close: vi.fn<() => void>() } satisfies PdfDocument;
}

function show(data: Blob = DATA) {
  return renderWithProviders(<PdfViewer lng="en" data={data} name="report.pdf" />);
}

describe('PdfViewer', () => {
  beforeEach(() => {
    watching = new Map();
    vi.stubGlobal('IntersectionObserver', Watcher);
    vi.stubGlobal('ResizeObserver', Measure);
    port.openPdf.mockReset();
    port.isLockedPdf.mockReset();
    port.isLockedPdf.mockReturnValue(false);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('says how many pages it holds, in a region the keyboard reaches', async () => {
    port.openPdf.mockResolvedValue(document(3));

    show();

    expect(await screen.findByText('workbench.files.pdf_pages(3)')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'report.pdf' })).toHaveAttribute('tabindex', '0');
    expect(screen.getAllByRole('group', { name: /workbench\.files\.pdf_page\(/ })).toHaveLength(3);
  });

  it('draws a page only once it comes near, at the width it has', async () => {
    const pdf = document(3);
    port.openPdf.mockResolvedValue(pdf);
    show();
    await screen.findByRole('group', { name: 'workbench.files.pdf_page(2)' });

    expect(pdf.draw).not.toHaveBeenCalled();
    near('workbench.files.pdf_page(2)');

    await waitFor(() => expect(pdf.draw).toHaveBeenCalledTimes(1));
    expect(pdf.draw.mock.calls[0]).toEqual([2, expect.anything(), WIDTH]);
  });

  it('takes the shape its page says', async () => {
    port.openPdf.mockResolvedValue(document(1));
    show();
    const label = 'workbench.files.pdf_page(1)';
    await screen.findByRole('group', { name: label });

    near(label);

    await waitFor(() =>
      expect(screen.getByRole('group', { name: label })).toHaveStyle({ height: '900px' })
    );
  });

  it('gives a page back when it leaves', async () => {
    const drawn = drawing();
    const pdf = document(
      1,
      vi.fn<PdfDocument['draw']>(() => drawn)
    );
    port.openPdf.mockResolvedValue(pdf);
    show();
    const label = 'workbench.files.pdf_page(1)';
    await screen.findByRole('group', { name: label });
    near(label);
    await waitFor(() => expect(pdf.draw).toHaveBeenCalled());

    near(label, false);

    expect(drawn.stop).toHaveBeenCalledTimes(1);
  });

  it('draws a page larger when the reader asks, and back', async () => {
    const pdf = document(1);
    port.openPdf.mockResolvedValue(pdf);
    const { user } = show();
    const label = 'workbench.files.pdf_page(1)';
    await screen.findByRole('group', { name: label });
    near(label);

    await user.click(screen.getByRole('button', { name: 'workbench.files.zoom_in' }));

    await waitFor(() => expect(pdf.draw.mock.lastCall?.[2]).toBe(WIDTH * 1.5));
    expect(screen.getByText('150 %')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'workbench.files.zoom_out' }));

    await waitFor(() => expect(pdf.draw.mock.lastCall?.[2]).toBe(WIDTH));
  });

  it('draws a page smaller than the screen when the reader asks', async () => {
    const pdf = document(1);
    port.openPdf.mockResolvedValue(pdf);
    const { user } = show();
    const label = 'workbench.files.pdf_page(1)';
    await screen.findByRole('group', { name: label });
    near(label);

    await user.click(screen.getByRole('button', { name: 'workbench.files.zoom_out' }));

    await waitFor(() => expect(pdf.draw.mock.lastCall?.[2]).toBe(WIDTH * 0.75));
    expect(screen.getByText('75 %')).toBeInTheDocument();
  });

  it('opens at the width of the screen', async () => {
    port.openPdf.mockResolvedValue(document(1));

    show();

    expect(await screen.findByText('100 %')).toBeInTheDocument();
  });

  it('stops at its bounds without losing the button under the keyboard', async () => {
    const pdf = document(1);
    port.openPdf.mockResolvedValue(pdf);
    const { user } = show();
    const smaller = await screen.findByRole('button', { name: 'workbench.files.zoom_out' });
    expect(smaller).not.toHaveAttribute('aria-disabled');

    await user.click(smaller);
    await user.click(smaller);

    expect(screen.getByText('50 %')).toBeInTheDocument();
    expect(smaller).toHaveAttribute('aria-disabled', 'true');
    expect(smaller).toBeEnabled();
    await user.click(smaller);

    expect(screen.getByText('50 %')).toBeInTheDocument();
  });

  it('says a page that cannot be drawn, and keeps the others', async () => {
    const refused = () => ({ done: Promise.reject(new Error('x')), stop: vi.fn<() => void>() });
    const pdf = document(2, vi.fn<PdfDocument['draw']>(refused));
    port.openPdf.mockResolvedValue(pdf);
    show();
    const label = 'workbench.files.pdf_page(1)';
    await screen.findByRole('group', { name: label });

    near(label);

    expect(await screen.findByText('workbench.files.page_failed')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'workbench.files.pdf_page(2)' })).toBeInTheDocument();
  });

  it('closes the document when it leaves', async () => {
    const pdf = document(1);
    port.openPdf.mockResolvedValue(pdf);
    const { unmount } = show();
    await screen.findByText('workbench.files.pdf_pages(1)');

    unmount();

    expect(pdf.close).toHaveBeenCalledTimes(1);
  });

  it('closes a document that opens once nobody waits for it', async () => {
    const pdf = document(1);
    let opened: (value: PdfDocument) => void = () => undefined;
    port.openPdf.mockReturnValue(new Promise<PdfDocument>(resolve => (opened = resolve)));
    const { unmount } = show();

    unmount();
    await act(async () => opened(pdf));

    expect(pdf.close).toHaveBeenCalledTimes(1);
  });

  it('opens another file in place of the first', async () => {
    const first = document(1);
    const second = document(4);
    port.openPdf.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    const { rerender } = show();
    await screen.findByText('workbench.files.pdf_pages(1)');

    rerender(<PdfViewer lng="en" data={new Blob(['%PDF 2'])} name="other.pdf" />);

    expect(await screen.findByText('workbench.files.pdf_pages(4)')).toBeInTheDocument();
    expect(first.close).toHaveBeenCalledTimes(1);
  });

  it('says a PDF only its password opens', async () => {
    port.openPdf.mockRejectedValue(new Error('locked'));
    port.isLockedPdf.mockReturnValue(true);

    show();

    expect(await screen.findByText('workbench.files.pdf_locked')).toBeInTheDocument();
  });

  it('says a file it cannot read', async () => {
    port.openPdf.mockRejectedValue(new Error('invalid'));

    show();

    expect(await screen.findByText('workbench.files.reading_failed')).toBeInTheDocument();
  });
});
