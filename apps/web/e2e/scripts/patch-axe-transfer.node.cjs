const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const { patchAxeTransfer } = require('./patch-axe-transfer.cjs');

const entry = require.resolve('@axe-core/playwright', { paths: [process.cwd()] });
const installedDirectory = path.dirname(path.dirname(entry));
// These two upstream 4.10.2 function fragments reconstruct pristine TEMPORARY
// copies after npm ci has patched the installed package. The patch's original
// SHA-256 checks also verify that reconstruction before it can be used.
const upstreamReceiver = `function chunkResultString(chunk) {
  if (!window.partialResults) {
    window.partialResults = "";
  }
  window.partialResults += chunk;
}`;
const upstreamTransfer = `    const sizeLimit = 6e7;
    const partialString = JSON.stringify(partialResults);
    async function chunkResults(result) {
      const chunk = result.substring(0, sizeLimit);
      await blankPage.evaluate(chunkResultString, chunk);
      if (result.length > sizeLimit) {
        return await chunkResults(result.substr(sizeLimit));
      }
    }
    await chunkResults(partialString);
    return await blankPage.evaluate(axeFinishRun, {
      options
    }).finally(async () => {
      await blankPage.close();
    });
  }
  async axeConfigure`;

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'lia-axe-transfer-'));
  fs.mkdirSync(path.join(root, 'dist'));
  fs.copyFileSync(path.join(installedDirectory, 'package.json'), path.join(root, 'package.json'));
  for (const name of ['index.js', 'index.mjs']) {
    const installed = fs.readFileSync(path.join(installedDirectory, 'dist', name), 'utf8');
    const pristine = installed
      .replace(/function chunkResultString[^]*?\n}/, upstreamReceiver)
      .replace(/    const sizeLimit = [^]*?\n  }\n  async axeConfigure/, upstreamTransfer);
    fs.writeFileSync(path.join(root, 'dist', name), pristine);
  }
  t.after(() => {
    for (const name of ['index.js', 'index.mjs']) fs.unlinkSync(path.join(root, 'dist', name));
    fs.unlinkSync(path.join(root, 'package.json'));
    fs.rmdirSync(path.join(root, 'dist'));
    fs.rmdirSync(root);
  });
  return root;
}
function texts(root) {
  return ['index.js', 'index.mjs'].map(name =>
    fs.readFileSync(path.join(root, 'dist', name), 'utf8')
  );
}
function transport(t, alter = arg => arg) {
  const root = fixture(t);
  patchAxeTransfer(root);
  const loaded = { exports: {} };
  vm.runInNewContext(texts(root)[0], {
    module: loaded,
    exports: loaded.exports,
    require: createRequire(entry),
  });
  const window = { axe: { finishRun: partials => JSON.parse(JSON.stringify(partials)) } };
  const realm = vm.createContext({ window });
  const receivedChunks = [];
  let closed = false;
  const blankPage = {
    async evaluate(fn, arg) {
      if (typeof fn === 'string') return;
      let delivered = structuredClone(arg);
      if (fn.name === 'chunkResultString') {
        receivedChunks.push(typeof delivered === 'string' ? delivered : delivered.chunk);
        delivered = alter(delivered, receivedChunks.length - 1);
      }
      return vm.runInContext(`(${fn.toString()})`, realm)(delivered);
    },
    async close() {
      closed = true;
    },
  };
  const page = { context: () => ({ newPage: async () => blankPage }), evaluate: async () => true };
  return {
    builder: new loaded.exports.default({ page }),
    window,
    receivedChunks,
    isClosed: () => closed,
  };
}

