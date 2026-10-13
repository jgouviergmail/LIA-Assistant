/**
 * What Playwright can READ of the browser differs by engine, and a journey must
 * not turn a tool's blind spot into a product verdict.
 *
 * Measured on 2026-10-13 in the matrix image (Playwright 1.63, Linux), with a
 * probe that sent the same requests to the three engines:
 * - WebKit exposes no `Cookie` header on an intercepted request (Chromium and
 *   Firefox do), and no file CONTENT in a multipart body — its part headers,
 *   file name included, are there;
 * - only Chromium emits a `download` event for a download started in a
 *   subframe (the export card's hidden transfer iframe): Firefox and WebKit
 *   request the file once and render nothing inline, but Playwright reports
 *   no download, with or without the iframe's sandbox.
 * - WebKit refuses to fulfil an intercepted request with a redirect status
 *   ("Cannot fulfill with redirect status: 302").
 *
 * Each helper keeps the assertion where the engine lets Playwright observe it,
 * and records the gap as a test annotation elsewhere, so a report never reads
 * a skipped check as a passed one.
 */
import { expect, test, type Request, type Route } from '@playwright/test';

type Engine = string;

function annotate(description: string): void {
  test.info().annotations.push({ type: 'engine-limit', description });
}

/** The request carried the session cookie, where the engine shows it. */
export async function expectSessionCookie(
  request: Request,
  engine: Engine,
  cookie: string
): Promise<void> {
  if (engine === 'webkit') {
    annotate('WebKit exposes no Cookie header on an intercepted request');
    return;
  }
  expect((await request.allHeaders()).cookie).toContain(cookie);
}

/** The multipart body carried the file — its name always, its content where readable. */
export function expectMultipartFile(
  request: Request,
  engine: Engine,
  file: { name: string; content: string }
): void {
  const body = request.postDataBuffer()?.toString('latin1') ?? '';
  expect(body).toContain(file.name);
  if (engine === 'webkit') {
    annotate('WebKit exposes no file content in an intercepted multipart body');
    return;
  }
  expect(body).toContain(file.content);
}

/** Whether Playwright reports a download started in a subframe on this engine. */
export function observesSubframeDownloads(engine: Engine): boolean {
  if (engine === 'chromium') return true;
  annotate(`${engine}: Playwright emits no download event for a subframe download`);
  return false;
}

/**
 * Answer with a redirect to `location`: a real 302 where the engine lets a
 * route fulfil one, a zero-delay meta refresh (no script, CSP-neutral) on WebKit.
 */
export async function fulfillRedirect(route: Route, engine: Engine, location: string): Promise<void> {
  if (engine !== 'webkit') {
    await route.fulfill({ status: 302, headers: { Location: location }, body: '' });
    return;
  }
  annotate('WebKit cannot fulfil an intercepted request with a redirect status');
  const target = location.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  await route.fulfill({
    contentType: 'text/html',
    body: `<!doctype html><meta http-equiv="refresh" content="0;url=${target}">`,
  });
}
