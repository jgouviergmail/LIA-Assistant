/**
 * Scaffold the throwaway Capacitor shell the probe runs inside.
 *
 * The native project is GENERATED, never vendored: committing an Android or
 * Xcode project would add thousands of files the repo cannot review, and would
 * freeze the very thing the probe exists to re-measure. It is built into the
 * OS temp directory so `task deploy:prod` — which rsyncs the WORKING TREE,
 * untracked files included — can never ship it.
 */

import { mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/**
 * Capacitor version the measurements were taken against.
 *
 * Pinned exactly: this harness is a non-regression guard, and a floating range
 * would let a silent upgrade change the answer without changing the evidence.
 * Bumping it is a deliberate act that must be followed by a fresh run.
 */
export const CAPACITOR_VERSION = '8.5.0';

/** Application id of the throwaway shell. */
export const APP_ID = 'com.lia.webviewprobe';

/**
 * Create (or reuse) the Capacitor project for one platform.
 *
 * @param {'android'|'ios'} platform - Native platform to add.
 * @param {string} serverUrl - URL the WebView loads (the probe server).
 * @param {boolean} fresh - Delete any existing project first.
 * @returns {Promise<string>} Absolute path of the generated project.
 */
export async function scaffold(platform, serverUrl, fresh = false) {
  const root = join(tmpdir(), `lia-webview-probe-${platform}`);

  if (fresh && existsSync(root)) {
    await rm(root, { recursive: true, force: true });
  }

  // Node refuses to spawn `.cmd` without a shell (CVE-2024-27980); npm and npx
  // ship as `.cmd` shims on Windows, so name them explicitly there.
  const win = process.platform === 'win32';
  const run = (cmd, args) =>
    execFileSync(win ? `${cmd}.cmd` : cmd, args, { cwd: root, stdio: 'inherit', shell: win });

  const isNew = !existsSync(join(root, 'node_modules'));
  await mkdir(join(root, 'www'), { recursive: true });

  await writeFile(
    join(root, 'package.json'),
    `${JSON.stringify({ name: 'lia-webview-probe', version: '0.0.0', private: true }, null, 2)}\n`
  );

  // Capacitor requires a webDir even when it loads a remote URL; this file is
  // never displayed, because `server.url` wins.
  await writeFile(
    join(root, 'www', 'index.html'),
    '<!doctype html><meta charset="utf-8"><title>unused</title>\n'
  );

  await writeFile(
    join(root, 'capacitor.config.json'),
    `${JSON.stringify(
      {
        appId: APP_ID,
        appName: 'LIAWebViewProbe',
        webDir: 'www',
        // cleartext: the probe server is plain HTTP on `localhost`, which is a
        // secure context in both engines — the only way to exercise Service
        // Workers and cross-origin isolation without provisioning a certificate.
        server: { url: serverUrl, cleartext: true },
        // Left at their defaults (false) ON PURPOSE, and asserted by run.mjs:
        // enabling either replaces window.fetch / document.cookie for the whole
        // application, which would silently break LIA's BFF cookie contract.
        plugins: { CapacitorHttp: { enabled: false }, CapacitorCookies: { enabled: false } },
      },
      null,
      2
    )}\n`
  );

  if (isNew) {
    run('npm', [
      'install',
      '--silent',
      '--no-audit',
      '--no-fund',
      `@capacitor/core@${CAPACITOR_VERSION}`,
      `@capacitor/cli@${CAPACITOR_VERSION}`,
      `@capacitor/${platform}@${CAPACITOR_VERSION}`,
    ]);
  }

  if (!existsSync(join(root, platform))) {
    run('npx', ['cap', 'add', platform]);
  } else {
    run('npx', ['cap', 'sync', platform]);
  }

  if (platform === 'ios') {
    await allowLocalhostOverHttp(join(root, 'ios', 'App', 'App', 'Info.plist'));
  }

  return root;
}

/**
 * Let the iOS shell load the probe server over plain HTTP on `localhost`.
 *
 * `server.cleartext` is an ANDROID-only option (it maps to
 * `usesCleartextTraffic`); Capacitor's iOS platform ignores it, and the
 * generated Info.plist carries no `NSAppTransportSecurity` key at all. Whether
 * App Transport Security tolerates loopback HTTP has varied across iOS
 * releases, so the exception is declared rather than relied upon — a probe must
 * not fail for a reason unrelated to what it measures.
 *
 * Scoped to `localhost`. `NSAllowsArbitraryLoads` would disable ATS for the
 * whole app, which is never an acceptable shape to copy into a shipping shell.
 *
 * @param {string} plistPath - Path of the generated Info.plist.
 */
export async function allowLocalhostOverHttp(plistPath) {
  const plist = await readFile(plistPath, 'utf8');
  if (plist.includes('NSAppTransportSecurity')) return;

  const exception = [
    '\t<key>NSAppTransportSecurity</key>',
    '\t<dict>',
    '\t\t<key>NSAllowsLocalNetworking</key>',
    '\t\t<true/>',
    '\t\t<key>NSExceptionDomains</key>',
    '\t\t<dict>',
    '\t\t\t<key>localhost</key>',
    '\t\t\t<dict>',
    '\t\t\t\t<key>NSExceptionAllowsInsecureHTTPLoads</key>',
    '\t\t\t\t<true/>',
    '\t\t\t</dict>',
    '\t\t</dict>',
    '\t</dict>',
    '</dict>',
  ].join('\n');

  // Tolerate CRLF and trailing whitespace: the file is generated by the
  // Capacitor CLI, which may run on either host.
  const closing = /<\/dict>\s*<\/plist>\s*$/;
  if (!closing.test(plist)) {
    throw new Error(`unexpected Info.plist shape: ${plistPath}`);
  }
  await writeFile(plistPath, plist.replace(closing, `${exception}\n</plist>\n`), 'utf8');
}
