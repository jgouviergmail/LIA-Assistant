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

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ spaceId: string }> }
) {
  const { spaceId } = await params;

  // Forward the request body as-is (multipart/form-data)
  const body = await request.arrayBuffer();
  const contentType = request.headers.get('content-type') || '';
  const cookie = request.headers.get('cookie') || '';

  const targetUrl = `${API_URL_SERVER}/api/v1/rag-spaces/${spaceId}/documents`;
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
