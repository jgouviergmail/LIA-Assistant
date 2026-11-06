/**
 * What is asked of PDF.js (ADR-369, lot 14). The library itself is proven in a browser
 * (`e2e/smoke/workbench-files.spec.ts`); here, what the page owes it: its runtime comes from the
 * app, forms stay out, a page let go gives everything back, and a page that fails says so.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { library, page, loading, drawn } = vi.hoisted(() => {
  const page = { getViewport: vi.fn(), render: vi.fn(), streamTextContent: vi.fn() };
  const loading = { promise: Promise.resolve({}), destroy: vi.fn() };
  const drawn = { words: { render: vi.fn(), cancel: vi.fn() } };
  const library = {
    version: '9.9.9',
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: vi.fn(),
    TextLayer: class {
      render = () => drawn.words.render();
      cancel = () => drawn.words.cancel();
    },
  };
  return { library, page, loading, drawn };
});
vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => library);

import { isLockedPdf, openPdf, type PdfSurface } from '../pdf-document';

const VIEW = { width: 300, height: 450, scale: 0.5 };

function surface(): PdfSurface {
  return { canvas: document.createElement('canvas'), words: document.createElement('div') };
}

function painting(promise: Promise<void> = Promise.resolve()) {
  return { promise, cancel: vi.fn() };
}

function layer(render: Promise<void> = Promise.resolve()) {
  return { render: vi.fn(() => render), cancel: vi.fn() };
}

function pdfOf(getPage = vi.fn().mockResolvedValue(page)) {
  loading.promise = Promise.resolve({ numPages: 3, getPage });
  library.getDocument.mockReturnValue(loading);
}

beforeEach(() => {
  vi.clearAllMocks();
  page.getViewport.mockReturnValue(VIEW);
  page.render.mockReturnValue(painting());
  pdfOf();
  drawn.words = layer();
});

describe('openPdf', () => {
  it('reads its worker and its data from the app, at the version it runs', async () => {
    await openPdf(new Blob(['%PDF']));

    expect(library.GlobalWorkerOptions.workerSrc).toBe('/pdfjs/9.9.9/pdf.worker.min.mjs');
    expect(library.getDocument).toHaveBeenCalledWith(
      expect.objectContaining({
        cMapUrl: '/pdfjs/9.9.9/cmaps/',
        standardFontDataUrl: '/pdfjs/9.9.9/standard_fonts/',
        wasmUrl: '/pdfjs/9.9.9/wasm/',
        enableXfa: false,
      })
    );
  });

  it('hands the library the file’s bytes', async () => {
    await openPdf(new Blob(['%PDF']));

    const asked = library.getDocument.mock.calls[0]?.[0] as { data: Uint8Array };
    expect(new TextDecoder().decode(asked.data)).toBe('%PDF');
  });

  it('says how many pages it holds, and closes', async () => {
    const pdf = await openPdf(new Blob(['%PDF']));

    pdf.close();

    expect(pdf.pages).toBe(3);
    expect(loading.destroy).toHaveBeenCalledTimes(1);
  });

  it('lets a refusal through', async () => {
    const locked = Object.assign(new Error('locked'), { name: 'PasswordException' });
    loading.promise = Promise.reject(locked);
    library.getDocument.mockReturnValue(loading);

    const refused = await openPdf(new Blob(['%PDF'])).catch((error: unknown) => error);

    expect(isLockedPdf(refused)).toBe(true);
  });
});

describe('isLockedPdf', () => {
  it('tells nothing else for a locked file', () => {
    expect(isLockedPdf(new Error('invalid'))).toBe(false);
    expect(isLockedPdf('PasswordException')).toBe(false);
  });
});

describe('a page', () => {
  it('is drawn at the width asked, and answers its shape', async () => {
    const pdf = await openPdf(new Blob(['%PDF']));
    const target = surface();

    const shape = await pdf.draw(2, target, 300).done;

    expect(shape).toBe(1.5);
    expect(target.canvas.width).toBeGreaterThanOrEqual(300);
    expect(target.words.style.getPropertyValue('--total-scale-factor')).toBe('0.5');
    expect(page.render).toHaveBeenCalledWith(expect.objectContaining({ canvas: target.canvas }));
  });

  it('stops what is under way and gives back what it holds', async () => {
    const paint = painting(new Promise(() => undefined));
    const words = layer(new Promise(() => undefined));
    page.render.mockReturnValue(paint);
    drawn.words = words;
    const pdf = await openPdf(new Blob(['%PDF']));
    const target = surface();
    target.words.append(document.createElement('span'));
    const drawing = pdf.draw(1, target, 300);
    await vi.waitFor(() => expect(page.render).toHaveBeenCalled());

    drawing.stop();

    expect(paint.cancel).toHaveBeenCalledTimes(1);
    expect(words.cancel).toHaveBeenCalledTimes(1);
    expect(target.canvas.width).toBe(0);
    expect(target.words.childElementCount).toBe(0);
  });

  it('draws nothing when it was let go before it arrived', async () => {
    let arrive: (value: typeof page) => void = () => undefined;
    pdfOf(vi.fn().mockReturnValue(new Promise(resolve => (arrive = resolve))));
    const pdf = await openPdf(new Blob(['%PDF']));
    const drawing = pdf.draw(1, surface(), 300);

    drawing.stop();
    arrive(page);

    await expect(drawing.done).resolves.toBeNull();
    expect(page.render).not.toHaveBeenCalled();
  });

  it('calls a drawing stopped midway no failure', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    page.render.mockReturnValue(painting(new Promise((_, reject) => (refuse = reject))));
    const pdf = await openPdf(new Blob(['%PDF']));
    const drawing = pdf.draw(1, surface(), 300);
    await vi.waitFor(() => expect(page.render).toHaveBeenCalled());

    drawing.stop();
    refuse(new Error('cancelled'));

    await expect(drawing.done).resolves.toBeNull();
  });

  it('says a page that could not be drawn', async () => {
    page.render.mockReturnValue(painting(Promise.reject(new Error('broken'))));
    const pdf = await openPdf(new Blob(['%PDF']));

    await expect(pdf.draw(1, surface(), 300).done).rejects.toThrow('broken');
  });
});
