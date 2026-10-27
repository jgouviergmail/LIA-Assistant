/**
 * Declare the shell's own Gradle dependencies in the generated Android project.
 *
 * Firebase Cloud Messaging is the only route to an Android device, and it is
 * not something Capacitor generates. Two ways to add it: shadow the whole
 * generated `app/build.gradle` in `native/`, or transform it. Transforming
 * wins for the same reason `xcode-sources.mjs` transforms the pbxproj — a
 * shadowed file freezes whatever Capacitor shipped the day it was copied, and
 * every upgrade then silently reverts its own changes.
 *
 * Note what is deliberately NOT added: the `com.google.gms.google-services`
 * plugin. It exists to bake ONE Firebase project into the binary, and this app
 * is published once for servers that each own a different one. Capacitor's
 * generated build file already applies that plugin only when a
 * `google-services.json` is present, so leaving the file out is the supported
 * path rather than a workaround.
 */

import { lstatSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

/**
 * The Firebase Android BoM, which then versions the individual artifacts.
 *
 * Pinned exactly: an unpinned platform declaration makes the build's output
 * depend on the day it ran, which is the class of thing this repository's
 * release contract forbids outright.
 */
const FIREBASE_BOM = 'com.google.firebase:firebase-bom:34.4.0';

const DEPENDENCIES = [
  `implementation platform('${FIREBASE_BOM}')`,
  "implementation 'com.google.firebase:firebase-messaging'",
];

/** Marks our block so a re-run recognises its own work. */
const MARKER = '// lia-shell: managed dependencies';

/**
 * Add the shell's dependencies to a generated `app/build.gradle`, idempotently.
 *
 * @param {string} gradlePath Absolute path to the generated file.
 * @returns {{added: string[], skipped: string[]}} What the run did.
 */
export function declareGradleDependencies(gradlePath) {
  const original = readFileSync(gradlePath, 'utf8');

  if (original.includes(MARKER)) {
    return { added: [], skipped: DEPENDENCIES };
  }

  // Anchor on the LAST `dependencies {` opening: Capacitor's file has a single
  // one, but anchoring on the last occurrence survives a future template that
  // grows a `buildscript { dependencies { ... } }` above it — where our
  // artifacts would be a build-time classpath entry rather than an app
  // dependency, and would fail in a way that reads like a Firebase problem.
  const opening = original.lastIndexOf('\ndependencies {');
  if (opening === -1) {
    throw new Error(`no dependencies block found in ${gradlePath}`);
  }

  const insertAt = opening + '\ndependencies {'.length;
  const block = [
    '',
    `    ${MARKER}`,
    ...DEPENDENCIES.map((line) => `    ${line}`),
  ].join('\n');

  writeFileSync(gradlePath, original.slice(0, insertAt) + block + original.slice(insertAt), 'utf8');
  return { added: DEPENDENCIES, skipped: [] };
}

const FLAT_DIR_MARKER = '// lia-shell: unused flatDir repositories removed';

/** Reject local inputs whose resolution might need a flat directory repository. */
function assertNoLocalArtifacts(directory) {
  let stat;
  try { stat = lstatSync(directory); } catch (error) {
    if (error && error.code === 'ENOENT') return;
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`unexpected local artifact path at ${directory}`);
  }
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) assertNoLocalArtifacts(path);
    else if (entry.name !== '.gitkeep' || entry.isSymbolicLink()) {
      throw new Error(`local artifact at ${path}; review its repository before preparing`);
    }
  }
}

/** Read an optional native input without masking invalid/unreadable files. */
function readOptionalNativeFile(path) {
  try { return readFileSync(path, 'utf8'); }
  catch (error) {
    if (error && error.code === 'ENOENT') return undefined;
    throw error;
  }
}

/** Capacitor 8 also discovers Cordova via plugin.xml, without JSON metadata. */
function assertNoCordovaPlugins(packageRoot) {
  const manifest = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8'));
  const packages = new Set(Object.keys({ ...manifest.dependencies, ...manifest.devDependencies, ...manifest.optionalDependencies }));
  const rawConfig = readOptionalNativeFile(join(packageRoot, 'capacitor.config.json'));
  const config = rawConfig === undefined ? {} : JSON.parse(rawConfig);
  for (const included of [config.includePlugins, config.android?.includePlugins]) {
    if (included === undefined) continue;
    if (!Array.isArray(included)) throw new Error('unexpected includePlugins configuration');
    for (const name of included) packages.add(name);
  }
  for (const name of packages) {
    if (typeof name !== 'string' || !/^(?:@[a-z0-9._-]+\/)?[a-z0-9._-]+$/.test(name)) {
      throw new Error('unexpected native dependency name');
    }
    const directory = join(packageRoot, 'node_modules', name);
    const descriptor = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'));
    if (Object.hasOwn(descriptor, 'cordova') || readOptionalNativeFile(join(directory, 'plugin.xml')) !== undefined) {
      throw new Error(`Cordova plugin ${name} requires repository review before preparing`);
    }
  }
}

/**
 * Remove only Capacitor's two known, unused flatDir scaffolds.
 * Validate all files and local inputs first; cap sync recreates the Cordova one.
 * Maven, direct fileTree dependencies and the Cordova module stay intact.
 *
 * @param {string} androidRoot Generated Android directory.
 * @returns {{removed: string[]}} Files changed by this run.
 */
export function removeUnusedFlatDirRepositories(androidRoot) {
  assertNoCordovaPlugins(dirname(androidRoot));
  const specs = [
    { file: join(androidRoot, 'app', 'build.gradle'), dirs: ["../capacitor-cordova-android-plugins/src/main/libs", 'libs'] },
    { file: join(androidRoot, 'capacitor-cordova-android-plugins', 'build.gradle'), dirs: ['src/main/libs', 'libs'] },
  ];
  for (const directory of [join(androidRoot, 'app', 'libs'), join(androidRoot, 'capacitor-cordova-android-plugins', 'src', 'main', 'libs'), join(androidRoot, 'capacitor-cordova-android-plugins', 'libs')]) {
    assertNoLocalArtifacts(directory);
  }
  const changes = specs.map(({ file, dirs }) => {
    const original = readFileSync(file, 'utf8');
    const text = original.replaceAll('\r\n', '\n');
    const blocks = [...text.matchAll(/^[ \t]*flatDir\s*\{([\s\S]*?)^[ \t]*\}/gm)];
    const declarations = [...text.matchAll(/\bflatDir\s*\{/g)];
    if (text.includes(FLAT_DIR_MARKER) && declarations.length === 0) return { file, original, content: original };
    const expected = `dirs '${dirs[0]}', '${dirs[1]}'`;
    if (text.includes(FLAT_DIR_MARKER) || blocks.length !== 1 || declarations.length !== 1 || blocks[0][1].trim().replace(/\s+/g, ' ') !== expected) {
      throw new Error(`unexpected flatDir structure at ${file}; review the generated template`);
    }
    return { file, original, content: text.replace(blocks[0][0], `    ${FLAT_DIR_MARKER}`) };
  });
  const removed = [];
  for (const { file, original, content } of changes) {
    if (content === original) continue;
    writeFileSync(file, content, 'utf8');
    removed.push(file);
  }
  return { removed };
}
