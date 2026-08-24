/**
 * Run the native-WebView capability probe on one platform and assert LIA's
 * invariants against the result.
 *
 * This is a GUARD, not a report. Facts that would silently break the product
 * fail the run; facts that are immovable platform limits are recorded as
 * evidence instead. The distinction matters: `PushManager` being absent is a
 * WebView property the design works around, whereas the httpOnly session
 * cookie becoming readable from JavaScript would be a security regression.
 *
 * Usage:
 *   node scripts/mobile-probe/run.mjs --platform android|ios [--coep MODE]
 *                                     [--port N] [--out FILE] [--fresh]
 */

import { execFileSync } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { startProbeServer, startApiOrigin, SESSION_SENTINEL, API_SENTINEL } from './server.mjs';
import { scaffold, APP_ID, CAPACITOR_VERSION } from './scaffold.mjs';

const WIN = process.platform === 'win32';

/**
 * How long the first launch runs before the cold restart.
 *
 * 60 s, and the value is EVIDENCE rather than a guess. Measured on Android 16 /
 * WebView 133: a restart ~28 s after the cookie was set loses it, the same
 * restart at 60 s keeps it. Chromium's WebView writes its cookie store to disk
 * on a ~30 s timer, and Capacitor calls `CookieManager.flush()` nowhere in its
 * lifecycle (the only flush lives inside the disabled CapacitorCookies plugin).
 *
 * The product consequence is real and must be fixed natively, not here: a user
 * who signs in and leaves within that window is signed out — which is exactly
 * when someone is most likely to background the app. The shell therefore owes a
 * `CookieManager.getInstance().flush()` on pause. Lower this value with
 * `--settle` to reproduce the hazard on demand.
 */
const FIRST_RUN_SETTLE_MS = 60_000;

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
 * Node refuses to spawn `.bat`/`.cmd` without a shell (CVE-2024-27980), and a
 * shell resolves the command against PATH rather than `cwd` — which is why a
 * bare `gradlew.bat` is not found. Quote the (absolute) path and use a shell
 * only for those two extensions.
 *
 * @param {string} cmd - Executable path or PATH-resolvable name.
 * @returns {{command: string, shell: boolean}} Spawn arguments.
 */
function spawnable(cmd) {
  const shell = WIN && /\.(cmd|bat)$/i.test(cmd);
  return { command: shell ? `"${cmd}"` : cmd, shell };
}

/** Run a command, inheriting stdio, failing the process on a non-zero exit. */
function sh(cmd, args, cwd) {
  const { command, shell } = spawnable(cmd);
  return execFileSync(command, args, { cwd, stdio: 'inherit', shell });
}

/** Run a command and capture its stdout. */
function shOut(cmd, args) {
  const { command, shell } = spawnable(cmd);
  return execFileSync(command, args, { encoding: 'utf8', shell });
}

/**
 * Build, install and launch the Android shell.
 *
 * @param {string} projectRoot - Generated Capacitor project.
 * @param {number} port - Probe server port to forward into the device.
 * @returns {() => void} Callback that cold-restarts the app.
 */