test('complete results survive multiple bounded chunks, Unicode and a split surrogate pair', async t => {
  const wire = transport(t);
  const partials = [
    { data: 'x'.repeat(1048565) + '😀é瑴', rules: [{ id: 'color-contrast', nodes: [1, 2, 3] }] },
  ];
  assert.deepEqual(await wire.builder.finishRun(partials), partials);
  assert.ok(wire.receivedChunks.length > 1);
  assert.ok(wire.receivedChunks.every(chunk => chunk.length <= 1048576));
  assert.equal(wire.window.partialResults, JSON.stringify(partials));
  assert.equal(wire.isClosed(), true);
});
test('a same-length ASCII to U+7474 mutation remains valid JSON but fails before append', async t => {
  const wire = transport(t, arg => {
    const chunk = typeof arg === 'string' ? arg : arg.chunk;
    const altered = chunk.replace('data', 'da瑴a');
    assert.equal(altered.length, chunk.length);
    assert.doesNotThrow(() => JSON.parse(altered));
    return typeof arg === 'string' ? altered : { ...arg, chunk: altered };
  });
  await assert.rejects(
    wire.builder.finishRun([{ data: null }]),
    /axe result transfer integrity check failed/
  );
  assert.equal(wire.window.partialResults, undefined);
  assert.equal(wire.isClosed(), true);
});
test('a truncated block fails explicitly before append and closes its page', async t => {
  const wire = transport(t, arg =>
    typeof arg === 'string' ? arg.slice(0, -1) : { ...arg, chunk: arg.chunk.slice(0, -1) }
  );
  await assert.rejects(
    wire.builder.finishRun([{ data: null }]),
    /axe result transfer integrity check failed/
  );
  assert.equal(wire.window.partialResults, undefined);
  assert.equal(wire.isClosed(), true);
});
test('an incorrect checksum is refused even when the block text is intact', async t => {
  const wire = transport(t, arg =>
    typeof arg === 'string' ? arg : { ...arg, hash: arg.hash ^ 1 }
  );
  await assert.rejects(
    wire.builder.finishRun([{ data: null }]),
    /axe result transfer integrity check failed/
  );
  assert.equal(wire.window.partialResults, undefined);
  assert.equal(wire.isClosed(), true);
});
test('an incorrect length is refused even when the text and checksum are intact', async t => {
  const wire = transport(t, arg =>
    typeof arg === 'string' ? arg : { ...arg, length: arg.length + 1 }
  );
  await assert.rejects(
    wire.builder.finishRun([{ data: null }]),
    /axe result transfer integrity check failed/
  );
  assert.equal(wire.window.partialResults, undefined);
  assert.equal(wire.isClosed(), true);
});
test('a corrupt later block cannot overwrite the intact earlier results', async t => {
  const wire = transport(t, (arg, index) => {
    if (index === 0) return arg;
    return typeof arg === 'string'
      ? arg.replace('x', '瑴')
      : { ...arg, chunk: arg.chunk.replace('x', '瑴') };
  });
  await assert.rejects(
    wire.builder.finishRun([{ data: 'x'.repeat(1100000) }]),
    /axe result transfer integrity check failed/
  );
  assert.equal(wire.window.partialResults, wire.receivedChunks[0]);
  assert.equal(wire.isClosed(), true);
});
test('patching is idempotent for both module formats', t => {
  const root = fixture(t);
  assert.equal(patchAxeTransfer(root), 2);
  const before = texts(root);
  assert.equal(patchAxeTransfer(root), 0);
  assert.deepEqual(texts(root), before);
});
test('a new package version is rejected before either source changes', t => {
  const root = fixture(t);
  const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  metadata.version = '4.10.3';
  fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify(metadata));
  const before = texts(root);
  assert.throws(() => patchAxeTransfer(root), /Review the axe transfer patch/);
  assert.deepEqual(texts(root), before);
});
test('an unknown second source is rejected before the first source is patched', t => {
  const root = fixture(t);
  fs.appendFileSync(path.join(root, 'dist/index.mjs'), '\n// source changed\n');
  const before = texts(root);
  assert.throws(() => patchAxeTransfer(root), /Unrecognized upstream axe source: index.mjs/);
  assert.deepEqual(texts(root), before);
});
test('the package identity cannot be substituted', t => {
  const root = fixture(t);
  const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  metadata.name = 'different-package';
  fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify(metadata));
  const before = texts(root);
  assert.throws(() => patchAxeTransfer(root), /Unexpected axe package/);
  assert.deepEqual(texts(root), before);
});
