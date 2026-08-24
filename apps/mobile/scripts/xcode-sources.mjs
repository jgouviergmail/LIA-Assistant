/**
 * Declare the shell's own Swift files in the generated Xcode project.
 *
 * Xcode compiles what `project.pbxproj` lists, not what sits in the folder —
 * `objectVersion = 60`, so no synchronized file groups to inherit from. Copying
 * a `.swift` file into `ios/App/App/` therefore does nothing at all, silently:
 * the build succeeds and the class is simply absent at runtime.
 *
 * This inserts the four entries Xcode needs per file, mirroring exactly what the
 * template already does for `AppDelegate.swift`. It is a targeted transform
 * rather than an overlay of the whole pbxproj, because that file carries
 * generated identifiers: overlaying it would freeze one Capacitor version's
 * project and fight every upgrade.
 *
 * Idempotent: a file already declared is left alone.
 */

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

/**
 * A pbxproj identifier: 24 uppercase hex characters, stable for a given name.
 *
 * Derived from the file name so re-running produces the same project rather
 * than a diff, and so two files can never collide by accident.
 *
 * @param {string} seed - Anything unique to the entry.
 * @returns {string} A 24-character hexadecimal identifier.
 */
function identifierFor(seed) {
  return createHash('sha256').update(seed).digest('hex').slice(0, 24).toUpperCase();
}

/**
 * Ensure every named Swift file is compiled by the App target.
 *
 * @param {string} pbxprojPath - Path of the generated project file.
 * @param {string[]} fileNames - File names, relative to `ios/App/App/`.
 * @returns {{added: string[], skipped: string[]}} What changed.
 */
export function declareSwiftSources(pbxprojPath, fileNames) {
  if (!existsSync(pbxprojPath)) {
    throw new Error(`no Xcode project at ${pbxprojPath}`);
  }
  let content = readFileSync(pbxprojPath, 'utf8');
  const added = [];
  const skipped = [];

  for (const name of fileNames) {
    if (content.includes(`/* ${name} */`)) {
      skipped.push(name);
      continue;
    }

    const fileRef = identifierFor(`ref:${name}`);
    const buildFile = identifierFor(`build:${name}`);

    // 1. The build file, next to AppDelegate's.
    content = content.replace(
      /(\t\t\S+ \/\* AppDelegate\.swift in Sources \*\/ = \{isa = PBXBuildFile;[^\n]*\n)/,
      `$1\t\t${buildFile} /* ${name} in Sources */ = {isa = PBXBuildFile; fileRef = ${fileRef} /* ${name} */; };\n`
    );

    // 2. The file reference.
    content = content.replace(
      /(\t\t\S+ \/\* AppDelegate\.swift \*\/ = \{isa = PBXFileReference;[^\n]*\n)/,
      `$1\t\t${fileRef} /* ${name} */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ${name}; sourceTree = "<group>"; };\n`
    );

    // 3. Membership of the App group, so it is visible in the navigator.
    content = content.replace(
      /(\t{4}\S+ \/\* AppDelegate\.swift \*\/,\n)/,
      `$1\t\t\t\t${fileRef} /* ${name} */,\n`
    );

    // 4. The sources build phase — the one that actually compiles it.
    content = content.replace(
      /(\t{4}\S+ \/\* AppDelegate\.swift in Sources \*\/,\n)/,
      `$1\t\t\t\t${buildFile} /* ${name} in Sources */,\n`
    );

    added.push(name);
  }

  if (added.length > 0) {
    writeFileSync(pbxprojPath, content, 'utf8');
  }
  return { added, skipped };
}
