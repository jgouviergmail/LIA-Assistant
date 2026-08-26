/**
 * Build the native shell for one platform.
 *
 * This exists because invoking the toolchains from the Taskfile needs a
 * different incantation per platform AND per shell: Task resolves executables
 * itself, so `gradlew.bat` is not found on PATH and `./gradlew.bat` is not a
 * cmd.exe idiom either. One script with absolute paths ends the guessing, the
 * way `prepare.mjs` already owns `local.properties`.
 *
 * Usage: node scripts/build.mjs --platform android|ios
 */

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const WIN = process.platform === 'win32';

/**
 * Build the Android shell.
 *
 * @returns {string} Path of the debug APK.
 */
function buildAndroid() {
  const androidDir = join(ROOT, 'android');
  if (!existsSync(androidDir)) {
    throw new Error('run `task mobile:prepare:android` first');
  }

  const wrapper = join(androidDir, WIN ? 'gradlew.bat' : 'gradlew');
  // Node refuses to spawn a `.bat` without a shell (CVE-2024-27980); quoting
  // the absolute path is what keeps a space in it from splitting the command.
  execFileSync(WIN ? `"${wrapper}"` : wrapper, ['assembleDebug', '--no-daemon'], {
    cwd: androidDir,
    stdio: 'inherit',
    shell: WIN,
  });

  return join(androidDir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk');
}

/**
 * Build the iOS shell for the simulator.
 *
 * Compilation IS the verification here: this repository has no Swift test
 * harness, so a green build on a macOS runner is what proves the shell's own
 * sources are sound.
 *
 * @returns {string} The scheme that was built.
 */
function buildIos() {
  const project = join(ROOT, 'ios', 'App', 'App.xcodeproj');
  if (!existsSync(project)) {
    throw new Error('run `task mobile:prepare:ios` first (macOS)');
  }

  // No .xcworkspace — Capacitor 8 uses Swift Package Manager. No shared scheme
  // either: schemes appear under xcuserdata the first time Xcode opens the
  // project, which never happens on a runner. Hence -project and -target.
  execFileSync(
    'xcodebuild',
    [
      '-project', project,
      '-target', 'App',
      '-sdk', 'iphonesimulator',
      '-configuration', 'Debug',
      'CODE_SIGNING_ALLOWED=NO',
      'CODE_SIGNING_REQUIRED=NO',
      'build',
    ],
    { cwd: ROOT, stdio: 'inherit' }
  );

  return 'App';
}

const platform = process.argv.includes('--platform')
  ? process.argv[process.argv.indexOf('--platform') + 1]
  : null;

if (platform === 'android') {
  console.log(`built: ${buildAndroid()}`);
} else if (platform === 'ios') {
  console.log(`built: ${buildIos()}`);
} else {
  throw new Error('--platform must be "android" or "ios"');
}
