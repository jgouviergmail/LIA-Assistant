/** Native HTTP tests of the actual TypeScript fixtures; no browser or backend. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer, request as httpRequest } from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));

// Compile the two owning modules, without changing their code or dependencies.
// The ordinary E2E typecheck separately checks their TypeScript contracts.
const compiled = fs.mkdtempSync(path.join(os.tmpdir(), 'lia-multipart-fixtures-'));
after(() => fs.rmSync(compiled, { recursive: true, force: true }));
fs.writeFileSync(path.join(compiled, 'package.json'), '{"type":"commonjs"}');
for (const name of ['api-network-guard', 'multipart-upload']) {
  const source = fs.readFileSync(path.join(scriptDirectory, '../fixtures', `${name}.ts`), 'utf8');
  const result = ts.transpileModule(source, {
    fileName: `${name}.ts`,
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  assert.deepEqual(result.diagnostics, []);
  fs.writeFileSync(path.join(compiled, `${name}.js`), result.outputText);
}
const { createApiNetworkGuard } = await import(
  pathToFileURL(path.join(compiled, 'api-network-guard.js'))
);
const UPLOAD = '/api/v1/workbench/files/upload';

async function fixture(t) {
  const requests = [];
  const upstream = createServer((request, response) => {
    requests.push({ method: request.method, url: request.url });
    response.writeHead(200, {
      'Content-Type': 'text/html',
      'Content-Security-Policy': "default-src 'self'; connect-src 'self'",
    });
    response.end('<p>Real upstream bytes</p>');
  });
  await new Promise((resolve, reject) => {
    upstream.once('error', reject);
    upstream.listen(0, '127.0.0.1', resolve);
  });
  const guard = await createApiNetworkGuard();
  t.after(async () => {
    await guard.close();
    upstream.closeAllConnections();
    await new Promise((resolve, reject) =>
      upstream.close(error => (error ? reject(error) : resolve()))
    );
  });
  const appOrigin = `http://127.0.0.1:${upstream.address().port}`;
  return { guard, appOrigin, requests };
}

function register(guard, appOrigin) {
  return guard.captureMultipartUpload({
    upstream: appOrigin,
    pathname: UPLOAD,
    response: { id: 'u1' },
  });
}

async function multipart(fileBytes) {
  const form = new FormData();
  form.append('name', 'Notes.txt');
  form.append('folder_id', 'd1');
  form.append('file', new Blob([fileBytes], { type: 'application/octet-stream' }), 'Notes.txt');
  const request = new Request('http://127.0.0.1/', { method: 'POST', body: form });
  return {
    body: Buffer.from(await request.arrayBuffer()),
    headers: { 'Content-Type': request.headers.get('content-type') },
  };
}

/** Real proxy transport, including opaque methods, without external sockets. */
function throughProxy(guard, method, url, body = Buffer.alloc(0), headers = {}) {
  const target = new URL(guard.proxy.server);
  return new Promise((resolve, reject) => {
    const request = httpRequest(
      { hostname: target.hostname, port: target.port, method, path: url, headers },
      response => {
        const chunks = [];
        response.on('data', chunk => chunks.push(chunk));
        response.on('error', reject);
        response.on('end', () =>
          resolve({
            status: response.statusCode,
            body: Buffer.concat(chunks),
            headers: response.headers,
          })
        );
      }
    );
    request.on('connect', (response, socket) => {
      socket.destroy();
      resolve({ status: response.statusCode });
    });
    request.on('upgrade', (response, socket) => {
      socket.destroy();
      resolve({ status: response.statusCode });
    });
    request.on('error', reject);
    // Multiple native writes also exercise chunked transfer without a Content-Length.
    const split = Math.floor(body.length / 2);
    if (split) request.write(body.subarray(0, split));
    request.end(body.subarray(split));
  });
}

test('receives exact binary multipart bytes and fields on the owned origin only', async t => {
  const { guard, appOrigin, requests } = await fixture(t);
  const capture = register(guard, appOrigin);
  const bytes = Buffer.from([0, 255, 13, 10, 104, 101, 108, 108, 111]);
  const payload = await multipart(bytes);
  const response = await throughProxy(
    guard,
    'POST',
    capture.origin + UPLOAD,
    payload.body,
    payload.headers
  );
  assert.equal(response.status, 201);
  assert.deepEqual(JSON.parse(response.body), { id: 'u1' });
  assert.equal(capture.uploads.length, 1);
  assert.equal(capture.uploads[0].byteLength, payload.body.length);
  assert.deepEqual(capture.uploads[0].parts, [
    { kind: 'field', name: 'name', value: 'Notes.txt' },
    { kind: 'field', name: 'folder_id', value: 'd1' },
    {
      kind: 'file',
      name: 'file',
      filename: 'Notes.txt',
      contentType: 'application/octet-stream',
      bytes,
    },
  ]);
  assert.deepEqual(capture.errors, []);
  assert.deepEqual(guard.blockedRequests, []);
  assert.deepEqual(requests, []);
});

test('serves actual app bytes and unchanged CSP for same-origin SSR and assets', async t => {
  const { guard, appOrigin, requests } = await fixture(t);
  const capture = register(guard, appOrigin);
  const page = await throughProxy(
    guard,
    'GET',
    capture.origin + '/en/dashboard/tools/files?folder=d1'
  );
  assert.equal(page.status, 200);
  assert.equal(page.body.toString(), '<p>Real upstream bytes</p>');
  assert.equal(page.headers['content-security-policy'], "default-src 'self'; connect-src 'self'");
  // A direct origin-form request must work too: browsers differ on local proxy routing.
  const asset = await fetch(capture.origin + '/_next/static/app.js');
  assert.equal(await asset.text(), '<p>Real upstream bytes</p>');
  assert.deepEqual(requests, [
    { method: 'GET', url: '/en/dashboard/tools/files?folder=d1' },
    { method: 'GET', url: '/_next/static/app.js' },
  ]);
});

