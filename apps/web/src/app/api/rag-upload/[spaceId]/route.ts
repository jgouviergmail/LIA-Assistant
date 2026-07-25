/**
 * API Route handler for RAG document uploads.
 *
 * Proxies multipart uploads to the backend API. Next.js rewrites don't honor
 * NODE_TLS_REJECT_UNAUTHORIZED for large multipart bodies (EPIPE/ECONNRESET
 * against the dev self-signed cert), so this route talks to the API directly
 * with a Node agent instead of going through the rewrite.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-15
 *
 * SEC-006 — this endpoint used to materialise the whole request with
 * `request.arrayBuffer()` *before* authenticating or checking any size, so
 * anonymous concurrent POSTs could exhaust the Node heap of the frontend
 * container. It now admits a request in this order: UUID shape → session
 * present → session actually valid upstream → concurrency slot →
 * `Content-Length` → bounded streaming read. Nothing is buffered until every
 * one of those passes.
 */

import { NextRequest, NextResponse } from 'next/server';
import https from 'https';
import http from 'http';
import type { IncomingMessage } from 'http';

const API_URL_SERVER = process.env.API_URL_SERVER || 'https://api:8000';

/** HTTPS agent that accepts self-signed certificates (dev only). */
const isDev = process.env.NODE_ENV !== 'production';
const httpsAgent = new https.Agent({ rejectUnauthorized: !isDev });

/**
 * Strict RFC 4122 UUID matcher (any version).
 *
 * SEC-017: `spaceId` is interpolated into the upstream URL, and WHATWG URL
 * parsing resolves `..` segments — so an encoded value like `..%2f..%2fauth`
 * could retarget a *different* backend route (route escape). Pinning the segment
 * to a strict UUID shape (no slash, backslash, dot-segment, query, fragment or
 * control char can pass) closes that class entirely before any work happens.
 */
const SPACE_ID_UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Name of the session cookie.
 *
 * FN-2: only this cookie is forwarded upstream. The handler used to relay the
 * entire `Cookie` header, which hands every unrelated cookie of the origin
 * (analytics, feature flags, anything a future feature sets) to a request the
 * user did not aim at them.
 */
const SESSION_COOKIE_NAME = 'lia_session';

/**
 * Per-file ceiling, in bytes — mirrors `RAG_SPACES_MAX_FILE_SIZE_MB_DEFAULT`
 * on the backend, read from the SAME `.env` both containers load — a hardcoded
 * copy would silently reject valid uploads the moment an operator raises the
 * backend limit, with a 413 no backend log explains. The backend re-checks it
 * anyway; this exists so an oversized body is refused before it costs the
 * frontend anything.
 */
const DEFAULT_MAX_FILE_MB = 20;
const parsedMaxFileMb = Number.parseInt(process.env.RAG_SPACES_MAX_FILE_SIZE_MB ?? '', 10);
const MAX_FILE_BYTES =
  (Number.isFinite(parsedMaxFileMb) && parsedMaxFileMb > 0 ? parsedMaxFileMb : DEFAULT_MAX_FILE_MB) *
  1024 *
  1024;

/**
 * Ceiling for the whole multipart body: the file plus its MIME envelope
 * (boundaries, headers, field names). 1 MB of slack over the file limit is far
 * more than any real envelope, and keeps the error attributable to the file
 * size rather than to framing.
 */
const MAX_BODY_BYTES = MAX_FILE_BYTES + 1024 * 1024;

/**
 * Ceiling for the upstream response we buffer. The backend answers with a JSON
 * document descriptor; anything beyond this is a malfunction, not a payload.
 */
const MAX_UPSTREAM_RESPONSE_BYTES = 1024 * 1024;

/** Upstream request timeout. Generous: the backend parses and embeds the file. */
const UPSTREAM_TIMEOUT_MS = 120_000;

/** Timeout for the pre-flight session check — a cheap call on the internal network. */
const AUTH_CHECK_TIMEOUT_MS = 5_000;

