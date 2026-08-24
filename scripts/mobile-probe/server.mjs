/**
 * Measurement server for the native-WebView capability probe.
 *
 * It serves `page.html` under LIA's REAL production security headers. Those
 * headers are IMPORTED from `apps/web/src/lib/csp.ts` — the same pure module
 * `next.config.ts` and `csp.test.ts` use — so the probe can never drift from
 * what production actually serves. Copying the policy here would recreate
 * exactly the duplication that module exists to prevent.
 *
 * The probe page POSTs its findings to `/result`; `run.mjs` awaits them.
 *
 * `Set-Cookie` is emitted on the FIRST document only. A second app launch
 * therefore proves whether the WebView's cookie store survived a cold restart:
 * a non-persistent store (WKWebView's default when misconfigured) silently
 * signs the user out on every launch, and nothing else surfaces it.
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { buildAppCsp, resolveCoepMode, buildHsts } from '../../apps/web/src/lib/csp.ts';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Sentinel session value: proves the server received the httpOnly cookie. */
export const SESSION_SENTINEL = 'probe-session-sentinel';

/** Cookie name LIA uses in production (`SecuritySettings.session_cookie_name`). */
const SESSION_COOKIE = 'lia_session';

/** Sentinel for the cross-site API cookie (see the API server below). */
export const API_SENTINEL = 'probe-api-sentinel';

/**
 * Build the production response headers for a probe document.
 *
 * @param {string|undefined} coepRaw - Value to resolve through `resolveCoepMode`.
 * @param {string} apiUrl - Separate API origin, as `NEXT_PUBLIC_API_URL` in
 *   production (`https://lia-back.…` next to the web app on `https://lia.…`).
 *   Passing it makes `connect-src` carry that origin, exactly as production does.
 * @returns {Record<string,string>} Header map mirroring `next.config.ts`.
 */
export function productionHeaders(coepRaw, apiUrl = '') {
  return {
    'Strict-Transport-Security': buildHsts(),
    'X-DNS-Prefetch-Control': 'on',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'origin-when-cross-origin',
    'Cross-Origin-Embedder-Policy': resolveCoepMode(coepRaw),
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Content-Security-Policy': buildAppCsp(false, apiUrl),
  };
}

/**
 * Start the cross-site "API" origin.
 *
 * Production puts the API on a SEPARATE ORIGIN (`connect-src` on
 * lia.jeyswork.com names https://lia-back.jeyswork.com), so every authenticated
 * call is a cross-origin credentialed request — a different code path from the
 * same-origin case, and one Android WebView can break on its own: unlike Chrome,
 * `CookieManager.setAcceptThirdPartyCookies` defaults to FALSE there.
 *
 * `localhost` and `127.0.0.1` are distinct sites for cookie purposes, so this
 * pair exercises the STRICTER case than production's same-site split — if the
 * cookie survives here, it survives there.
 *
 * @param {number} port - Port to listen on (bound to 127.0.0.1).
 * @returns {Promise<{close: () => Promise<void>}>} Handle to shut it down.
 */
export async function startApiOrigin(port) {
  const cors = origin => ({
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    Vary: 'Origin',
  });

  const server = createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const origin = req.headers.origin || '*';

    if (url.pathname === '/set') {
      res.writeHead(200, {
        'Content-Type': 'text/plain',
        // SameSite=None is mandatory for a cross-site credentialed cookie, and
        // it requires Secure — which Chromium accepts on a loopback host even
        // over plain HTTP, because loopback counts as a trustworthy origin.
        'Set-Cookie': `api_session=${API_SENTINEL}; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=3600`,
        ...cors(origin),
      });
      res.end('set');
      return;
    }

    res.writeHead(200, { 'Content-Type': 'text/plain', ...cors(origin) });
    res.end(req.headers.cookie || '(no cookie)');
  });

  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  return { close: () => new Promise(resolve => server.close(resolve)) };
}

/**
 * Start the probe server.
 *
 * @param {{port?: number, coep?: string, expected?: number, apiUrl?: string}}
 *   options - Listen port, COEP mode, how many probe runs to await, and the
 *   separate API origin to declare in `connect-src`.
 * @returns {Promise<{close: () => Promise<void>, results: Promise<object[]>, port: number}>}
 */
export async function startProbeServer({ port = 8787, coep, expected = 1, apiUrl = '' } = {}) {
  const template = await readFile(join(HERE, 'page.html'), 'utf8');
  const page = template.replace('__API_ORIGIN__', apiUrl);
  const headers = productionHeaders(coep, apiUrl);

  const collected = [];
  let documentsServed = 0;
  let resolveResults;
  const results = new Promise(resolve => {
    resolveResults = resolve;
  });

  const server = createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');

    if (url.pathname === '/sse') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      let sent = 0;
      const timer = setInterval(() => {
        res.write(`data: tick ${++sent}\n\n`);
        if (sent >= 5) {
          clearInterval(timer);
          res.end();
        }
      }, 200);
      req.on('close', () => clearInterval(timer));
      return;
    }

    if (url.pathname === '/sw.js') {
      res.writeHead(200, {
        'Content-Type': 'application/javascript',
        'Service-Worker-Allowed': '/',
      });
      res.end("self.addEventListener('install', () => self.skipWaiting());\n");
      return;
    }

    if (url.pathname === '/whoami') {
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', ...headers });
      res.end(req.headers.cookie || '(no cookie)');
      return;
    }

    if (url.pathname === '/result' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => {
        body += chunk;
      });
      req.on('end', () => {
        res.writeHead(204, headers);
        res.end();
        try {
          collected.push(JSON.parse(body));
        } catch (error) {
          collected.push({ parse_error: String(error), raw: body });
        }
        if (collected.length >= expected) {
          resolveResults(collected);
        }
      });
      return;
    }

    documentsServed += 1;
    const documentHeaders = { 'Content-Type': 'text/html; charset=utf-8', ...headers };
    if (documentsServed === 1) {
      // httpOnly + Max-Age mirrors production: persistent, JS-invisible.
      documentHeaders['Set-Cookie'] = [
        `${SESSION_COOKIE}=${SESSION_SENTINEL}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
        'NEXT_LOCALE=fr; Path=/; SameSite=Lax; Max-Age=3600',
      ];
    }
    res.writeHead(200, documentHeaders);
    res.end(page);
  });

  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));

  return {
    port,
    results,
    close: () => new Promise(resolve => server.close(resolve)),
  };
}
