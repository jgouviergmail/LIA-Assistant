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

import { readFileSync, writeFileSync } from 'node:fs';

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