/**
 * Concurrent uploads this process will admit.
 *
 * Sized against the memory this route can hold at once: each admitted upload may
 * buffer up to `MAX_BODY_BYTES` (21 MB), so 4 slots bound the route at ~84 MB —
 * survivable on the 8 GB Raspberry Pi that also runs the API, Postgres and the
 * observability stack. Without a budget, the per-request cap alone is not a
 * memory bound: N concurrent requests cost N × 21 MB.
 */
const MAX_CONCURRENT_UPLOADS = 4;

let activeUploads = 0;

/** JSON error with the shape the frontend already parses (`detail`). */
function errorResponse(status: number, detail: string): NextResponse {
  return NextResponse.json({ detail }, { status });
}

/**
 * Extract a single cookie value from a raw `Cookie` header.
 *
 * @param header - Raw `Cookie` header, or null.
 * @param name - Cookie name to extract.
 * @returns The raw value, or null when absent.
 */
function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) return part.slice(eq + 1).trim();
  }
  return null;
}

/**
 * Read a request body into memory, refusing to exceed `MAX_BODY_BYTES`.
 *
 * Counts the bytes actually received rather than trusting `Content-Length`: a
 * client can omit it, understate it, or use chunked transfer encoding. The
 * stream is cancelled as soon as the ceiling is crossed, so an oversized upload
 * costs at most one chunk beyond the limit.
 *
 * @param request - Incoming request.
 * @returns The body, or null when the ceiling was exceeded.
 */
async function readBoundedBody(request: NextRequest): Promise<Buffer | null> {
  const stream = request.body;
  if (!stream) return Buffer.alloc(0);

  const reader = stream.getReader();
  const chunks: Buffer[] = [];
  let total = 0;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;

      total += value.byteLength;
      if (total > MAX_BODY_BYTES) {
        await reader.cancel().catch(() => undefined);
        return null;
      }
      chunks.push(Buffer.from(value));
    }
  } finally {
    reader.releaseLock();
  }

  return Buffer.concat(chunks);
}

/** Outcome of an upstream call: never carries a transport error message. */
interface UpstreamResult {
  status: number;
  body: string;
  contentType: string;
}

/**
 * Perform one upstream request with the Node agent.
 *
 * A single transport on purpose (SEC-006): the previous implementation tried
 * `fetch` first and fell back to `http.request` on failure, which can replay a
 * whole upload when the first attempt failed *after* the backend already
 * accepted it — a duplicate document from an ambiguous error.
 *
 * @param url - Absolute upstream URL.
 * @param options - Method, headers and timeout.
 * @param payload - Optional request body.
 * @returns Status, bounded body and content type.
 */
function requestUpstream(
  url: string,
  options: { method: string; headers: Record<string, string>; timeoutMs: number },
  payload?: Buffer
): Promise<UpstreamResult> {
  return new Promise<UpstreamResult>((resolve, reject) => {
    const parsed = new URL(url);
    const isHttps = parsed.protocol === 'https:';
    const mod = isHttps ? https : http;

    const req = mod.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: `${parsed.pathname}${parsed.search}`,
        method: options.method,
        headers: options.headers,
        ...(isHttps ? { agent: httpsAgent } : {}),
      },
      (res: IncomingMessage) => {
        const chunks: Buffer[] = [];
        let received = 0;
        let truncated = false;

        res.on('data', (chunk: Buffer) => {
          received += chunk.length;
          if (received > MAX_UPSTREAM_RESPONSE_BYTES) {
            // Bound the response too: an upstream malfunction must not be able
            // to exhaust this process's memory either.
            truncated = true;
            res.destroy();
            return;
          }
          chunks.push(chunk);
        });

        res.on('close', () => {
          if (truncated) {
            resolve({
              status: 502,
              body: JSON.stringify({ detail: 'Upstream response too large' }),
              contentType: 'application/json',
            });
          }
        });

        res.on('end', () => {
          resolve({
            status: res.statusCode || 502,
            body: Buffer.concat(chunks).toString('utf-8'),
            contentType: res.headers['content-type'] || 'application/json',
          });
        });

        // A reset mid-response emits 'error' on the response, not on the
        // request. Without this the promise would never settle and the upload
        // would hold its concurrency slot until the socket timeout fired.
        res.on('error', reject);
      }
    );

    req.setTimeout(options.timeoutMs, () => req.destroy(new Error('timeout')));
    req.on('error', reject);

    if (payload) req.write(payload);
    req.end();
  });
}