function driveAndroid(projectRoot, port, apiPort) {
  const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
  if (!sdk) throw new Error('ANDROID_HOME (or ANDROID_SDK_ROOT) must be set');

  const androidDir = join(projectRoot, 'android');

  // Forward slashes on purpose: a backslash-escaped Windows path in
  // local.properties makes Gradle fail during dependency resolution with an
  // opaque "syntax of the file name, directory or volume is incorrect".
  writeFileSync(
    join(androidDir, 'local.properties'),
    `sdk.dir=${sdk.replace(/\\/g, '/')}\n`,
    'utf8'
  );

  sh(
    join(androidDir, WIN ? 'gradlew.bat' : 'gradlew'),
    ['assembleDebug', '--no-daemon', '-q'],
    androidDir
  );

  const apk = join(androidDir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk');

  // The probe server listens on the HOST; `adb reverse` makes the device's own
  // localhost reach it, which keeps the page in a secure context (Service
  // Workers and cross-origin isolation both require one).
  sh('adb', ['reverse', `tcp:${port}`, `tcp:${port}`]);
  // The separate API origin needs its own tunnel, or the cross-site credentialed
  // check would fail for a network reason rather than a cookie-policy one.
  sh('adb', ['reverse', `tcp:${apiPort}`, `tcp:${apiPort}`]);
  sh('adb', ['install', '-r', apk]);

  const launch = () => sh('adb', ['shell', 'am', 'start', '-n', `${APP_ID}/.MainActivity`]);
  launch();

  return restartMode => {
    // Android WebView writes its cookie store to disk lazily, and Capacitor
    // never calls `CookieManager.flush()` in any lifecycle callback (verified
    // in @capacitor/android: the only flush lives inside the disabled
    // CapacitorCookies plugin). So HOW the app dies decides whether a session
    // survives — which is exactly what these two modes separate.
    if (restartMode === 'pause') {
      sh('adb', ['shell', 'input', 'keyevent', 'KEYCODE_HOME']);
      sh('adb', ['shell', 'sleep', '3']);
    }
    sh('adb', ['shell', 'am', 'force-stop', APP_ID]);
    launch();
  };
}

/**
 * Build, install and launch the iOS shell on a booted simulator.
 *
 * @param {string} projectRoot - Generated Capacitor project.
 * @returns {() => void} Callback that cold-restarts the app.
 */
function driveIos(projectRoot) {
  const iosDir = join(projectRoot, 'ios', 'App');
  const derived = join(projectRoot, 'ios-build');

  // Capacitor 8 generates an .xcodeproj with Swift Package Manager
  // (CapApp-SPM/Package.swift) — there is NO .xcworkspace, and CocoaPods is not
  // involved. Verified against a generated project rather than assumed.
  const project = join(iosDir, 'App.xcodeproj');

  // The generated project ships no SHARED scheme: schemes are created under
  // xcuserdata the first time Xcode opens it, which never happens on a runner.
  // Ask xcodebuild what exists and fall back to the target, instead of failing
  // with "scheme App not found" after a successful checkout.
  let selector = ['-target', 'App'];
  try {
    const listed = JSON.parse(shOut('xcodebuild', ['-list', '-project', project, '-json']));
    if (listed.project?.schemes?.includes('App')) {
      selector = ['-scheme', 'App'];
    }
  } catch {
    // `-list` can fail on a project with no schemes at all; the target selector
    // is the safe default, so keep going.
  }

  sh('xcodebuild', [
    '-project',
    project,
    ...selector,
    '-sdk',
    'iphonesimulator',
    '-configuration',
    'Debug',
    '-derivedDataPath',
    derived,
    'CODE_SIGNING_ALLOWED=NO',
    'CODE_SIGNING_REQUIRED=NO',
    'build',
  ]);

  // Pick an iPhone on the HIGHEST available iOS runtime. Neither the device
  // list nor its order is stable across Xcode releases, and taking whatever
  // comes last silently measured iOS 18.7 on a runner that also had newer
  // runtimes — an answer about the wrong engine. Runtime identifiers look like
  // `com.apple.CoreSimulator.SimRuntime.iOS-18-7`, so the version is parsed
  // rather than string-compared (iOS-9 must not outrank iOS-18).
  const listed = JSON.parse(shOut('xcrun', ['simctl', 'list', 'devices', 'available', '--json']));
  const runtimeVersion = identifier => {
    const match = identifier.match(/iOS-(\d+)(?:-(\d+))?/);
    return match ? Number(match[1]) * 1000 + Number(match[2] || 0) : -1;
  };

  const iosRuntimes = Object.entries(listed.devices)
    .filter(([identifier, devices]) => runtimeVersion(identifier) >= 0 && devices.length > 0)
    .sort(([a], [b]) => runtimeVersion(b) - runtimeVersion(a));

  const chosen = iosRuntimes
    .map(([identifier, devices]) => [identifier, devices.filter(d => d.name.startsWith('iPhone'))])
    .find(([, devices]) => devices.length > 0);

  if (!chosen) throw new Error('no available iPhone simulator on this runner');
  const [runtimeId, iphones] = chosen;
  console.log(`simulator runtime: ${runtimeId} — device: ${iphones[iphones.length - 1].name}`);
  const udid = iphones[iphones.length - 1].udid;

  try {
    sh('xcrun', ['simctl', 'boot', udid]);
  } catch {
    // Already booted: simctl exits non-zero, which is not a failure here.
  }
  sh('xcrun', ['simctl', 'bootstatus', udid]);

  const app = join(derived, 'Build', 'Products', 'Debug-iphonesimulator', 'App.app');
  sh('xcrun', ['simctl', 'install', udid, app]);

  const launch = () => sh('xcrun', ['simctl', 'launch', udid, APP_ID]);
  launch();

  return restartMode => {
    if (restartMode === 'pause') {
      // Send the app to the background so WKWebView commits its data store,
      // mirroring the Android `pause` mode. simctl has no "press home", so this
      // foregrounds SpringBoard instead — best effort by nature, hence the
      // catch: a failure here must degrade the run to a plain kill, never abort
      // it and lose every other measurement.
      try {
        sh('xcrun', ['simctl', 'launch', udid, 'com.apple.springboard']);
        sh('sh', ['-c', 'sleep 3']);
      } catch {
        console.warn('could not background the app; falling back to a direct kill');
      }
    }
    try {
      sh('xcrun', ['simctl', 'terminate', udid, APP_ID]);
    } catch {
      // Not running — nothing to terminate.
    }
    launch();
  };
}

/**
 * Invariants that must hold, or the shell architecture is unsound.
 *
 * @param {object} first - Result of the first launch.
 * @param {object} second - Result of the cold restart.
 * @param {'pause'|'kill'} restartMode - How the app was terminated in between.
 * @returns {{name: string, ok: boolean, detail: string}[]} Ordered checks.
 */
function assertions(first, second, restartMode, apiHost, platform) {
  const sameSite = apiHost === 'localhost';
  const checks = [
    {
      name: 'native bridge injected under the production CSP',
      ok: first.bridge_Capacitor === 'object' && first.bridge_isNative === true,
      detail: `Capacitor=${first.bridge_Capacitor} isNative=${first.bridge_isNative}`,
    },
    {
      name: 'httpOnly session cookie stays invisible to JavaScript',
      ok: !String(first.document_cookie).includes('lia_session'),
      detail: `document.cookie=${JSON.stringify(first.document_cookie)}`,
    },
    {
      name: "credentials:'include' carries the session cookie (BFF contract)",
      ok: String(first.server_saw_cookies).includes(SESSION_SENTINEL),
      detail: String(first.server_saw_cookies),
    },
    {
      name: `session cookie survives a cold restart (${restartMode})`,
      ok: String(second.server_saw_cookies).includes(SESSION_SENTINEL),
      detail: String(second.server_saw_cookies),
    },
    {
      // Production splits web and API across two origins, so this is the path
      // every authenticated call actually takes. In same-site mode this MUST
      // hold on both engines. In cross-site mode it is a deployment constraint
      // rather than a defect: WKWebView's ITP blocks it, while Android permits
      // it because Capacitor enables third-party cookies unconditionally
      // (Bridge.create → MockCordovaWebViewImpl.init →
      // CapacitorCordovaCookieManager → setAcceptThirdPartyCookies(true)).
      name: `${sameSite ? 'cross-origin' : 'cross-site'} credentialed call to the API origin keeps its cookie`,
      ok: String(first.api_origin_saw_cookies).includes(API_SENTINEL),
      detail: String(first.api_origin_saw_cookies),
      advisory: !sameSite,
    },
    {
      name: 'SSE streams (the chat rail depends on it)',
      ok: first.sse?.ok === true,
      detail: JSON.stringify(first.sse),
    },
    {
      // WKWebView disables Service Workers unless the app declares
      // `WKAppBoundDomains` in Info.plist AND sets
      // `limitsNavigationsToAppBoundDomains` — a STATIC list of at most ten
      // domains, so it cannot follow a server URL chosen at runtime. Under a
      // per-deployment build the list can be generated from the configured URL,
      // which also relaxes ITP between the listed domains. Until the shell does
      // that, the absence is a documented architectural trade-off on iOS, not a
      // regression to fail on — while on Android it must keep working.
      name: 'Service Worker registers (offline shell, ADR-146)',
      ok: first.sw_registered === true,
      detail: `scope=${first.sw_scope ?? first.sw_error}`,
      advisory: platform === 'ios',
    },
    {
      name: 'the production CSP is genuinely enforced in this WebView',
      ok: first.csp_blocks_cross_origin === true,
      detail: `cross-origin fetch blocked=${first.csp_blocks_cross_origin}`,
    },
    {
      name: 'voice and geolocation APIs are reachable',
      ok: first.has_getUserMedia === true && first.has_geolocation === true,
      detail: `getUserMedia=${first.has_getUserMedia} geolocation=${first.has_geolocation}`,
    },
  ];

  // An advisory check is measured and reported, never fatal: it records a
  // platform behaviour the design accounts for, rather than a contract the
  // shell broke. Keeping them in the same list means they stay VISIBLE — a
  // limit that quietly disappears from the report is a limit nobody revisits.
  return checks.map(check => ({ ...check, advisory: check.advisory === true }));
}

/**
 * Platform limits recorded as evidence: they shape the design, not the verdict.
 *
 * @param {object} result - First-run probe result.
 * @returns {Record<string, boolean>} Limits observed on this engine.
 */
function platformLimits(result) {
  return {
    // WKWebView hides `navigator.serviceWorker` unless the app declares
    // WKAppBoundDomains; Android WebView exposes it unconditionally.
    service_worker_unavailable: result.has_serviceWorker === false,
    // No Push API in either WebView → push must be native on BOTH platforms.
    web_push_unavailable: result.has_Notification === false && result.has_PushManager === false,
    // No cross-origin isolation → no SharedArrayBuffer → sherpaKws degrades to
    // tap-to-speak. Measured false even under COEP `require-corp`.
    cross_origin_isolation_unavailable: result.crossOriginIsolated === false,
    wake_word_unavailable: result.has_SharedArrayBuffer === false,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const platform = args.platform;
  if (platform !== 'android' && platform !== 'ios') {
    throw new Error('--platform must be "android" or "ios"');
  }

  const port = Number(args.port || 8787);
  const apiPort = Number(args['api-port'] || port + 1);

  // Production's exact shape — two different HOSTS under one registrable domain
  // (lia. / lia-back. on jeyswork.com) — cannot be reproduced on loopback, and
  // the reason is worth writing down so nobody "fixes" it back:
  //
  //   * `app.localhost` / `api.localhost` LOOK right but are not: for an
  //     unknown TLD the registrable domain is the whole name, so those two are
  //     DIFFERENT SITES. Measured — the Lax cookie was correctly withheld.
  //   * A real registrable domain (app./api.lia-probe.test) needs TLS to stay a
  //     secure context, and without a secure context there are no Service
  //     Workers left to measure. The two requirements exclude each other here.
  //
  // So the probe BOUNDS production instead of pretending to reproduce it:
  //   - `localhost:apiPort` — cross-origin, same host: proves the CORS +
  //     credentials plumbing carries cookies in this engine (asserted);
  //   - `127.0.0.1` — genuinely cross-site: records the ITP difference between
  //     the engines (advisory).
  // Production sits between the two. That it works under WebKit's ITP is
  // already evidenced outside this harness: LIA's web app runs in Safari on iOS
  // today, on the same engine and the same origin split.
  const docHost = 'localhost';
  const apiHost = args['api-host'] === '127.0.0.1' ? '127.0.0.1' : 'localhost';
  const apiUrl = `http://${apiHost}:${apiPort}`;
  const outPath = args.out || join(tmpdir(), `lia-webview-probe-${platform}.json`);
  const timeoutMs = Number(args.timeout || 300_000);
  const settleMs = Number(args.settle || FIRST_RUN_SETTLE_MS);

  // `pause` is the default because it is what actually happens to a real app:
  // the OS calls onPause/willResignActive before reclaiming it. `kill` is the
  // adversarial case (a crash, or "force stop" from Settings) and is measured
  // separately rather than asserted, since no app can prevent an abrupt SIGKILL.
  const restartMode = args.restart === 'kill' ? 'kill' : 'pause';

  // Two runs: the second document is served WITHOUT Set-Cookie, so it proves
  // the WebView's cookie store survived a cold restart.
  const server = await startProbeServer({ port, coep: args.coep, expected: 2, apiUrl });
  const sameSite = apiHost === 'localhost';
  const apiOrigin = await startApiOrigin(apiPort, apiHost);
  console.log(
    `document http://${docHost}:${port} — API ${apiUrl} (${sameSite ? 'cross-origin, same host' : 'cross-site'})`
  );

  try {
    const projectRoot = await scaffold(platform, `http://${docHost}:${port}`, Boolean(args.fresh));
    const relaunch =
      platform === 'android'
        ? driveAndroid(projectRoot, port, apiPort)
        : driveIos(projectRoot);

    const runs = await Promise.race([
      (async () => {
        await new Promise(resolve => setTimeout(resolve, settleMs));
        relaunch(restartMode);
        return server.results;
      })(),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error(`probe timed out after ${timeoutMs} ms`)), timeoutMs);
      }),
    ]);

    const [first, second] = runs;
    const checks = assertions(first, second, restartMode, apiHost, platform);
    const failed = checks.filter(check => !check.ok && !check.advisory);
    const advisories = checks.filter(check => !check.ok && check.advisory);

    const evidence = {
      platform,
      capacitor: CAPACITOR_VERSION,
      coep: typeof args.coep === 'string' ? args.coep : 'default',
      api_origin: apiUrl,
      api_topology: sameSite ? 'cross-origin, same host' : 'cross-site',
      restart_mode: restartMode,
      settle_ms: settleMs,
      user_agent: first.ua,
      runs,
      assertions: checks,
      platform_limits: platformLimits(first),
      verdict: failed.length === 0 ? 'PASS' : 'FAIL',
    };

    await writeFile(outPath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');

    for (const check of checks) {
      const label = check.ok ? 'PASS' : check.advisory ? 'NOTE' : 'FAIL';
      console.log(`${label}  ${check.name}`);
      console.log(`      ${check.detail}`);
    }
    if (advisories.length > 0) {
      console.log(`\n${advisories.length} platform behaviour(s) recorded as NOTE, not failure.`);
    }
    console.log(`\nrecorded platform limits: ${JSON.stringify(evidence.platform_limits)}`);
    console.log(`evidence written to ${outPath}`);

    if (failed.length > 0) process.exitCode = 1;
  } finally {
    await server.close();
    await apiOrigin.close();
  }
}

await main();