test('keeps other origins, methods, queries, API paths and opaque transports refused', async t => {
  const { guard, appOrigin, requests } = await fixture(t);
  const capture = register(guard, appOrigin);
  for (const [method, url] of [
    ['POST', appOrigin + UPLOAD],
    ['GET', capture.origin + UPLOAD],
    ['OPTIONS', capture.origin + UPLOAD],
    ['POST', capture.origin + UPLOAD + '?query=1'],
    ['POST', capture.origin + '/api/v1/other'],
    ['GET', capture.origin + '/%61pi/v1/other'],
    ['GET', capture.origin + '/api'],
    ['POST', capture.origin + '/not-api'],
  ])
    assert.equal((await throughProxy(guard, method, url)).status, 501);
  assert.equal((await throughProxy(guard, 'CONNECT', 'www.google.com:443')).status, 501);
  assert.equal(
    (
      await throughProxy(guard, 'GET', capture.origin + '/socket', Buffer.alloc(0), {
        Connection: 'Upgrade',
        Upgrade: 'websocket',
      })
    ).status,
    501
  );
  assert.equal(guard.blockedRequests.length, 10);
  assert.deepEqual(capture.uploads, []);
  assert.deepEqual(requests, []);
});

test('records empty or missing files as received, never fabricates the expected payload', async t => {
  const { guard, appOrigin } = await fixture(t);
  const capture = register(guard, appOrigin);
  const empty = await multipart(Buffer.alloc(0));
  assert.equal(
    (await throughProxy(guard, 'POST', capture.origin + UPLOAD, empty.body, empty.headers)).status,
    201
  );
  const file = capture.uploads[0].parts.find(part => part.kind === 'file');
  assert.equal(file.bytes.length, 0);
  assert.notDeepEqual(file.bytes, Buffer.from('hello'));
  const form = new FormData();
  form.append('name', 'Notes.txt');
  const request = new Request(capture.origin + UPLOAD, { method: 'POST', body: form });
  assert.equal((await fetch(request)).status, 201);
  assert.equal(
    capture.uploads[1].parts.some(part => part.kind === 'file'),
    false
  );
});

test('refuses malformed and oversized bodies without reporting a received upload', async t => {
  const { guard, appOrigin } = await fixture(t);
  const capture = register(guard, appOrigin);
  for (const [body, contentType] of [
    [Buffer.from('hello'), 'text/plain'],
    [Buffer.from('broken'), 'multipart/form-data; boundary=absent'],
    [Buffer.alloc(1024 * 1024 + 1), 'multipart/form-data; boundary=large'],
  ]) {
    const response = await throughProxy(guard, 'POST', capture.origin + UPLOAD, body, {
      'Content-Type': contentType,
    });
    assert.equal(response.status, 400);
  }
  assert.equal(capture.errors.length, 3);
  assert.deepEqual(capture.uploads, []);
});

test('quarantine closes the upload exception as well as ordinary forwarding', async t => {
  const { guard, appOrigin, requests } = await fixture(t);
  const capture = register(guard, appOrigin);
  guard.quarantine();
  const payload = await multipart(Buffer.from('hello'));
  assert.equal(
    (await throughProxy(guard, 'POST', capture.origin + UPLOAD, payload.body, payload.headers))
      .status,
    501
  );
  assert.equal((await throughProxy(guard, 'GET', appOrigin + '/public')).status, 501);
  assert.throws(() => register(guard, appOrigin), /closed or already registered/);
  assert.deepEqual(capture.uploads, []);
  assert.deepEqual(requests, []);
});

test('closing the owner terminates an unfinished native upload and awaits its reader', async () => {
  const guard = await createApiNetworkGuard();
  const capture = register(guard, 'http://127.0.0.1:9');
  const target = new URL(capture.origin);
  const errors = [];
  const request = httpRequest({
    hostname: target.hostname,
    port: target.port,
    method: 'POST',
    path: UPLOAD,
    headers: { 'Content-Type': 'multipart/form-data; boundary=incomplete', 'Content-Length': 1000 },
  });
  request.on('error', error => errors.push(error.code));
  const closed = new Promise(resolve => request.once('close', resolve));
  try {
    await new Promise(resolve => request.once('socket', socket => socket.once('connect', resolve)));
    request.write('--incomplete\r\nContent-Disposition: form-data; name="file"\r\n');
    await guard.close();
    await closed;
    assert.deepEqual(capture.uploads, []);
    assert.ok(errors.every(code => code === 'ECONNRESET'));
  } finally {
    request.destroy();
  }
});

test('accepts only a fixed loopback app and exact API pathname with one owner', async t => {
  const { guard, appOrigin } = await fixture(t);
  for (const upstream of [
    'http://example.com',
    'http://localhost:3000',
    'https://127.0.0.1',
    'http://127.0.0.1:3000/path',
    guard.proxy.server,
  ]) {
    assert.throws(() => register(guard, upstream), /literal HTTP loopback/);
  }
  assert.throws(
    () =>
      guard.captureMultipartUpload({
        upstream: appOrigin,
        pathname: UPLOAD + '?x=1',
        response: {},
      }),
    /exact API pathname/
  );
  register(guard, appOrigin);
  assert.throws(() => register(guard, appOrigin), /closed or already registered/);
});