/**
 * Validate the session upstream before the body is read.
 *
 * Cookie *presence* is not authentication — any client can send an arbitrary
 * value — so the session is resolved against the API. This is what makes the
 * body read safe to perform: by the time a single byte is buffered, the caller
 * is known.
 *
 * @param sessionCookie - Raw session cookie value.
 * @returns True when the session is valid.
 */
async function isSessionValid(sessionCookie: string): Promise<boolean> {
  try {
    const result = await requestUpstream(`${API_URL_SERVER}/api/v1/auth/me`, {
      method: 'GET',
      headers: { cookie: `${SESSION_COOKIE_NAME}=${sessionCookie}` },
      timeoutMs: AUTH_CHECK_TIMEOUT_MS,
    });
    return result.status === 200;
  } catch {
    // Upstream unreachable — fail closed rather than admit an unverified body.
    return false;
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ spaceId: string }> }
) {
  const { spaceId } = await params;

  // SEC-017: reject a non-UUID spaceId up front — before reading the body or
  // building the upstream URL — so it can never escape to another route.
  if (!SPACE_ID_UUID_RE.test(spaceId)) {
    return errorResponse(400, 'Invalid space id');
  }

  // SEC-006 step 1: no session cookie at all → refuse without reading anything.
  const sessionCookie = readCookie(request.headers.get('cookie'), SESSION_COOKIE_NAME);
  if (!sessionCookie) {
    return errorResponse(401, 'Authentication required');
  }

  // SEC-006 step 2: a cookie is not a session — resolve it upstream first.
  if (!(await isSessionValid(sessionCookie))) {
    return errorResponse(401, 'Authentication required');
  }

  // SEC-006 step 3: bound how much this process can hold at once. Checked after
  // authentication so an anonymous flood cannot consume the slots themselves.
  if (activeUploads >= MAX_CONCURRENT_UPLOADS) {
    return errorResponse(503, 'Too many concurrent uploads, please retry');
  }
  activeUploads += 1;

  try {
    // SEC-006 step 4: refuse an over-limit declared length before reading. The
    // header is a hint, not a guarantee — the streaming counter below is what
    // actually enforces the ceiling.
    const declaredLength = Number(request.headers.get('content-length'));
    if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
      return errorResponse(413, 'File too large');
    }

    // SEC-006 step 5: count the bytes actually received and stop at the ceiling.
    const body = await readBoundedBody(request);
    if (body === null) {
      return errorResponse(413, 'File too large');
    }

    // spaceId is a validated UUID; encodeURIComponent is defense in depth so the
    // segment can never widen the path even if the guard above is ever loosened.
    const targetUrl = `${API_URL_SERVER}/api/v1/rag-spaces/${encodeURIComponent(spaceId)}/documents`;

    const upstream = await requestUpstream(
      targetUrl,
      {
        method: 'POST',
        headers: {
          'content-type': request.headers.get('content-type') || 'application/octet-stream',
          'content-length': String(body.byteLength),
          cookie: `${SESSION_COOKIE_NAME}=${sessionCookie}`,
        },
        timeoutMs: UPSTREAM_TIMEOUT_MS,
      },
      body
    );

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { 'content-type': upstream.contentType },
    });
  } catch {
    // Never surface the transport error: it leaks internal hostnames, ports and
    // certificate details to the client.
    return errorResponse(502, 'Upload failed');
  } finally {
    activeUploads -= 1;
  }
}
