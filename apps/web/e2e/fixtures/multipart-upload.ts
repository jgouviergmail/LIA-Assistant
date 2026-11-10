/** Receive browser-generated multipart bytes without Playwright's body projection. */
import type { IncomingMessage, ServerResponse } from 'node:http';

// Fixture payloads are small; a broken sender must not allocate an unbounded body.
const MAX_CAPTURE_BYTES = 1024 * 1024;

export type MultipartPart =
  | { kind: 'field'; name: string; value: string }
  | { kind: 'file'; name: string; filename: string; contentType: string; bytes: Buffer };

export interface MultipartUpload {
  byteLength: number;
  parts: MultipartPart[];
}

export interface MultipartCapture {
  origin: string;
  uploads: MultipartUpload[];
  errors: string[];
}

export interface MultipartCaptureOptions {
  upstream: string;
  pathname: string;
  response: unknown;
}

export interface OwnedMultipartCapture {
  upstream: URL;
  pathname: string;
  capture: MultipartCapture;
  receive: (request: IncomingMessage, response: ServerResponse) => Promise<void>;
}

/** Parse only bytes that arrived on the owned HTTP socket, preserving duplicate fields. */
async function readMultipart(request: IncomingMessage): Promise<MultipartUpload> {
  const contentType = request.headers['content-type'];
  if (!contentType?.startsWith('multipart/form-data;')) {
    throw new Error('Expected a native multipart/form-data upload');
  }
  const chunks: Buffer[] = [];
  let byteLength = 0;
  for await (const chunk of request) {
    if (!Buffer.isBuffer(chunk)) throw new Error('Expected binary upload chunks');
    byteLength += chunk.length;
    if (byteLength > MAX_CAPTURE_BYTES) throw new Error('Upload fixture exceeds 1 MiB');
    chunks.push(chunk);
  }
  const bytes = new Uint8Array(Buffer.concat(chunks));
  const form = await new Response(bytes, { headers: { 'Content-Type': contentType } }).formData();
  const parts: MultipartPart[] = [];
  for (const [name, value] of form) {
    parts.push(
      typeof value === 'string'
        ? { kind: 'field', name, value }
        : {
            kind: 'file',
            name,
            filename: value.name,
            contentType: value.type,
            bytes: Buffer.from(await value.arrayBuffer()),
          }
    );
  }
  return { byteLength, parts };
}

/** One exact route on the guard's own origin; never a real backend destination. */
export function createMultipartCapture(
  origin: string,
  options: MultipartCaptureOptions
): OwnedMultipartCapture {
  const upstream = new URL(options.upstream);
  if (
    upstream.protocol !== 'http:' ||
    upstream.hostname !== '127.0.0.1' ||
    upstream.username ||
    upstream.password ||
    upstream.pathname !== '/' ||
    upstream.search ||
    upstream.hash ||
    upstream.origin === origin
  ) {
    throw new Error('Multipart capture requires a separate literal HTTP loopback app origin');
  }
  if (!/^\/api\/v1\/[a-z0-9/-]+$/.test(options.pathname)) {
    throw new Error('Multipart capture requires an exact API pathname without a query');
  }
  const payload = JSON.stringify(options.response);
  if (payload === undefined) throw new Error('Multipart capture requires a JSON response');
  const capture: MultipartCapture = { origin, uploads: [], errors: [] };
  return {
    upstream,
    pathname: options.pathname,
    capture,
    receive: async (request, response) => {
      try {
        capture.uploads.push(await readMultipart(request));
        response.writeHead(201, { 'Content-Type': 'application/json' }).end(payload);
      } catch (error) {
        capture.errors.push(error instanceof Error ? error.message : String(error));
        if (!response.headersSent) response.writeHead(400);
        response.end();
      }
    },
  };
}
