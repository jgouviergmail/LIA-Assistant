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
import { existsSync, readFileSync, readdirSync } from 'node:fs';
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
  execFileSync(WIN ? `"${wrapper}"` : wrapper, ['testDebugUnitTest', 'assembleDebug', '--no-daemon'], {
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

  // prepare creates a shared App scheme, including the package dependencies.
  execFileSync('xcodebuild', iosSimulatorBuildArguments(project), { cwd: ROOT, stdio: 'inherit' });

  return 'App';
}

/**
 * Arguments for the unsigned generic simulator check, never a store archive.
 *
 * LM_SKIP_METADATA_EXTRACTION is an internal Swift Build 6.3 opt-out, not a
 * publicly stable Xcode setting. The shell has no AppIntents feature; requalify
 * the absence of that metadata phase when the SDK changes. Source:
 * https://github.com/swiftlang/swift-build/blob/fc3609a1658bc5e119dc38906eb8049a9e8b24a1/Sources/SWBApplePlatform/AppIntentsMetadataTaskProducer.swift
 *
 * @param {string} project Generated App.xcodeproj directory.
 * @returns {string[]} xcodebuild arguments.
 */
export function iosSimulatorBuildArguments(project) {
  const inspect = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) inspect(path);
      else if (entry.name.endsWith('.swift') && /\b(?:AppIntents|AppIntent|AppShortcutsProvider)\b/.test(readFileSync(path, 'utf8'))) {
        throw new Error('AppIntents source requires reviewing the simulator metadata opt-out');
      }
    }
  };
  inspect(join(dirname(project), 'App'));
  return [
    '-project', project,
    '-scheme', 'App',
    '-sdk', 'iphonesimulator',
    '-destination', 'generic/platform=iOS Simulator',
    '-configuration', 'Debug',
    'ONLY_ACTIVE_ARCH=NO',
    'CODE_SIGNING_ALLOWED=NO',
    'CODE_SIGNING_REQUIRED=NO',
    'LM_SKIP_METADATA_EXTRACTION=YES',
    'build',
  ];
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const platform = process.argv.includes('--platform')
    ? process.argv[process.argv.indexOf('--platform') + 1]
    : null;
  if (platform === 'android') console.log(`built: ${buildAndroid()}`);
  else if (platform === 'ios') console.log(`built: ${buildIos()}`);
  else throw new Error('--platform must be "android" or "ios"');
}
