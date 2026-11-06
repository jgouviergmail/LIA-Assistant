/**
 * A PDF opened in the page, through PDF.js (ADR-369, lot 14).
 *
 * The one module that speaks to the library, loaded when a PDF is first shown, in its legacy
 * build: a WebView can be older than the browsers the main build asks for. A sender's file is
 * parsed in the library's worker. This version evaluates no code of any kind (the road of
 * CVE-2024-4367 is gone, its option with it), and the page's policy would refuse it. Forms are not
 * drawn, and no annotation layer is, so nothing in a file acts. The worker and the data it reads
 * come from the app itself (`scripts/copy-pdf-runtime.mjs`), which asks no third party for
 * anything.
 */
import type { PDFDocumentProxy } from 'pdfjs-dist';

type Library = typeof import('pdfjs-dist/legacy/build/pdf.mjs');

/** Past two device pixels, a page costs memory nobody sees. */
const MAX_PIXEL_RATIO = 2;
const LOCKED = 'PasswordException';

/** Where a page is drawn: its picture, and its words above it for a reader to select. */
export interface PdfSurface {
  canvas: HTMLCanvasElement;
  words: HTMLElement;
}

export interface PdfDrawing {
  /** The page's height over its width; null when it was let go before the end. */
  done: Promise<number | null>;
  /** Stops the drawing and gives back what it held. */
  stop: () => void;
}

export interface PdfDocument {
  pages: number;
  /**
   * @param number - The page, from 1.
   * @param surface - Where it is drawn.
   * @param width - Its width, in CSS pixels.
   */
  draw: (number: number, surface: PdfSurface, width: number) => PdfDrawing;
  close: () => void;
}

/** A PDF only its password opens: the page says so rather than « could not be read ». */
export function isLockedPdf(error: unknown): boolean {
  return error instanceof Error && error.name === LOCKED;
}

function drawPage(
  library: Library,
  pdf: PDFDocumentProxy,
  number: number,
  { canvas, words }: PdfSurface,
  width: number
): PdfDrawing {
  let stopped = false;
  let halt = () => {};
  const painted = async (): Promise<number | null> => {
    const page = await pdf.getPage(number);
    if (stopped) return null;
    const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width });
    const pixels = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
    canvas.width = Math.floor(viewport.width * pixels);
    canvas.height = Math.floor(viewport.height * pixels);
    words.style.setProperty('--total-scale-factor', String(viewport.scale));
    const painting = page.render({ canvas, viewport, transform: [pixels, 0, 0, pixels, 0, 0] });
    const layer = new library.TextLayer({
      textContentSource: page.streamTextContent({ includeMarkedContent: true }),
      container: words,
      viewport,
    });
    halt = () => {
      painting.cancel();
      layer.cancel();
    };
    await Promise.all([painting.promise, layer.render()]);
    return viewport.height / viewport.width;
  };
  return {
    done: painted().catch((error: unknown) => {
      if (stopped) return null;
      throw error;
    }),
    stop: () => {
      stopped = true;
      halt();
      canvas.width = 0;
      canvas.height = 0;
      words.replaceChildren();
    },
  };
}

/**
 * @param data - The file: somebody else's.
 * @returns The document, for the caller to close.
 * @throws When it is no PDF, or only its password opens it (`isLockedPdf`).
 */
export async function openPdf(data: Blob): Promise<PdfDocument> {
  const library = await import('pdfjs-dist/legacy/build/pdf.mjs');
  const runtime = `/pdfjs/${library.version}/`;
  library.GlobalWorkerOptions.workerSrc = `${runtime}pdf.worker.min.mjs`;
  const loading = library.getDocument({
    data: new Uint8Array(await data.arrayBuffer()),
    cMapUrl: `${runtime}cmaps/`,
    standardFontDataUrl: `${runtime}standard_fonts/`,
    wasmUrl: `${runtime}wasm/`,
    enableXfa: false,
  });
  const pdf = await loading.promise;
  return {
    pages: pdf.numPages,
    draw: (number, surface, width) => drawPage(library, pdf, number, surface, width),
    close: () => void loading.destroy(),
  };
}
