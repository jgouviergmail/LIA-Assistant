// Lossless transport patch for @axe-core/playwright 4.10.2. npm ci applies
// exactly these changes to both exports, or rejects unfamiliar source first.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const PACKAGE_VERSION = '4.10.2';
const SOURCES = [
  {
    name: 'index.js',
    original: '324cddfa2a4a61d7db0f85c38be009adf53612afb7377e6f262988e0b933a604',
    patched: '253532213de1e2d40093d899d10e7c40b50cc2822e578dc3a812ae741fcc7b9e',
  },
  {
    name: 'index.mjs',
    original: '882da2974fd96503b75a612f14dbe9267c3147294230e2b46da88fc3ac703393',
    patched: '2d20c05c057c2f9131667663fa9b0d0438614d86e77da4d2e4d00ba757a37000',
  },
];
const REPLACEMENTS = [
  ['const sizeLimit = 6e7;', 'const sizeLimit = 1024 * 1024;'],
  [
    `function chunkResultString(chunk) {
  if (!window.partialResults) {
    window.partialResults = "";
  }
  window.partialResults += chunk;
}`,
    `function chunkResultString({ chunk, length, hash }) {
  let actualHash = 2166136261;
  for (let index = 0; index < chunk.length; index++) {
    actualHash = Math.imul(actualHash ^ chunk.charCodeAt(index), 16777619);
  }
  if (chunk.length !== length || (actualHash >>> 0) !== hash) {
    throw new Error("axe result transfer integrity check failed (length/hash mismatch)");
  }
  if (!window.partialResults) {
    window.partialResults = "";
  }
  window.partialResults += chunk;
}`,
  ],
  [
    '      await blankPage.evaluate(chunkResultString, chunk);',
    `      let hash = 2166136261;
      for (let index = 0; index < chunk.length; index++) {
        hash = Math.imul(hash ^ chunk.charCodeAt(index), 16777619);
      }
      await blankPage.evaluate(chunkResultString, {
        chunk, length: chunk.length, hash: hash >>> 0
      });`,
  ],
  [
    `    await chunkResults(partialString);
    return await blankPage.evaluate(axeFinishRun, {
      options
    }).finally(async () => {
      await blankPage.close();
    });`,
    `    try {
      await chunkResults(partialString);
      return await blankPage.evaluate(axeFinishRun, {
        options
      });
    } finally {
      await blankPage.close();
    }`,
  ],
];
const digest = text => crypto.createHash('sha256').update(text).digest('hex');

function patchAxeTransfer(packageDirectory) {
  const metadata = JSON.parse(fs.readFileSync(path.join(packageDirectory, 'package.json'), 'utf8'));
  assert.equal(metadata.name, '@axe-core/playwright', 'Unexpected axe package');
  assert.equal(metadata.version, PACKAGE_VERSION, 'Review the axe transfer patch for this version');
  const updates = SOURCES.map(source => {
    const filename = path.join(packageDirectory, 'dist', source.name);
    let patched = fs.readFileSync(filename, 'utf8');
    const actualDigest = digest(patched);
    if (actualDigest === source.patched) return { filename, patched: null };
    assert.equal(actualDigest, source.original, `Unrecognized upstream axe source: ${source.name}`);
    for (const [original, replacement] of REPLACEMENTS) {
      assert.equal(patched.split(original).length, 2, 'Each axe transfer patch must match once');
      patched = patched.replace(original, replacement);
    }
    assert.equal(digest(patched), source.patched, `Unexpected patched axe source: ${source.name}`);
    return { filename, patched };
  });
  // Prevalidate BOTH modules before writing either of them.
  for (const update of updates) {
    if (update.patched !== null) fs.writeFileSync(update.filename, update.patched);
  }
  return updates.filter(update => update.patched !== null).length;
}

if (require.main === module) {
  const entry = require.resolve('@axe-core/playwright', { paths: [process.cwd()] });
  const patchedCount = patchAxeTransfer(path.dirname(path.dirname(entry)));
  console.log(
    `axe transport: ${patchedCount} modules patched; 1,048,576 UTF-16 code units per chunk with integrity checks`
  );
}

module.exports = { patchAxeTransfer };
