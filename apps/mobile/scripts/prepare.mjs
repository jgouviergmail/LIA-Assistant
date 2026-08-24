/**
 * Regenerate a native project and lay our own sources on top.
 *
 * The generated `android/` and `ios/` trees are NOT versioned (owner
 * arbitration 2026-08-24): `cap add` writes thousands of files nobody can
 * review, they conflict on every Capacitor upgrade, and `task deploy:prod`
 * rsyncs the working tree — a generated Xcode project would ship to the
 * Raspberry Pi. What IS versioned is `native/`: the handful of files that are
 * ours.
 *
 * The cost of that choice is drift: an upgrade can change a template we
 * replace, and our copy would keep overriding it, silently, for years. So every
 * overlay that shadows a generated file carries the hash of the file it
 * shadowed. When upstream moves, this script says so instead of hiding it.
 *
 * Usage: node scripts/prepare.mjs --platform android|ios [--accept-drift]
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { cp, mkdir, readdir, readFile, stat } from 'node:fs/promises';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { declareSwiftSources } from './xcode-sources.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const WIN = process.platform === 'win32';

/** Where the hashes of shadowed upstream files live. */
const DRIFT_BASELINE = join(ROOT, 'native', 'upstream-baseline.json');

/**
 * Parse `--key value` and `--flag` arguments.
 *
 * @param {string[]} argv - Arguments after the script name.
 * @returns {Record<string, string|boolean>} Parsed options.
 */
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    const key = argv[i].slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      out[key] = next;
      i += 1;
    } else {
      out[key] = true;
    }
  }
  return out;
}

/**
 * Run a command in the mobile package, failing the process on a non-zero exit.
 *
 * pnpm, not npm: this package is a member of the repository's pnpm workspace
 * (`packages: ['apps/*']`), and a second lockfile beside `pnpm-lock.yaml` would
 * be a second authority on the same dependencies — the shape this repository
 * refuses everywhere else. It also broke CI outright: `pnpm install
 * --frozen-lockfile` fails the moment a workspace member's manifest is not in
 * the root lockfile.
 */
function run(command, args) {
  // Node refuses to spawn `.cmd` without a shell (CVE-2024-27980); pnpm ships
  // as a `.cmd` shim on Windows.
  const resolved = WIN ? `${command}.cmd` : command;
  execFileSync(resolved, args, { cwd: ROOT, stdio: 'inherit', shell: WIN });
}

/** SHA-256 of a file's bytes, hex. */
function hashOf(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

/**
 * List every file under a directory, as paths relative to it.
 *
 * @param {string} dir - Directory to walk.
 * @param {string} [base] - Root the results are relative to.
 * @returns {Promise<string[]>} Relative file paths.
 */
async function filesUnder(dir, base = dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const found = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await filesUnder(full, base)));
    } else {
      found.push(relative(base, full));
    }
  }
  return found;
}

/**
 * Copy our sources over the generated tree, reporting upstream drift.
 *
 * @param {'android'|'ios'} platform - Platform being prepared.
 * @param {boolean} acceptDrift - Record the new upstream hashes instead of failing.
 * @param {boolean} freshlyGenerated - True when the platform was just added.
 * @returns {Promise<void>}
 */
async function overlay(platform, acceptDrift, freshlyGenerated) {
  const from = join(ROOT, 'native', platform);
  const to = join(ROOT, platform);
  if (!existsSync(from)) {
    console.log(`no overlay for ${platform}`);
    return;
  }

  const baseline = existsSync(DRIFT_BASELINE)
    ? JSON.parse(readFileSync(DRIFT_BASELINE, 'utf8'))
    : {};
  const drifted = [];
  const observed = { ...baseline };

  for (const rel of await filesUnder(from)) {
    const target = join(to, rel);
    const key = `${platform}/${rel.split('\\').join('/')}`;

    // Drift is only observable on a FRESH generation. `cap sync` does not
    // rewrite MainActivity or the storyboard, so on a sync the file sitting
    // there is our own overlay from last time — comparing it to the recorded
    // template says nothing, and reports drift every time we edit our own
    // sources. Measured twice on 2026-08-24 before the reason was clear.
    if (freshlyGenerated && existsSync(target)) {
      const upstream = hashOf(target);
      if (baseline[key] && baseline[key] !== upstream) {
        drifted.push(key);
      }
      observed[key] = upstream;
    }

    await mkdir(dirname(target), { recursive: true });
    await cp(join(from, rel), target, { force: true });
  }

  if (drifted.length > 0 && !acceptDrift) {
    console.error(
      '\nUpstream changed files this overlay replaces:\n' +
        drifted.map(name => `  - ${name}`).join('\n') +
        '\n\nRead the new template, fold what matters into native/, then re-run\n' +
        'with --accept-drift to record the new upstream hashes.\n'
    );
    process.exitCode = 1;
    return;
  }

  writeFileSync(DRIFT_BASELINE, `${JSON.stringify(observed, null, 2)}\n`, 'utf8');
  console.log(`overlay applied: ${platform}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const platform = args.platform;
  if (platform !== 'android' && platform !== 'ios') {
    throw new Error('--platform must be "android" or "ios"');
  }

  if (!existsSync(join(ROOT, 'node_modules'))) {
    run('pnpm', ['install']);
  }

  const freshlyGenerated = !existsSync(join(ROOT, platform));
  if (freshlyGenerated) {
    run('pnpm', ['exec', 'cap', 'add', platform]);
  } else {
    run('pnpm', ['exec', 'cap', 'sync', platform]);
  }

  await overlay(platform, Boolean(args['accept-drift']), freshlyGenerated);

  if (platform === 'android') {
    const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
    if (!sdk) throw new Error('ANDROID_HOME (or ANDROID_SDK_ROOT) must be set');
    // Forward slashes: a backslash-escaped Windows path makes Gradle fail
    // during dependency resolution with an opaque "syntax of the file name,
    // directory or volume is incorrect". Written here rather than in the
    // Taskfile so one place owns it, on every platform.
    writeFileSync(
      join(ROOT, 'android', 'local.properties'),
      `sdk.dir=${sdk.replaceAll('\\', '/')}\n`,
      'utf8'
    );
  }

  if (platform === 'ios') {
    // Copying a .swift file into the folder compiles nothing: Xcode builds what
    // the project lists. Declaring it is the step whose absence fails silently.
    const report = declareSwiftSources(
      join(ROOT, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj'),
      ['ServerUrlStore.swift', 'LiaShellPlugin.swift', 'MainViewController.swift']
    );
    console.log(
      `xcode sources — declared: ${report.added.join(', ') || 'none'}` +
        (report.skipped.length > 0 ? ` | already present: ${report.skipped.join(', ')}` : '')
    );
  }
}

await main();
