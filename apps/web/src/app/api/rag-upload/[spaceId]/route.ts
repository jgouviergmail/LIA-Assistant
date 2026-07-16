/**
 * API Route handler for RAG document uploads.
 *
 * Proxies multipart uploads to the backend API with proper TLS handling.
 * Next.js 16 rewrites don't honor NODE_TLS_REJECT_UNAUTHORIZED for large
 * multipart bodies, causing EPIPE/ECONNRESET errors with self-signed certs.
 * This route bypasses the rewrite proxy by using Node.js https agent directly.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-15
 */

import { NextRequest, NextResponse } from 'next/server';
import https from 'https';
import http from 'http';

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

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ spaceId: string }> }
) {
  const { spaceId } = await params;

  // SEC-017: reject a non-UUID spaceId up front — before reading the body or
  // building the upstream URL — so it can never escape to another route.
  if (!SPACE_ID_UUID_RE.test(spaceId)) {
    return NextResponse.json({ detail: 'Invalid space id' }, { status: 400 });
  }

  // Forward the request body as-is (multipart/form-data)
  const body = await request.arrayBuffer();
  const contentType = request.headers.get('content-type') || '';
  const cookie = request.headers.get('cookie') || '';

  // spaceId is a validated UUID; encodeURIComponent is defense in depth so the
  // segment can never widen the path even if the guard above is ever loosened.
  const targetUrl = `${API_URL_SERVER}/api/v1/rag-spaces/${encodeURIComponent(spaceId)}/documents`;
  const isHttps = targetUrl.startsWith('https');

  try {
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'content-type': contentType,
        cookie,
      },
      body: Buffer.from(body),
      // @ts-expect-error -- Node.js fetch supports agent via dispatcher
      dispatcher: isHttps ? httpsAgent : undefined,
    });

    const responseBody = await response.text();

    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        'content-type': response.headers.get('content-type') || 'application/json',
      },
    });
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
  } catch (_error) {
    // Fallback: use Node.js native http/https for environments where fetch doesn't support dispatcher
    return new Promise<NextResponse>(resolve => {
      const url = new URL(targetUrl);
      const mod = isHttps ? https : http;

      const options: https.RequestOptions = {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'POST',
        headers: {
          'content-type': contentType,
          cookie,
          'content-length': body.byteLength.toString(),
        },
        ...(isHttps && isDev ? { rejectUnauthorized: false } : {}),
      };

      const req = mod.request(options, res => {
        const chunks: Buffer[] = [];
        res.on('data', chunk => chunks.push(chunk));
        res.on('end', () => {
          const responseBody = Buffer.concat(chunks).toString('utf-8');
          resolve(
            new NextResponse(responseBody, {
              status: res.statusCode || 500,
              headers: {
                'content-type': res.headers['content-type'] || 'application/json',
              },
            })
          );
        });
      });

      req.on('error', err => {
        resolve(
          NextResponse.json({ detail: `Upload proxy error: ${err.message}` }, { status: 502 })
        );
      });

      req.write(Buffer.from(body));
      req.end();
    });
  }
}
